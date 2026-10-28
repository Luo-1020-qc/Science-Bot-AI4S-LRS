"""Existing HTTP routes host multi-turn interview state and idempotence."""
import json
import unittest
import test_general_http as helpers
import test_tabular_g2 as fixtures


class InterviewHTTPTests(unittest.TestCase):
    setUp = helpers.GeneralHTTPTests.setUp
    tearDown = helpers.GeneralHTTPTests.tearDown
    request = helpers.GeneralHTTPTests.request
    create = helpers.GeneralHTTPTests.create

    def test_interview_through_existing_messages_and_resume_does_not_repeat(self):
        (self.project/"groups.csv").write_bytes(fixtures.csv_text(["id", "group", "y"],
            [[f"u{i}", "A" if i < 4 else "B", y] for i, y in enumerate([1, 3, 4, 7, 2, 5, 8, 9])]).encode("utf-8"))
        created = self.create()
        identity = created["id"]
        status, first = self.request(f"/{identity}/messages", {"text": "/interview groups.csv"}, "start")
        self.assertEqual(status, 200, first)
        self.assertEqual(first["action"], "ask:research_question")
        fields = {"research_question": "比较两组y", "response": "y", "unit": "id", "design": "independent",
                  "unit_structure": "independent_rows", "factor": "group", "levels": ["A", "B"],
                  "provenance": "synthetic", "sampling_note": "全部现有合成样本，探索性演示"}
        payload = {"text": "/answer "+json.dumps(fields, ensure_ascii=False)}
        status, draft = self.request(f"/{identity}/messages", payload, "fields")
        self.assertEqual(status, 200, draft)
        self.assertTrue(draft["requires_confirmation"])
        _, replay = self.request(f"/{identity}/messages", payload, "fields")
        self.assertEqual(replay, draft)
        self.server.service.sessions.clear()
        status, restored = self.request(f"/{identity}")
        self.assertEqual(status, 200, restored)
        self.assertEqual(restored["interview"]["fields"]["response"], "y")
        self.assertFalse(restored["confirmed"])
        status, _ = self.request(f"/{identity}/resume", {}, "unconfirmed")
        self.assertEqual(status, 409)
        self.request(f"/{identity}/confirm", {"draft_hash": draft["draft_hash"]}, "confirm")
        self.request(f"/{identity}/resume", {}, "run")
        self.server.service.workers[identity].join(10)
        status, report = self.request(f"/{identity}/report")
        self.assertEqual(status, 200, report)
        self.assertTrue(report["execution_success"])
        session = self.server.service.sessions[identity]
        self.assertEqual(session.resources()["tool_attempts"], 4)
        self.request(f"/{identity}/resume", {}, "run")
        self.assertEqual(session.resources()["tool_attempts"], 4)


if __name__ == "__main__":
    unittest.main()
