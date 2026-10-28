"""Real session registry and isolated tools; no live model or scientific job."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.registry import ToolRegistry
from rut_science.science_bot.general.tool_library import LIBRARY, catalog, summary
from rut_science.science_bot.general.router import route_request


class DetailedLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.session = GeneralSession.create(self.base/"sessions", backend="offline", limits={"tool_calls": 80})

    def call(self, name, arguments, key=None):
        return self.session.execute_library_tool(name, arguments, key=key or f"call_{self.session.meta['tool_attempts']}")

    def test_registry_contains_all_20_and_no_disabled_or_contract_only_tools(self):
        actual = {t["name"] for t in self.session.registry.specs() if t["domain"] == "detailed_research"}
        expected = {t["name"] for t in catalog() if t["implementation"] == "offline_implemented"}
        self.assertEqual(len(actual), 20); self.assertEqual(actual, expected)
        self.assertNotIn("cvit_train_real", actual)
        with self.assertRaises(ValueError): self.call("cvit_train_real", {})
        with self.assertRaises(ValueError): ToolRegistry().execute("project_create", {"title": "x", "objective": "x"}, {})

    def test_command_and_native_host_adapter_share_results_and_restore(self):
        result = self.session.message('/tools call project_create '+json.dumps({"title": "x", "objective": "offline"}))
        self.assertFalse(result.get("research_error"), result)
        ref = result["tool_result"]["project_ref"]
        self.assertEqual(self.session.status()["tool_library"]["state"]["refs"]["project_ref"], ref)
        restored = GeneralSession.restore(self.session.folder)
        self.assertEqual(restored.meta["tool_library"], self.session.meta["tool_library"])
        output = restored.execute_library_tool("artifact_read", {"artifact_ref": ref}, key="read")
        self.assertEqual(output["artifact"]["title"], "x")
        other = GeneralSession.create(self.base/"other", backend="offline")
        with self.assertRaises(ValueError): other.execute_library_tool("artifact_read", {"artifact_ref": ref}, key="foreign")

    def test_successful_calls_idempotent_and_budget_bounded(self):
        args = {"title": "same", "objective": "offline"}
        first = self.call("project_create", args, "same")
        attempts = self.session.meta["tool_attempts"]
        self.assertEqual(first, self.call("project_create", args, "same"))
        self.assertEqual(self.session.meta["tool_attempts"], attempts)
        self.assertEqual(self.session.meta["tool_library"]["calls"], 1)
        with self.assertRaises(ValueError): self.call("project_create", {**args, "title": "different"}, "same")
        limited = GeneralSession.create(self.base/"limited", backend="offline", limits={"tool_calls": 1})
        limited.execute_library_tool("project_create", args, key="first")
        with self.assertRaises(ValueError): limited.execute_library_tool("tool_catalog", {}, key="second")

    def test_discovery_reports_online_registration_without_duplicating_native_schemas(self):
        result = self.call("tool_catalog", {})
        self.assertTrue(result["live_agent_registered"])
        self.assertEqual(len(result["tools"]), 45)
        self.assertTrue(all(set(row) == {"name", "implementation", "purpose"} for row in result["tools"]))

    def test_host_mock_scenario_cannot_be_selected_by_policy(self):
        with self.assertRaisesRegex(ValueError, "chosen by the host"):
            self.call("job_run_mock", {"freeze_ref": "0"*64, "scenario": "benefit"})
        self.session.message('/tools scenario harm')
        self.assertEqual(summary(self.session)["state"]["scenario"], "harm")
        self.call("project_create", {"title": "x", "objective": "x"})
        changed = self.session.message('/tools scenario benefit')
        self.assertTrue(changed["research_error"])

    def replay(self, domain):
        self.session.message('/tools scenario benefit')
        trace = json.loads((LIBRARY/"runs"/domain/"demo_summary.json").read_text(encoding="utf-8"))["tool_calls"]
        for index, call in enumerate(trace):
            output = self.call(call["tool"], call["arguments"], domain+str(index))
            for name, ref in call["result"].items():
                if call["tool"] == "job_reconcile_mock" and name == "job_ref": continue
                if name.endswith("_ref"): self.assertEqual(output[name], ref)
        report = self.session.research_report()
        self.assertIsNotNone(report)
        restored = GeneralSession.restore(self.session.folder)
        self.assertEqual(restored.research_report(), report)
        self.assertEqual(restored.meta["tool_library"]["calls"], len(trace))
        self.assertFalse(report["real_scientific_claim_verified"])

    def test_full_darcy_review_repair_freeze_and_report_loop(self): self.replay("darcy")
    def test_full_cvit_review_repair_freeze_and_report_loop(self): self.replay("cvit")

    def test_native_model_proposals_execute_registered_tools_with_observed_citations(self):
        self.session.meta["backend"] = "api"
        session = self.session
        class Provider:
            def __init__(self): self.count = 0; self.validations = []
            def complete(self, messages, tools, role):
                self.count += 1
                self_names = {t["function"]["name"] for t in tools}
                if len(self_names) != 20: raise AssertionError("Wrong provider tools")
                job = next(t for t in tools if t["function"]["name"] == "job_run_mock")
                if "scenario" in job["function"]["parameters"]["properties"]: raise AssertionError("Hidden mock fixture leaked")
                if self.count == 1:
                    return {"content": None, "tool_calls": [{"id": "project", "name": "project_create", "arguments": {"title": "model proposal", "objective": "offline"}}]}
                output = json.loads(messages[-1]["content"])
                return {"tool_calls": [], "content": json.dumps({"answer": "Created a synthetic project only", "evidence_refs": [output["evidence_ref"]]})}
            def mark_validation(self, *args): self.validations.append(args)
        provider = Provider(); session._provider = provider
        with patch('rut_science.science_bot.general.provider.load_api_config', side_effect=AssertionError("No real API")):
            result = session.message('/tools chat create an offline project')
        self.assertFalse(result.get("research_error"), result)
        self.assertEqual(result["tool_calls"][0]["tool"], "project_create")
        self.assertTrue(result["evidence_refs"])
        self.assertEqual(provider.count, 2)

    def test_explicit_natural_route_but_explanation_does_not_grant_permissions(self):
        self.assertEqual(route_request("使用详细工具库：设计离线研究").reason, "explicit_detailed_tool_library")
        self.assertNotEqual(route_request("详细工具库是否接入了？").reason, "explicit_detailed_tool_library")

    def test_tampered_artifact_blocks_cross_process_restore(self):
        result = self.call("project_create", {"title": "tamper", "objective": "offline"})
        path = self.session.folder/"tool_library/objects"/(result["project_ref"][:24]+".json")
        value = json.loads(path.read_text(encoding="utf-8")); value["data"]["title"] = "modified"
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ValueError): GeneralSession.restore(self.session.folder)

    def test_public_state_and_host_preconditions_match_training_boundaries(self):
        self.session.message('/tools scenario harm')
        self.assertEqual(summary(self.session, policy=True)["state"]["scenario"], "host_private_mock_fixture")
        with self.assertRaisesRegex(ValueError, "Verify the current workflow"):
            self.call("job_run_mock", {"freeze_ref": "0"*64, "scenario": "harm"})
        with self.assertRaisesRegex(ValueError, "Report requires"):
            self.call("report_build", {"assessment_ref": "0"*64, "workflow_ref": "0"*64})


if __name__ == "__main__": unittest.main()
