"""Existing authenticated HTTP messages endpoint serves the same research bridge."""
import unittest
from unittest.mock import patch
import test_general_http as helpers


class ResearchHTTPTests(unittest.TestCase):
    setUp = helpers.GeneralHTTPTests.setUp
    tearDown = helpers.GeneralHTTPTests.tearDown
    request = helpers.GeneralHTTPTests.request
    create = helpers.GeneralHTTPTests.create

    def test_detailed_tools_use_existing_authenticated_messages_and_idempotency(self):
        import json
        created = self.create(backend="offline")
        identity = created["id"]
        body = {"text": '/tools call project_create '+json.dumps({"title": "HTTP project", "objective": "offline"})}
        status, first = self.request(f"/{identity}/messages", body, "detailed-first", timeout=45)
        self.assertEqual(status, 200, first)
        self.assertIn("project_ref", first["tool_result"])
        status, repeated = self.request(f"/{identity}/messages", body, "detailed-first", timeout=45)
        self.assertEqual(first, repeated)
        status, current = self.request(f"/{identity}")
        self.assertEqual(current["tool_library"]["state"]["calls"], 1)
        self.assertFalse(current["tool_library"]["real_execution_authorized"])

    def test_doe_through_messages_idempotent_restore_and_report(self):
        with patch("rut_science.science_bot.general.provider.load_api_config", side_effect=AssertionError("No live API")):
            created = self.create(backend="api")
            identity = created["id"]
            body = {"text": "/doe demo"}
            status, result = self.request(f"/{identity}/messages", body, "doe", timeout=45)
            self.assertEqual(status, 200, result)
            self.assertTrue(result["research"]["result"]["validation"]["ready_for_review"])
            self.assertFalse(result["execution_authorized"])
            status, replay = self.request(f"/{identity}/messages", body, "doe")
            self.assertEqual(replay, result)
            session = self.server.service.sessions[identity]
            self.assertEqual(session.resources()["tool_attempts"], 1)
            self.server.service.sessions.clear()
            status, restored = self.request(f"/{identity}")
            self.assertEqual(status, 200, restored)
            self.assertTrue(restored["research"]["doe"]["ready_for_review"])
            status, report = self.request(f"/{identity}/report")
            self.assertEqual(status, 200, report)
            self.assertEqual(report["schema_version"], "online_research_result_v1")
            self.assertEqual(self.request(f"/{identity}/confirm", {"draft_hash": "anything"}, "confirm")[0], 409)
            self.assertEqual(self.request(f"/{identity}/resume", {}, "resume")[0], 409)

    def test_simulation_and_results_use_same_existing_endpoint(self):
        created = self.create()
        identity = created["id"]
        status, simulation = self.request(f"/{identity}/messages", {"text": "/research simulate g2_3"}, "simulate", timeout=45)
        self.assertEqual(status, 200, simulation)
        self.assertTrue(simulation["research"]["result"]["state_restore_checked"])
        status, result = self.request(f"/{identity}/messages", {"text": "/research results g2_2"}, "results", timeout=45)
        self.assertEqual(status, 200, result)
        self.assertIn("metrics", result["research"]["result"])

    def test_http_authentication_and_research_training_remain_closed(self):
        created = self.create()
        identity = created["id"]
        self.assertEqual(self.request(f"/{identity}", auth=False)[0], 401)
        status, result = self.request(f"/{identity}/messages", {"text": "/research train g2_3"}, "train")
        self.assertEqual(status, 200, result)
        self.assertTrue(result["research_error"])
