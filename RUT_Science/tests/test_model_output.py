"""Model display and replay tests use fake credentials and mock HTTP only."""
from contextlib import contextmanager
import copy
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from rich.console import Console
from rut_science.science_bot.session import ScienceSession
from rut_science.science_bot.terminal import show_model_output, show_event
from rut_science.util import digest, write_json


INTAKE = {"schema_version": "intake_proposal_v2", "fields": {
    "dataset_name": {"value": "generated", "source": "user", "evidence": "generated"}},
    "missing_required": [], "conflicts": [], "questions": []}
CANDIDATES = {"schema_version": "candidate_proposal_v1", "candidates": [
    {"template_id": "fit_mean", "parameters": {}, "purpose": "建立基线"}], "unresolved": []}
EXPLANATION = {"schema_version": "report_explainer_v1", "summary": "实测结果已保存，请核对科研报告。",
               "findings": [{"statement": "已执行允许的实验", "evidence": "verified_report"}],
               "limitations": ["仅限当前受控任务"], "artifact_refs": ["report.json"]}


class ModelOutputTests(unittest.TestCase):
    @contextmanager
    def api(self, *responses):
        queue = iter(responses)
        def provider(*args, **kwargs):
            value = next(queue)
            if isinstance(value, Exception):
                raise value
            envelope = {"model": "mock-actual-model", "id": "mock-request",
                        "usage": {"prompt_tokens": 100, "completion_tokens": 200},
                        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}
            return io.BytesIO(json.dumps(envelope).encode())
        with patch("rut_science.science_bot.llm.load_api_config", return_value={
                "endpoint": "https://example.invalid/chat/completions", "api_key": "fake_never_display_this_key"}), \
                patch("rut_science.agents.urllib.request.urlopen", side_effect=provider) as network:
            yield network

    def create(self, folder, **kwargs):
        return ScienceSession.create(folder, backend="api", planner="adaptive", **kwargs)

    def console(self):
        stream = io.StringIO()
        return Console(file=stream, width=120, force_terminal=False, highlight=False), stream

    def test_live_events_display_actual_roles_and_host_validation(self):
        with tempfile.TemporaryDirectory() as folder, self.api(INTAKE, CANDIDATES, EXPLANATION) as network:
            session = self.create(folder)
            console, stream = self.console()
            session.event_callback = lambda event: show_event(console, session, event)
            session.message("generated regression_output")
            session.confirm(session.confirmation)
            session.run()
            self.assertEqual(network.call_count, 3)
            self.assertTrue(session.env.done)
            self.assertTrue((session.folder/"explanation.json").exists())
            calls = session.model_output("list")["calls"]
            self.assertEqual([c["role"] for c in calls], ["intake_v2", "candidate_generator_v1", "report_explainer_v1"])
            self.assertTrue(all(c["status"] == "accepted" for c in calls))
            text = stream.getvalue()
            for expected in ("需求理解", "候选提议", "报告解释", EXPLANATION["summary"], "待宿主校验", "宿主契约检查通过", "planner=adaptive"):
                self.assertIn(expected, text)
            self.assertNotIn("模型选择理由", text)
            self.assertNotIn("fake_never_display_this_key", text)

    def test_replay_after_restore_is_read_only_and_does_not_call_model(self):
        with tempfile.TemporaryDirectory() as folder, self.api(INTAKE) as network:
            session = self.create(folder)
            session.message("generated")
            restored = ScienceSession.restore(session.folder)
            files_before = {p.relative_to(session.folder).as_posix(): p.read_bytes()
                            for p in session.folder.rglob("*") if p.is_file()}
            state_before = copy.deepcopy(restored.env.state)
            console, stream = self.console()
            for _ in range(2):
                show_model_output(console, restored)
                show_model_output(console, restored, "1")
                show_model_output(console, restored, "list")
            self.assertEqual(network.call_count, 1)
            self.assertEqual(restored.env.state, state_before)
            self.assertEqual(files_before, {p.relative_to(session.folder).as_posix(): p.read_bytes()
                                           for p in session.folder.rglob("*") if p.is_file()})
            self.assertIn("mock-actual-model", stream.getvalue())

    def test_invalid_user_provenance_is_displayed_as_rejected_without_execution(self):
        bad = copy.deepcopy(INTAKE)
        bad["fields"] = {"compute_units": {"value": 99, "source": "user", "evidence": "alpha 99"}}
        with tempfile.TemporaryDirectory() as folder, self.api(bad):
            session = self.create(folder)
            with self.assertRaises(ValueError):
                session.message("alpha 99")
            self.assertEqual(session.model_output()["status"], "rejected")
            self.assertEqual(session.model_output()["response"], bad)
            self.assertEqual(session.env.state["attempts"], 0)
            self.assertFalse(session.status()["confirmed"])

    def test_missing_information_has_its_own_status(self):
        proposal = copy.deepcopy(INTAKE)
        proposal.update(missing_required=["target"], questions=["希望预测哪个目标？"])
        with tempfile.TemporaryDirectory() as folder, self.api(proposal):
            session = self.create(folder)
            session.message("generated")
            self.assertEqual(session.model_output()["status"], "needs_input")
            self.assertEqual(session.env.state["attempts"], 0)

    def test_invalid_candidate_does_not_become_an_accepted_plan(self):
        bad = copy.deepcopy(CANDIDATES)
        bad["candidates"][0]["template_id"] = "arbitrary_shell"
        with tempfile.TemporaryDirectory() as folder, self.api(bad):
            session = self.create(folder)
            with self.assertRaises(ValueError):
                session.propose()
            self.assertEqual(session.model_output()["status"], "rejected")
            self.assertFalse(session.meta["candidates_ready"])

    def test_real_llm_selector_reason_and_stale_rejection(self):
        for stale in (False, True):
            with self.subTest(stale=stale), tempfile.TemporaryDirectory() as folder:
                session = ScienceSession.create(folder, backend="api", planner="llm")
                response = {"schema_version": "action_selection_v1", "observation_ref": "old" if stale else session.env.observe()["observation_ref"],
                            "action_id": "mean", "evidence_refs": [], "reason": "先建立低成本基线"}
                with self.api(response):
                    if stale:
                        with self.assertRaises(ValueError):
                            session.llm.choose(session.env.observe())
                    else:
                        self.assertEqual(session.llm.choose(session.env.observe()), "mean")
                self.assertEqual(session.model_output()["status"], "rejected" if stale else "accepted")
                console, stream = self.console()
                show_model_output(console, session)
                self.assertIn(response["reason"], stream.getvalue())
                self.assertEqual(session.env.state["attempts"], 0)

    def test_explanation_rejection_keeps_scientific_report_available(self):
        bad = copy.deepcopy(EXPLANATION)
        bad["summary"] = "伪造的误差为 8.7654321"
        with tempfile.TemporaryDirectory() as folder:
            session = ScienceSession.create(folder, backend="offline", planner="adaptive")
            session.confirm(session.confirmation)
            session.run()
            report = copy.deepcopy(session.env.state["report"])
            session.meta["backend"] = "api"
            console, stream = self.console()
            session.event_callback = lambda event: show_event(console, session, event)
            with self.api(bad):
                session.finish()
            self.assertEqual(session.model_output()["status"], "rejected")
            self.assertEqual(session.env.state["report"]["scientific_success"], report["scientific_success"])
            self.assertEqual(session.env.state["report"]["sealed_error"], report["sealed_error"])
            self.assertFalse((session.folder/"explanation.json").exists())
            self.assertIn("宿主拒绝", stream.getvalue())
            self.assertIn("/report", stream.getvalue())

    def test_format_and_transport_failures_are_saved_without_fake_responses(self):
        for response, status, error in ((["wrong schema"], "schema_rejected", ValueError),
                                        (URLError("fake service failure"), "failed", RuntimeError)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder, self.api(response):
                session = self.create(folder)
                with self.assertRaises(error):
                    session.message("generated")
                restored = ScienceSession.restore(session.folder)
                self.assertEqual(restored.model_output()["status"], status)
                if status == "failed":
                    self.assertIsNone(restored.model_output()["response"])
                self.assertEqual(restored.env.state["requests"], 1)
                console, stream = self.console()
                show_model_output(console, restored)
                self.assertNotIn("fake_never_display_this_key", stream.getvalue())

    def test_legacy_output_replays_without_claiming_host_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            session = ScienceSession.create(folder, backend="offline", planner="adaptive")
            path = session.folder/"model_calls"/"0002_response.json"
            write_json(path, {"role": "report_explainer_v1", "response": EXPLANATION, "response_hash": digest(EXPLANATION)})
            self.assertEqual(ScienceSession.restore(session.folder).model_output()["status"], "legacy_unverified")
            before = path.read_bytes()
            console, stream = self.console()
            show_model_output(console, session)
            self.assertIn("未记录宿主校验状态", stream.getvalue())
            self.assertEqual(path.read_bytes(), before)

    def test_model_text_is_literal_and_cannot_send_terminal_controls(self):
        response = copy.deepcopy(EXPLANATION)
        response["summary"] = "[bold red]原文[/bold red]\x1b[2J\x9b31m\r\u202e"
        with tempfile.TemporaryDirectory() as folder:
            session = self.create(folder)
            write_json(session.folder/"model_calls"/"0001_response.json",
                       {"role": "report_explainer_v1", "response": response, "response_hash": digest(response)})
            console, stream = self.console()
            show_model_output(console, session)
            text = stream.getvalue()
            self.assertIn("[bold red]原文[/bold red]", text)
            for char in ("\x1b", "\x9b", "\r", "\u202e"):
                self.assertNotIn(char, text)
            self.assertIn("\\u001b", text)
            self.assertIn("\\u202e", text)

    def test_offline_empty_history_and_invalid_selectors_do_not_access_network(self):
        with tempfile.TemporaryDirectory() as folder, patch("rut_science.science_bot.llm.load_api_config", side_effect=AssertionError("must stay local")):
            session = ScienceSession.create(folder, backend="offline", planner="adaptive")
            session.message("generated 预算6")
            console, stream = self.console()
            self.assertIsNone(show_model_output(console, session))
            self.assertIn("离线模式未调用大语言模型", stream.getvalue())
            self.assertEqual(session.model_output("list"), {"calls": []})
            for selector in ("../0001_request.json", "-1", "0", "1 --anything", "999999999999", "1"):
                with self.assertRaises(ValueError):
                    session.model_output(selector)
            self.assertEqual(session.env.state["requests"], 0)
            self.assertEqual(session.env.state["cu"], 0)

    def test_replay_refuses_tampered_response(self):
        with tempfile.TemporaryDirectory() as folder:
            session = self.create(folder)
            write_json(session.folder/"model_calls"/"0001_response.json",
                       {"role": "intake_v2", "response": INTAKE, "response_hash": "wrong"})
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                session.model_output()


if __name__ == "__main__":
    unittest.main()
