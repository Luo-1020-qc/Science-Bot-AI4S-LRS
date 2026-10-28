"""Semantic and recovery regressions found during the G1 integration review."""
import json
import unittest

import test_general_session as helpers
from rut_science.science_bot.general.conversation import GeneralSession, numeric_parameters


class GeneralIntegrationRegressions(unittest.TestCase):
    setUp = helpers.GeneralSessionTests.setUp
    api = helpers.GeneralSessionTests.api
    create = helpers.GeneralSessionTests.create

    def test_malformed_and_conflicting_resources_cannot_become_default_drafts(self):
        for text in ("预算6.5", "预算-6", "预算1e2", "预算6，预算7", "预算多少", "门槛-0.2",
                     "门槛0", "门槛0.2.5", "门槛nan", "门槛0.2，门槛0.3"):
            with self.subTest(text=text):
                session = self.create()
                result = session.message("运行 generated 实验，"+text)
                self.assertEqual(result["intent"], "clarify")
                self.assertIsNone(session.env)
                self.assertFalse((session.folder/"experiments").exists())
                self.assertEqual(session.resources()["tool_attempts"], 0)

    def test_numeric_values_are_whole_and_positive(self):
        self.assertEqual(numeric_parameters("预算6，门槛.15"), {"budget": 6, "quality_threshold": .15})
        self.assertEqual(numeric_parameters("budget=6 CU; threshold=1.5e-1"), {"budget": 6, "quality_threshold": .15})

    def test_file_listing_cannot_support_a_file_content_answer(self):
        call = {"id": "list_only", "type": "function", "function": {"name": "project_list", "arguments": "{}"}}
        def final(body):
            value = json.loads(body["messages"][-1]["content"])
            return helpers.envelope(json.dumps({"answer": "文件里有一个从未读取的模型。", "evidence_refs": [value["evidence_ref"]]}))
        with self.api(helpers.envelope(calls=[call]), final):
            session = GeneralSession.create(self.base/"api", workspace=self.project)
            with self.assertRaises(ValueError):
                session.message("解释 model.py 的结构")
        self.assertEqual(session.model_output()["status"], "rejected")
        self.assertIsNone(session.env)

    def test_answer_must_read_all_explicitly_selected_files(self):
        def final(body):
            value = json.loads(body["messages"][-1]["content"])
            return helpers.envelope(json.dumps({"answer": "比较两个文件。", "evidence_refs": [value["evidence_ref"]]}))
        with self.api(helpers.envelope(calls=[helpers.tool_call()]), final):
            session = GeneralSession.create(self.base/"api", workspace=self.project)
            with self.assertRaises(ValueError):
                session.message("解释 model.py 和 other.py")
        self.assertEqual(session.model_output()["status"], "rejected")

    def test_committed_turn_dispatch_is_not_repeated(self):
        session = self.create(workspace=self.project)
        first = session.message("读取 model.py")
        before = session.resources()
        from rut_science.science_bot.general.router import route_request
        replay = session.dispatch(route_request("读取 model.py", session.workspace).to_dict(), 1)
        self.assertEqual(first, replay)
        self.assertEqual(before, session.resources())


if __name__ == "__main__":
    unittest.main()
