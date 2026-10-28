import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rut_science.benchmark import build_tasks
from rut_science.environment import ScientificMLEnvironment
from rut_science.plan_spec import PlanSpec, PlanValidationError, public_control_plan
from rut_science.planning_agent import PlanningSession, read_checkpoint, session_lock
from rut_science.planning_cli import main
from rut_science.planning_evaluation import verify_artifacts
from rut_science.research_spec import ResearchSpec
from rut_science.util import digest, write_json


@unittest.skipIf(importlib.util.find_spec("langgraph") is None, "Optional planning dependency not installed")
class PlanningAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name) / "run"
        self.env = ScientificMLEnvironment()
        self.spec = ResearchSpec.from_task(build_tasks()[0], self.env.snapshot())

    def tearDown(self):
        self.temp.cleanup()

    def create(self, **kwargs):
        self.output.mkdir(exist_ok=True)
        return PlanningSession.create(self.output, self.env, self.spec, workflow="synthetic", task_id="science_001", **kwargs)

    def test_complete_offline_plan_executes_and_independently_scores(self):
        session = self.create()
        status = session.run()
        self.assertTrue(status["execution_success"])
        self.assertEqual(status["tool_calls"], 6)
        self.assertEqual(set(status["nodes"].values()), {"succeeded"})
        self.assertEqual(verify_artifacts(self.output)["status"], "passed")

    def test_pause_resume_does_not_repeat_completed_training(self):
        session = self.create()
        self.assertEqual(session.run(stop_after=4)["phase"], "paused")
        first = read_checkpoint(self.output)
        self.assertEqual(first["environment_state"]["budget"]["train_calls"], 1)
        session = PlanningSession.restore(self.output, ScientificMLEnvironment())
        self.assertTrue(session.run()["execution_success"])
        final = read_checkpoint(self.output)
        self.assertEqual(final["tool_calls"], 6)
        self.assertEqual(final["events"][:len(first["events"])], first["events"])
        self.assertEqual(sum(e.get("tool_name") == "train_model" for e in final["events"]), 1)
        complete = PlanningSession.restore(self.output, ScientificMLEnvironment())
        with patch.object(complete.env, "invoke", side_effect=AssertionError("must not rerun")):
            self.assertTrue(complete.run()["execution_success"])

    def test_invalid_file_plan_never_calls_tools(self):
        value = public_control_plan(self.spec).to_dict()
        value["nodes"][3]["arguments"]["model"] = "ridge"
        path = Path(self.temp.name) / "bad_plan.json"
        write_json(path, value)
        session = self.create(backend="file", plan_file=path)
        with patch.object(self.env, "invoke", side_effect=AssertionError("invalid plan must not execute")):
            self.assertEqual(session.run()["phase"], "plan_rejected")
        self.assertEqual(read_checkpoint(self.output)["tool_calls"], 0)

    def test_equivalent_validated_dataset_binding_executes_same_science(self):
        value = public_control_plan(self.spec).to_dict()
        value["nodes"][2]["arguments"]["dataset_id"] = "$validate.dataset_id"
        path = Path(self.temp.name) / "equivalent_plan.json"
        write_json(path, value)
        session = self.create(backend="file", plan_file=path)
        self.assertTrue(session.run()["execution_success"])
        self.assertEqual(verify_artifacts(self.output)["status"], "passed")

    def test_file_backend_accepts_powershell_utf8_bom(self):
        path = Path(self.temp.name) / "powershell_plan.json"
        path.write_text(json.dumps(public_control_plan(self.spec).to_dict()), encoding="utf-8-sig")
        session = self.create(backend="file", plan_file=path)
        self.assertTrue(session.run()["execution_success"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["validate", "--workflow", "synthetic", "--plan-file", str(path)]), 0)

    def test_revision_preserves_completed_nodes_and_records_versions(self):
        session = self.create()
        session.run(stop_after=3)
        old = PlanSpec.from_dict(session.state["plan"])
        value = old.to_dict()
        value.update(version=2, parent_plan_hash=old.plan_hash)
        # Rename only the unexecuted final node; dependencies and science stay valid.
        value["nodes"][-1]["node_id"] = "final_report"
        session.revise(PlanSpec.from_dict(value), "Operator renamed pending report node")
        self.assertEqual(session.state["phase"], "paused")
        resumed = PlanningSession.restore(self.output, ScientificMLEnvironment())
        self.assertTrue(resumed.run()["execution_success"])
        self.assertEqual(verify_artifacts(self.output)["plan_versions"], 2)
        self.assertEqual(resumed.state["tool_calls"], 6)

    def test_revision_cannot_change_completed_evidence_or_spec(self):
        session = self.create()
        session.run(stop_after=2)
        old = PlanSpec.from_dict(session.state["plan"])
        value = old.to_dict()
        value.update(version=2, parent_plan_hash=old.plan_hash)
        value["nodes"][0]["node_id"] = "changed_inspection"
        value["nodes"][1]["depends_on"] = ["changed_inspection"]
        value["nodes"][1]["arguments"]["dataset_id"] = "$changed_inspection.dataset_id"
        value["nodes"][2]["arguments"]["dataset_id"] = "$changed_inspection.dataset_id"
        with self.assertRaises(PlanValidationError):
            session.revise(PlanSpec.from_dict(value), "Attempt to replace completed node")
        value = old.to_dict() | {"version": 2, "parent_plan_hash": old.plan_hash, "research_spec_hash": "0"*64}
        with self.assertRaises(PlanValidationError):
            session.revise(PlanSpec.from_dict(value), "Attempt to replace specification")

    def test_uncertain_running_marker_refuses_automatic_replay(self):
        session = self.create()
        session.run(stop_after=2)
        session.state["node_status"]["split"] = "running"
        session.save()
        with self.assertRaisesRegex(ValueError, "uncertain"):
            PlanningSession.restore(self.output, ScientificMLEnvironment())

    def test_checkpoint_and_artifact_tampering_are_detected(self):
        session = self.create()
        session.run(stop_after=2)
        wrapper = json.loads((self.output / "checkpoint.json").read_text(encoding="utf-8"))
        wrapper["state"]["tool_calls"] += 1
        write_json(self.output / "checkpoint.json", wrapper)
        with self.assertRaises(ValueError):
            read_checkpoint(self.output)

    def test_result_publication_can_resume_without_scientific_reexecution(self):
        session = self.create()
        with patch("rut_science.planning_evaluation.seal_artifacts", side_effect=OSError("simulated publish interruption")):
            with self.assertRaises(OSError):
                session.run()
        restored = PlanningSession.restore(self.output, ScientificMLEnvironment())
        with patch.object(restored.env, "invoke", side_effect=AssertionError("must not rerun science")):
            self.assertTrue(restored.run()["execution_success"])
        self.assertEqual(verify_artifacts(self.output)["status"], "passed")

    def test_completed_resume_refuses_changed_artifacts(self):
        session = self.create()
        session.run()
        (self.output / "scientific_reports.json").write_text("{}", encoding="utf-8")
        restored = PlanningSession.restore(self.output, ScientificMLEnvironment())
        with self.assertRaises(ValueError):
            restored.run()

    def test_failed_tool_preserves_original_error_and_blocks_successors(self):
        session = self.create()
        original = self.env.invoke
        def failing(name, args):
            if name == "train_model":
                return {"status": "error", "error_code": "injected_test_failure", "message": "unit fixture"}
            return original(name, args)
        with patch.object(self.env, "invoke", side_effect=failing):
            status = session.run()
        self.assertEqual(status["phase"], "execution_failed")
        self.assertEqual(status["nodes"]["train"], "failed")
        self.assertEqual(status["nodes"]["evaluate"], "pending")
        self.assertEqual(self.env.snapshot()["budget"]["test_calls"], 0)
        self.assertEqual(session.state["events"][-1]["tool_result"]["error_code"], "injected_test_failure")

    def test_planner_only_sees_public_context_and_can_repair_invalid_proposal(self):
        config = {"endpoint": "https://example.invalid/chat/completions", "model": "mock", "api_key": "fake_key"}
        spec = self.spec
        class FakePlanner:
            def __init__(self, *args, **kwargs):
                self.calls = []
                self.call_records = []
                self.usage = {"prompt_tokens": 0, "completion_tokens": 0}
                self.actual_model = "mock"
            def reset(self, *args):
                pass
            def step(self, messages):
                self.calls.append(messages)
                value = public_control_plan(spec).to_dict()
                if len(self.calls) == 1:
                    value["nodes"][3]["arguments"]["model"] = "ridge"
                return value
        with patch("rut_science.planning_agent.load_api_config", return_value=config), patch("rut_science.planning_agent.JSONHTTPAgent", FakePlanner):
            session = self.create(backend="api", model="mock")
        self.assertTrue(session.run()["execution_success"])
        self.assertEqual(len(session.transport.calls), 2)
        wire = str(session.transport.calls)
        for forbidden in ("oracle", "initial_state", "rows", "predictions", "coefficients", "fake_key"):
            self.assertNotIn(forbidden, wire)
        self.assertEqual(len(session.state["validation_errors"]), 1)

    def test_host_deadline_prevents_execution_after_late_plan_reply(self):
        session = self.create()
        with patch.object(session, "remaining_seconds", return_value=-1):
            self.assertEqual(session.run()["phase"], "limit_reached")
        self.assertEqual(session.state["tool_calls"], 0)

    def test_cli_run_status_resume_and_verify(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["run", "--workflow", "synthetic", "--output", str(self.output), "--stop-after", "3"]), 0)
            self.assertEqual(main(["status", "--output", str(self.output)]), 0)
            self.assertEqual(main(["resume", "--output", str(self.output)]), 0)
            self.assertEqual(main(["verify", "--output", str(self.output)]), 0)

    def test_os_lock_prevents_two_concurrent_executors(self):
        with session_lock(self.output):
            with self.assertRaises(ValueError):
                with session_lock(self.output):
                    pass
