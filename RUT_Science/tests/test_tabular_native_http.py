"""Native provider planning and existing HTTP entry for G2."""
import json
import unittest

import test_general_session as model_helpers
import test_general_http as http_helpers
import test_tabular_g2 as data_helpers
from rut_science.science_bot.general.conversation import GeneralSession


class TabularNativeTests(unittest.TestCase):
    setUp = data_helpers.TabularG2Tests.setUp
    spec = data_helpers.TabularG2Tests.spec
    api = model_helpers.GeneralSessionTests.api

    def arguments(self):
        return {key: value for key, value in self.spec().to_dict().items() if key != "schema_version" and value is not None}

    def prompt(self):
        return ("请对 groups.csv 设计独立两组比较，response=y，unit=id，factor=group，levels为A和B；"
                "数据为合成；样本依据：全部现有合成样本，探索性分析。")

    def test_native_csv_then_preparation_preserves_wire_ids_and_shared_budget(self):
        inspect = model_helpers.envelope(calls=[model_helpers.tool_call("csv_inspect", {"path": "groups.csv"}, "inspect_1")])
        def prepare(body):
            result = json.loads(body["messages"][-1]["content"])
            self.assertEqual(body["messages"][-1]["tool_call_id"], "inspect_1")
            self.assertEqual(result["rows"], 10)
            self.assertNotIn("text", result)
            return model_helpers.envelope(calls=[model_helpers.tool_call("prepare_tabular_experiment", self.arguments(), "prepare_2")])
        with self.api(inspect, prepare, model_helpers.envelope("可以继续讨论。")) as (network, bodies):
            session = GeneralSession.create(self.root/"native", workspace=self.project, planner="adaptive")
            result = session.message(self.prompt())
            self.assertTrue(result["requires_confirmation"])
            self.assertFalse(session.status()["confirmed"])
            self.assertFalse(session.tabular.meta["completed"])
            self.assertEqual(network.call_count, 2)
            offered = {t["function"]["name"] for t in bodies[0]["tools"]}
            self.assertEqual(offered, {"csv_inspect", "prepare_tabular_experiment"})
            session.confirm(session.confirmation)
            session.run()
            self.assertEqual(network.call_count, 2)
            self.assertEqual(session.resources()["tool_attempts"], 4)
            session.message("什么是区组设计？")
            self.assertEqual(session.resources()["llm_requests"], 3)
            self.assertEqual(session.resources()["llm_tokens"], 450)
            self.assertEqual([c["role"] for c in session.model_output("list")["calls"]],
                             ["tabular_planner", "tabular_planner", "general_chat"])
            wire = json.loads((session.folder/"turns/0001_messages.json").read_text(encoding="utf-8"))
            self.assertEqual([m["tool_call_id"] for m in wire if m["role"] == "tool"], ["inspect_1", "prepare_2"])

    def test_model_cannot_invent_source_unit_or_sample_basis(self):
        calls = [model_helpers.tool_call("csv_inspect", {"path": "groups.csv"}, "inspect"),
                 model_helpers.tool_call("prepare_tabular_experiment", self.arguments(), "invented")]
        with self.api(model_helpers.envelope(calls=calls), model_helpers.envelope("请补充数据来源和单位。")):
            session = GeneralSession.create(self.root/"native", workspace=self.project, planner="adaptive")
            result = session.message("请比较 groups.csv 中两组的响应")
            self.assertEqual(result["intent"], "clarify")
            self.assertIsNone(session.tabular)
            self.assertFalse((session.folder/"experiments").exists())
            self.assertEqual(session.model_output("1")["status"], "rejected")
            self.assertEqual(session.model_output("2")["status"], "needs_input")

    def test_inspection_and_model_text_alone_cannot_claim_completed_analysis(self):
        with self.api(model_helpers.envelope("我已分析，p=0.001，证明显著。")):
            session = GeneralSession.create(self.root/"native", workspace=self.project)
            result = session.message(self.prompt())
            self.assertEqual(result["intent"], "clarify")
            self.assertNotIn("0.001", result["answer"])
            self.assertFalse(session.status()["report_available"])
            self.assertIsNone(session.tabular)


class TabularHTTPTests(unittest.TestCase):
    setUp = http_helpers.GeneralHTTPTests.setUp
    tearDown = http_helpers.GeneralHTTPTests.tearDown
    request = http_helpers.GeneralHTTPTests.request
    create = http_helpers.GeneralHTTPTests.create

    def test_existing_messages_confirm_resume_report_and_idempotent_replay(self):
        rows = [[f"u{i}", "A" if i < 5 else "B", y] for i, y in enumerate([1, 2, 4, 6, 7, 4, 7, 8, 10, 13])]
        (self.project/"groups.csv").write_bytes(data_helpers.csv_text(["id", "group", "y"], rows).encode("utf-8"))
        spec = {"data_path": "groups.csv", "research_question": "两个组的响应是否不同", "design": "independent",
                "response": "y", "unit": "id", "factor": "group", "levels": ["A", "B"],
                "provenance": "synthetic", "sampling_note": "全部试验数据，探索性分析"}
        created = self.create()
        identity = created["id"]
        payload = {"text": "/design "+json.dumps(spec, ensure_ascii=False)}
        status, draft = self.request(f"/{identity}/messages", payload, "design")
        self.assertEqual(status, 200, draft)
        status, replay = self.request(f"/{identity}/messages", payload, "design")
        self.assertEqual(draft, replay)
        session = self.server.service.sessions[identity]
        self.assertEqual(session.resources()["tool_attempts"], 2)
        status, confirmed = self.request(f"/{identity}/confirm", {"draft_hash": draft["draft_hash"]}, "confirm")
        self.assertEqual(status, 200, confirmed)
        self.assertTrue(confirmed["confirmed"])
        status, _ = self.request(f"/{identity}/resume", {}, "run")
        self.assertEqual(status, 200)
        self.server.service.workers[identity].join(10)
        status, report = self.request(f"/{identity}/report")
        self.assertEqual(status, 200, report)
        self.assertEqual(report["schema_version"], "tabular_report_v1")
        self.assertAlmostEqual(report["metrics"]["mean_difference"], -4.4)
        self.request(f"/{identity}/resume", {}, "run")
        self.assertEqual(session.resources()["tool_attempts"], 4)
        self.assertEqual(session.resources()["llm_requests"], 0)
        self.server.service.sessions.clear()
        status, restored = self.request(f"/{identity}")
        self.assertEqual(status, 200, restored)
        self.assertTrue(restored["report_available"])
        self.assertEqual(restored["tabular"]["completed"], ["compare", "report"])


if __name__ == "__main__":
    unittest.main()
