"""G1 acceptance scenarios use temporary projects and mocked provider HTTP only."""
from contextlib import contextmanager
import io
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rut_science.budget import RunLimitError
from rut_science.science_bot.contracts import BudgetedResearchSpec
from rut_science.science_bot.general.conversation import GeneralSession


CONFIG = {"endpoint": "https://example.invalid/chat/completions", "api_key": "fake_g1_never_display_key"}
CANDIDATES = {"schema_version": "candidate_proposal_v1", "candidates": [
    {"template_id": "fit_mean", "parameters": {}, "purpose": "建立基线"}], "unresolved": []}
EXPLANATION = {"schema_version": "report_explainer_v1", "summary": "实际科研报告已保存。",
               "findings": [{"statement": "结果依据工具证据", "evidence": "verified_report"}],
               "limitations": ["仅限注册数值场景"], "artifact_refs": ["report.json"]}


def envelope(content=None, calls=None):
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return {"model": "mock-g1-model", "id": "mock-g1-response",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "choices": [{"finish_reason": "tool_calls" if calls else "stop", "message": message}]}


def tool_call(name="project_read", arguments=None, call_id="call_real_123"):
    return {"id": call_id, "type": "function", "function": {"name": name,
            "arguments": json.dumps(arguments or {"path": "model.py"}, ensure_ascii=False)}}


class GeneralSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project = self.base/"研究 project"
        self.project.mkdir()
        (self.project/"model.py").write_bytes(b"width = 32\noutput = width * 2\n")
        (self.project/"other.py").write_bytes(b"unselected_payload = 123\n")

    def create(self, **kwargs):
        return GeneralSession.create(self.base/"sessions", backend="offline", planner="adaptive", **kwargs)

    @contextmanager
    def api(self, *responses):
        queue = iter(responses)
        bodies = []

        def respond(request, **kwargs):
            body = json.loads(request.data)
            bodies.append(body)
            value = next(queue)
            if isinstance(value, Exception):
                raise value
            if callable(value):
                value = value(body)
            return io.BytesIO(json.dumps(value, ensure_ascii=False).encode("utf-8"))

        with patch("rut_science.science_bot.general.provider.load_api_config", return_value=CONFIG), \
                patch("rut_science.science_bot.llm.load_api_config", return_value=CONFIG), \
                patch("urllib.request.urlopen", side_effect=respond) as network:
            yield network, bodies

    def test_fresh_session_does_not_load_data_weights_or_credentials(self):
        with patch("rut_science.science_bot.session.load_data", side_effect=AssertionError("implicit data load")), \
                patch("rut_science.science_bot.session.LearnedPolicy", side_effect=AssertionError("implicit policy load")), \
                patch("rut_science.science_bot.general.provider.load_api_config", side_effect=AssertionError("implicit API")):
            session = GeneralSession.create(self.base/"fresh", backend="api", planner="rl")
            restored = GeneralSession.restore(session.folder)
            for item in (session, restored):
                status = item.status()
                self.assertIsNone(item.env)
                self.assertIsNone(item.spec)
                self.assertIsNone(item.confirmation)
                self.assertEqual(status["engine_version"], "general_v1")
                self.assertFalse(status["confirmed"])
                self.assertIsNone(status["observation"])
                self.assertEqual(status["resources"]["llm_requests"], 0)
            self.assertFalse((session.folder/"environment.json").exists())
            self.assertFalse((session.folder/"experiments").exists())

    def test_offline_questions_unknown_and_unsupported_never_start_default_experiment(self):
        requests = [("解释区组设计", "chat"), ("Darcy 是什么？", "chat"),
                    ("这是一条没有具体目标的描述", "clarify"),
                    ("用 CViT 训练当前模型", "unsupported"),
                    ("分析新 CSV 数据集", "unsupported")]
        with patch("rut_science.science_bot.session.load_data", side_effect=AssertionError("implicit data load")), \
                patch("rut_science.science_bot.general.provider.load_api_config", side_effect=AssertionError("offline API")):
            for request, intent in requests:
                with self.subTest(request=request):
                    session = self.create()
                    result = session.message(request)
                    self.assertEqual(result["intent"], intent)
                    self.assertIsNone(session.env)
                    self.assertFalse(session.status()["confirmed"])
                    self.assertEqual(session.resources()["llm_requests"], 0)
                    with self.assertRaises(ValueError):
                        session.confirm(None)
                    with self.assertRaises(ValueError):
                        session.run()

    def test_explicit_registered_numeric_drafts_have_correct_scope_and_need_confirmation(self):
        for dataset in ("generated", "darcy"):
            with self.subTest(dataset=dataset):
                session = self.create()
                result = session.message(f"运行 {dataset} 实验，预算6，门槛0.3")
                self.assertEqual(result["intent"], "numeric")
                self.assertEqual(session.spec.dataset, dataset)
                self.assertEqual(session.spec.compute_units, 6)
                self.assertEqual(session.spec.quality_threshold, .3)
                self.assertEqual(session.env.state["attempts"], 0)
                self.assertTrue(result["requires_confirmation"])
                self.assertFalse(session.status()["confirmed"])
                with self.assertRaises(ValueError):
                    session.run()

    def test_explicit_spec_retains_legacy_numeric_entry_compatibility(self):
        session = self.create(spec=BudgetedResearchSpec(dataset="generated", split="demo", compute_units=2))
        self.assertIsNotNone(session.env)
        self.assertEqual(session.spec.compute_units, 2)
        self.assertFalse(session.status()["confirmed"])

    def test_numeric_pause_restore_then_complete_uses_existing_evidence(self):
        session = self.create(workspace=self.project)
        session.message("运行 generated 回归实验，预算6")
        session.confirm(session.confirmation)
        session.run(max_steps=1)
        self.assertEqual(session.meta["phase"], "paused")
        self.assertEqual(session.env.state["attempts"], 1)
        first_evidence = session.env.state["experiments"]["mean"].copy()
        child_folder = session.numeric.folder
        restored = GeneralSession.restore(session.folder, workspace=self.project)
        self.assertEqual(restored.numeric.folder, child_folder)
        self.assertEqual(restored.env.state["experiments"]["mean"], first_evidence)
        restored.run()
        self.assertTrue(restored.env.done)
        self.assertIsNotNone(restored.research_report())
        self.assertEqual(restored.env.state["experiments"]["mean"]["attempts"], 1)
        self.assertTrue((restored.folder/"general_graph.sqlite").exists())
        self.assertTrue((child_folder/"graph.sqlite").exists())

    def test_new_question_revokes_previous_numeric_authority(self):
        session = self.create()
        session.message("运行 generated 回归实验，预算6")
        old_hash = session.confirmation
        session.confirm(old_hash)
        self.assertTrue(session.status()["confirmed"])
        result = session.message("解释随机区组设计")
        self.assertEqual(result["intent"], "chat")
        self.assertIsNone(session.env)
        self.assertFalse(session.status()["confirmed"])
        self.assertIsNone(session.numeric.meta["confirmed"])
        self.assertEqual(session.numeric.env.state["attempts"], 0)
        for item in (session, GeneralSession.restore(session.folder)):
            with self.assertRaises(ValueError):
                item.confirm(old_hash)
            with self.assertRaises(ValueError):
                item.run()

    def test_offline_project_answer_contains_real_bounded_source_evidence(self):
        session = self.create(workspace=self.project)
        with patch("rut_science.science_bot.general.provider.load_api_config", side_effect=AssertionError("offline API")):
            result = session.message("读取 model.py")
        self.assertEqual(result["intent"], "project_qa")
        self.assertIn("width = 32", result["answer"])
        expected_hash = hashlib.sha256((self.project/"model.py").read_bytes()).hexdigest()
        self.assertEqual(result["evidence_refs"], [f"model.py:L1-L2#{expected_hash[:12]}"])
        self.assertIsNone(session.env)
        self.assertEqual(session.resources()["tool_attempts"], 1)
        self.assertEqual(session.resources()["llm_requests"], 0)
        stored = list((session.folder/"tool_results").glob("*.json"))
        self.assertEqual(len(stored), 1)
        self.assertEqual(json.loads(stored[0].read_text(encoding="utf-8"))["sha256"], expected_hash)

    def test_workspace_restore_by_id_and_binding_enforced_for_general_sessions(self):
        session = GeneralSession.create(backend="offline", planner="adaptive", workspace=self.project)
        restored = GeneralSession.restore(session.meta["id"], workspace=self.project)
        self.assertEqual(restored.workspace.binding, session.workspace.binding)
        self.assertIsNone(restored.env)
        other = self.base/"different_project"
        other.mkdir()
        with self.assertRaises(ValueError):
            GeneralSession.restore(session.folder, workspace=other)

    def test_native_project_read_round_trip_has_ids_actual_citations_and_saved_validation(self):
        def final_answer(body):
            tool = body["messages"][-1]
            self.assertEqual(tool["role"], "tool")
            self.assertEqual(tool["tool_call_id"], "call_real_123")
            evidence = json.loads(tool["content"])
            self.assertEqual(evidence["text"], "width = 32\noutput = width * 2\n")
            return envelope(json.dumps({"answer": "width 为32，output是它的两倍。",
                                        "evidence_refs": [evidence["evidence_ref"]]}, ensure_ascii=False))

        with self.api(envelope(calls=[tool_call()]), final_answer) as (network, bodies):
            session = GeneralSession.create(self.base/"api", backend="api", planner="adaptive", workspace=self.project)
            result = session.message("解释 model.py 的结构")
            self.assertEqual(network.call_count, 2)
            self.assertEqual(result["intent"], "project_qa")
            self.assertIn("model.py:L1-L2#", result["evidence_refs"][0])
            self.assertEqual(session.resources()["llm_requests"], 2)
            self.assertEqual(session.resources()["llm_tokens"], 300)
            self.assertEqual(session.resources()["tool_attempts"], 1)
            self.assertIsNone(session.env)
            self.assertTrue(all(c["status"] == "accepted" for c in session.model_output("list")["calls"]))
            self.assertEqual(bodies[1]["messages"][-2]["tool_calls"][0]["id"], "call_real_123")
            wire = json.loads((session.folder/"turns/0001_messages.json").read_text(encoding="utf-8"))
            self.assertTrue(any(m.get("tool_call_id") == "call_real_123" for m in wire))
            saved = "\n".join(path.read_text(encoding="utf-8") for path in session.folder.rglob("*.json"))
            self.assertNotIn(CONFIG["api_key"], saved)
            self.assertNotIn("unselected_payload", saved)

    def test_project_answer_without_real_citations_is_rejected_and_restorable(self):
        bad_final = envelope(json.dumps({"answer": "虚构文件结论", "evidence_refs": ["invented"]}))
        with self.api(envelope(calls=[tool_call()]), bad_final):
            session = GeneralSession.create(self.base/"api", backend="api", planner="adaptive", workspace=self.project)
            with self.assertRaises(ValueError):
                session.message("解释 model.py")
        restored = GeneralSession.restore(session.folder)
        self.assertEqual(restored.meta["phase"], "paused")
        self.assertEqual(restored.model_output()["status"], "rejected")
        self.assertIsNone(restored.env)
        self.assertIsNone(restored.meta["last_answer"])
        self.assertEqual(restored.resources()["llm_requests"], 2)

    def test_unknown_native_tool_does_not_create_numeric_environment(self):
        with self.api(envelope(calls=[tool_call("arbitrary_shell", {"cmd": "train"})])):
            session = GeneralSession.create(self.base/"api", backend="api", planner="adaptive", workspace=self.project)
            with self.assertRaises(ValueError):
                session.message("读取 model.py")
        self.assertIsNone(session.env)
        self.assertEqual(session.resources()["tool_attempts"], 0)
        self.assertEqual(session.model_output()["status"], "schema_rejected")
        self.assertEqual(GeneralSession.restore(session.folder).model_output()["status"], "schema_rejected")

    def test_tool_cannot_read_unselected_file_or_turn_file_content_into_authority(self):
        bad_calls = [tool_call(arguments={"path": "other.py"})]
        final = envelope(json.dumps({"answer": "无有效文件证据", "evidence_refs": []}))
        with self.api(envelope(calls=bad_calls), final) as (network, bodies):
            session = GeneralSession.create(self.base/"api", backend="api", planner="adaptive", workspace=self.project)
            with self.assertRaises(ValueError):
                session.message("读取 model.py")
            self.assertEqual(network.call_count, 2)
            tool_result = json.loads(bodies[1]["messages"][-1]["content"])
            self.assertEqual(tool_result["error_type"], "ValueError")
            self.assertNotIn("unselected_payload", json.dumps(bodies))
        self.assertEqual(session.resources()["tool_attempts"], 1)
        self.assertFalse((session.folder/"tool_results").exists())
        self.assertTrue(all(c["status"] == "rejected" for c in session.model_output("list")["calls"]))

    def test_shared_ledger_survives_general_numeric_general_without_reset_or_collisions(self):
        with self.api(envelope("区组用于控制已知变异。"), envelope(json.dumps(CANDIDATES)),
                      envelope(json.dumps(EXPLANATION)), envelope("可以继续讨论其他问题。")) as (network, bodies):
            session = GeneralSession.create(self.base/"api", backend="api", planner="adaptive",
                                            limits={"llm_requests": 4})
            session.message("什么是区组设计？")
            self.assertEqual(session.resources()["llm_requests"], 1)
            session.message("运行 generated 回归实验，预算2")
            session.confirm(session.confirmation)
            session.run()
            self.assertTrue(session.env.done)
            self.assertEqual(session.resources()["llm_requests"], 3)
            self.assertEqual(session.numeric.env.state["requests"], 3)
            session.message("解释因子和水平的区别")
            self.assertEqual(session.resources()["llm_requests"], 4)
            self.assertEqual(session.resources()["llm_tokens"], 600)
            calls = session.model_output("list")["calls"]
            self.assertEqual([c["request_index"] for c in calls], [1, 2, 3, 4])
            self.assertEqual([c["role"] for c in calls], ["general_chat", "candidate_generator_v1",
                                                         "report_explainer_v1", "general_chat"])
            self.assertTrue(all(c["status"] == "accepted" for c in calls))
            self.assertEqual(network.call_count, 4)
            self.assertNotIn("tools", bodies[0])
            self.assertFalse((session.numeric.folder/"llm_ledger.json").exists())
            self.assertFalse((session.numeric.folder/"model_calls").exists())
            with self.assertRaises(RunLimitError):
                session.message("什么是随机化？")
            self.assertEqual(network.call_count, 4)
            self.assertEqual(session.resources()["llm_requests"], 4)

    def test_saved_outputs_replay_after_restore_without_writes_or_calls(self):
        with self.api(envelope("这是实际返回的回答。")) as (network, bodies):
            session = GeneralSession.create(self.base/"api", backend="api", planner="adaptive")
            session.message("什么是实验单位？")
            restored = GeneralSession.restore(session.folder)
            before = {p.relative_to(session.folder).as_posix(): p.read_bytes()
                      for p in session.folder.rglob("*") if p.is_file()}
            for _ in range(2):
                self.assertEqual(restored.model_output()["status"], "accepted")
                self.assertEqual(restored.model_output("1")["response"]["content"], "这是实际返回的回答。")
                self.assertEqual(len(restored.model_output("list")["calls"]), 1)
                restored.status()
            self.assertEqual(network.call_count, 1)
            self.assertEqual(before, {p.relative_to(session.folder).as_posix(): p.read_bytes()
                                     for p in session.folder.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
