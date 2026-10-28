"""Real bridge processes; all tasks synthetic, temporary projects, no model API."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.research import HUB, parse, saved, worker
from rut_science.science_bot.general.router import route_request
from rut_science.science_bot.general.registry import ToolRegistry
from rut_science.science_bot.terminal import COMMANDS


class ResearchSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project = self.base/"project with spaces"
        self.project.mkdir()
        self.session = GeneralSession.create(self.base/"sessions", backend="api", workspace=self.project,
            limits={"tool_calls": 30})
        self.api = patch("rut_science.science_bot.general.provider.load_api_config", side_effect=AssertionError("No model call in research mode"))
        self.api.start(); self.addCleanup(self.api.stop)

    def message(self, text, *, error=False):
        value = self.session.message(text)
        self.assertEqual(value["intent"], "research", value)
        self.assertEqual(bool(value.get("research_error")), error, value)
        self.assertFalse(value.get("execution_authorized"))
        self.assertIsNone(self.session.env)
        return value

    def files(self):
        result = self.message("/doe template factorial_2x2")
        data = result["research"]["result"]
        for name in ("request", "contract"):
            (self.project/(name+" file.json")).write_text(json.dumps(data[name]), encoding="utf-8")
        return data

    def test_help_and_status_work_without_calls_or_default_numeric_environment(self):
        r = self.message("/research")
        self.assertIn("G2.4", r["answer"])
        self.message("/research status")
        self.assertEqual(self.session.resources()["tool_attempts"], 0)
        self.assertEqual(self.session.resources()["llm_requests"], 0)
        self.assertIn("/research", COMMANDS); self.assertIn("/doe", COMMANDS)

    def test_demo_persists_and_restores_without_reexecution_or_extra_cost(self):
        first = self.message("/doe demo")
        value = first["research"]["result"]["validation"]
        self.assertTrue(value["ready_for_review"])
        self.assertIsNone(value["scientific_success"])
        self.assertEqual(self.session.resources()["tool_attempts"], 1)
        self.session = GeneralSession.restore(self.session.folder, workspace=self.project)
        with patch("rut_science.science_bot.general.research.worker", side_effect=AssertionError("cached replay launched process")):
            repeated = self.message("/doe demo")
        self.assertEqual(first["research"], repeated["research"])
        self.assertEqual(self.session.resources()["tool_attempts"], 1)
        self.assertEqual(self.session.status()["research"]["doe"]["ready_for_review"], True)
        self.assertEqual(self.session.research_report(), repeated["research"])

    def test_workspace_json_validates_and_recheck_notices_changed_input(self):
        data = self.files()
        first = self.message('/doe validate "request file.json" "contract file.json"')
        self.assertTrue(first["research"]["result"]["validation"]["ready_for_review"])
        data["contract"]["analysis"]["sigma"] *= 2
        (self.project/"contract file.json").write_text(json.dumps(data["contract"]), encoding="utf-8")
        changed = self.message("/doe recheck")
        v = changed["research"]["result"]["validation"]
        self.assertFalse(v["ready_for_review"])
        self.assertNotEqual(first["result_ref"], changed["result_ref"])
        self.assertIn("evidence_grounding", [c["code"] for c in v["checks"] if c["status"] == "blocked"])

    def test_doe_latest_survives_other_study_results_and_restores(self):
        self.message("/doe demo")
        self.message("/research results g2_2")
        self.session = GeneralSession.restore(self.session.folder)
        result = self.message("/doe recheck")
        self.assertTrue(result["research"]["result"]["validation"]["ready_for_review"])

    def test_inline_json_is_explicit_and_duplicate_keys_are_rejected(self):
        data = self.files()
        result = self.message("/doe validate "+json.dumps({"request": data["request"], "contract": data["contract"]}))
        self.assertTrue(result["research"]["result"]["validation"]["ready_for_review"])
        self.message('/doe validate {"request":{},"request":{},"contract":{}}', error=True)

    def test_extreme_numerical_diagnostics_remain_blocked_finite_json(self):
        data = self.files()
        data["contract"]["analysis"]["sigma"] /= 10
        value = self.message("/doe validate "+json.dumps({"request": data["request"], "contract": data["contract"]}))
        report = value["research"]["result"]["validation"]
        self.assertFalse(report["ready_for_review"])
        json.dumps(report, allow_nan=False)

    def test_confirm_and_resume_cannot_execute_research_result(self):
        self.message("/doe demo")
        self.assertFalse(self.session.status()["confirmed"])
        self.assertIsNone(self.session.confirmation)
        with self.assertRaises(ValueError): self.session.confirm(None)
        with self.assertRaises(ValueError): self.session.run()

    def test_g22_rule_and_bc_are_only_explicit_development_simulations(self):
        rule = self.message("/research simulate g2_2")["research"]["result"]
        bc = self.message("/research simulate g2_2 --policy bc --seed 37")["research"]["result"]
        self.assertEqual(rule["policy"], "rule"); self.assertEqual(bc["policy"], "bc")
        self.assertEqual(rule["split"], "development")
        self.assertIsNone(bc["metric"])
        self.assertEqual(self.session.status()["research"]["default_interview_policy"], "rule")

    def test_g23_rule_reuses_existing_job_and_checks_snapshot_restore(self):
        r = self.message("/research simulate g2_3")["research"]["result"]
        self.assertTrue(r["success"])
        self.assertTrue(r["state_restore_checked"])
        self.assertEqual(r["mock_launches"], 0)
        self.assertIsNone(r["metric"])

    def test_g23_all_frozen_policy_variants_compare_without_training(self):
        r = self.message("/research compare g2_3 --seed 37")["research"]["result"]
        self.assertEqual({v["policy"] for v in r["comparisons"]}, {"rule", "bc", "bc_ppo", "ppo_scratch", "feedback_baseline", "feedback_ppo"})
        self.assertTrue(all(v["score"] == "public_evidence_strict" for v in r["comparisons"]))
        scratch = next(v for v in r["comparisons"] if v["policy"] == "ppo_scratch")
        self.assertFalse(scratch["success"])

    def test_three_frozen_studies_verify_via_chat_and_verify_is_not_cached(self):
        for study in ("g2_2", "g2_3", "g2_4"):
            self.assertTrue(self.message("/research verify "+study)["research"]["result"]["passed"])
        before = self.session.resources()["tool_attempts"]
        self.message("/research verify g2_4")
        self.assertEqual(self.session.resources()["tool_attempts"], before+1)

    def test_exported_pending_queues_are_copies_and_pending_import_is_rejected(self):
        for command, count in (("/doe review-export", 42), ("/research review-export g2_2", 72)):
            r = self.message(command)
            records = r["research"]["result"]["records"]
            self.assertEqual(len(records), count)
            copied = self.session.folder/r["result_ref"]
            self.assertTrue((copied.parent/"pending_review_copy.jsonl").is_file())
            (self.project/"pending.jsonl").write_text(json.dumps(records[0])+"\n", encoding="utf-8")
            self.message("/doe review-import pending.jsonl" if count == 42 else "/research review-import g2_2 pending.jsonl", error=True)

    def test_claimed_expert_review_is_saved_without_training_or_verified_identity(self):
        r = self.message("/doe review-export")
        record = deepcopy(r["research"]["result"]["records"][0])
        record["review"].update(status="approved", verdict="acceptable", reviewer="synthetic-test-reviewer-not-expert",
            rationale="Import boundary unit test only", reviewed_at="2026-10-27T16:00:00+08:00")
        (self.project/"reviewed.jsonl").write_text(json.dumps(record)+"\n", encoding="utf-8")
        imported = self.message("/doe review-import reviewed.jsonl")["research"]["result"]
        self.assertFalse(imported["automatic_training"])
        self.assertFalse(imported["expert_identity_independently_verified"])

    def test_results_use_strict_g23_audit_and_g24_disclaims_expert_accuracy(self):
        r = self.message("/research results g2_3")["research"]["result"]
        self.assertEqual(r["strict_public_evidence_metrics"]["seed_21/ppo_scratch"], 0)
        r = self.message("/research results g2_4")["research"]["result"]
        self.assertEqual(r["human_expert_labels"], 0)
        self.assertFalse(r["heldout_records_scored"])

    def test_research_path_selection_cannot_escape_workspace_or_read_credentials(self):
        self.message('/doe validate "../outside.json" "contract.json"', error=True)
        self.message('/doe validate "API_key_Agent.json" "contract.json"', error=True)
        self.assertEqual(self.session.resources()["tool_attempts"], 0)

    def test_training_shell_unknown_model_and_heldout_requests_fail_closed(self):
        for cmd in ("/research train g2_3", "/research simulate g2_3 --policy evil", "/research simulate g2_2 --seed 99",
                    "/research simulate g2_3 --scenario new_heldout", "/research simulate g2_3 --checkpoint evil.pt",
                    "/doe execute", "/research simulate g2_3 --policy rule --policy bc"):
            with self.subTest(cmd=cmd): self.message(cmd, error=True)

    def test_explicit_natural_language_routes_but_explanation_and_negation_do_not(self):
        for text in ("运行DOE演示", "运行CViT模拟", "查看G2.3研究结果"):
            self.assertEqual(route_request(text).intent, "research")
        for text in ("不要运行DOE演示", "如何运行CViT模拟？", "DOE是什么？"):
            self.assertNotEqual(route_request(text).intent, "research")
        self.message("运行CViT模拟")

    def test_research_context_switch_suspends_interview(self):
        result = self.session.message("/interview")
        self.assertNotEqual(result.get("intent"), "research")
        self.message("/research")
        self.assertFalse(self.session.status()["interview"]["active"])

    def test_result_tamper_is_detected_on_restore(self):
        r = self.message("/doe demo")
        path = self.session.folder/r["result_ref"]
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError): GeneralSession.restore(self.session.folder)

    def test_old_session_without_new_metadata_restores(self):
        self.session.meta.pop("research_latest", None)
        self.session.meta.pop("research_cache", None)
        self.session.save()
        restored = GeneralSession.restore(self.session.folder)
        self.assertIsNone(restored.status()["research"]["latest"])

    def test_general_tool_budget_is_shared_and_enforced(self):
        self.session.limits["tool_calls"] = 1
        self.message("/doe demo")
        self.message("/research results g2_2", error=True)
        self.assertEqual(self.session.resources()["tool_attempts"], 1)

    def test_input_read_budget_is_enforced_before_worker_execution(self):
        self.files()
        self.session.limits["read_bytes"] = 1
        before = self.session.resources()["tool_attempts"]
        self.message('/doe validate "request file.json" "contract file.json"', error=True)
        self.assertEqual(self.session.resources()["tool_attempts"], before)


class TerminalTests(unittest.TestCase):
    def test_existing_terminal_dispatches_research_commands_and_refuses_confirm(self):
        from contextlib import nullcontext
        from io import StringIO
        from rich.console import Console
        import rut_science.science_bot.terminal as terminal
        lines = iter(["/research", "/doe demo", "/status", "/report", "/confirm", "/exit"])
        class Prompt:
            async def prompt_async(self, *args, **kwargs):
                return next(lines)
        output = StringIO()
        with tempfile.TemporaryDirectory() as base, \
             patch.object(terminal, "PromptSession", return_value=Prompt()), \
             patch.object(terminal, "patch_stdout", return_value=nullcontext()), \
             patch.object(terminal, "Console", return_value=Console(file=output, width=110)), \
             patch("rut_science.science_bot.general.provider.load_api_config", side_effect=AssertionError("terminal API")):
            code = terminal.main(["--backend", "offline", "--sessions", base])
        self.assertEqual(code, 0)
        self.assertIn("research / DOE", output.getvalue())
        self.assertIn("Execution: not authorized", output.getvalue())


class WorkerBoundaryTests(unittest.TestCase):
    def test_unknown_payload_keys_and_training_action_rejected_in_worker(self):
        for payload in ({"study": "g2_4", "action": "train"}, {"study": "g2_4", "action": "demo", "shell": "anything"}):
            with self.assertRaises(ValueError): worker(payload)

    def test_tool_requires_explicit_host_scope(self):
        registry = ToolRegistry()
        with self.assertRaises(ValueError): registry.execute("research_interface", {"payload": {"study": "g2_4", "action": "demo"}}, {})

    def test_worker_audit_blocks_writes_credentials_network_and_live_imports(self):
        script = '''import importlib.util,json,pathlib,socket,sys
path=pathlib.Path(sys.argv[1]); spec=importlib.util.spec_from_file_location("bridge",path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.install_guard()
blocked=0
for action in (lambda:path.with_name("forbidden_probe.txt").write_text("never"),
               lambda:(path.parents[3]/"API_key_Agent.json").read_text(), lambda:socket.socket(),
               lambda:__import__("rut_science")):
 try:action()
 except PermissionError:blocked+=1
print(json.dumps(dict(blocked=blocked)))'''
        result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(HUB/"online_worker.py")], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["blocked"], 4)
        self.assertFalse((HUB/"forbidden_probe.txt").exists())
