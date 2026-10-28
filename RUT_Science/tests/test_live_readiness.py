import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rut_science.agents import JSONHTTPAgent
from rut_science.budget import RunBudget, RunLimitError
from rut_science.clarification import check_clarification
from rut_science.cli import main
from rut_science.configuration import load_api_config, load_profiles


class LiveReadinessTests(unittest.TestCase):
    def test_adjacent_objects_trailing_comma_and_quoted_comma_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"API_key_Agent.json"
            raw = '{"API":"fake,}value","base_url":"https://example.invalid/v1"}\n{"API":"other","base_url":"https://second.invalid",}'
            path.write_text(raw, encoding="utf-8")
            self.assertEqual(len(load_profiles(path)), 2)
            cfg = load_api_config(path)
            self.assertEqual(cfg["api_key"], "fake,}value")
            self.assertEqual(cfg["endpoint"], "https://example.invalid/v1/chat/completions")
            self.assertEqual(path.read_text(encoding="utf-8"), raw)

    def test_config_errors_do_not_include_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"API_key_Agent.json"
            path.write_text('{"API":"sensitive_fake", BROKEN}', encoding="utf-8")
            with self.assertRaises(ValueError) as error:
                load_api_config(path)
            self.assertNotIn("sensitive_fake", str(error.exception))

    def test_request_limit_and_actual_usage_replace_reservation(self):
        budget = RunBudget(max_requests=1, max_tokens=10000)
        body = {"messages": [{"role":"user", "content":"hello"}], "max_tokens": 20}
        entry = budget.reserve(body, {"episode_id":"a"})
        budget.finish(entry, {"prompt_tokens": 9, "completion_tokens": 4}, "ok")
        self.assertEqual(budget.snapshot()["accounted_tokens"], 13)
        with self.assertRaises(RunLimitError):
            budget.reserve(body, {})

    def test_unknown_usage_remains_reserved_and_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            budget = RunBudget(path=Path(folder)/"budget.json")
            entry = budget.reserve({"messages":[], "max_tokens":30}, {})
            budget.finish(entry, None, "timeout")
            saved=json.loads(budget.path.read_text(encoding="utf-8"))
            self.assertEqual(saved["unresolved_token_reservations"],entry["reservation"])
            self.assertEqual(saved["accounted_tokens"],entry["reservation"])

    def test_token_and_context_limits_prevent_network_admission(self):
        for budget in (RunBudget(max_tokens=1), RunBudget(max_context_bytes=1)):
            with self.subTest(budget=budget), self.assertRaises(RunLimitError):
                budget.reserve({"messages":[{"role":"user","content":"hello"}],"max_tokens":30}, {})
            self.assertFalse(budget.calls)

    def test_bilingual_relevant_question_and_fabricated_metric(self):
        for text in ("请指定资料以及要预测的性质？", "Which dataset and target property should I use?"):
            result=check_clarification(text,"missing_critical_context")
            self.assertTrue(result["relevant"] and result["requests_resolution"])
        result=check_clarification("I cannot provide a new model without training. Please confirm permission?", "unresolved_conflict")
        self.assertTrue(result["relevant"] and result["requests_resolution"])
        self.assertFalse(check_clarification("训练条件冲突，请确认？MAE=0", "unresolved_conflict")["no_invented_metric"])

    def test_resume_skips_saved_episodes_and_rejects_changed_config(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            output=Path(folder)/"run"
            args=["run","--agents","rule_context","--task","science_001","--output",str(output)]
            self.assertEqual(main(args),0)
            files=list((output/"episodes").glob("*.json"))
            before={p.name:p.read_bytes() for p in files}
            with patch("rut_science.cli.run_episode",side_effect=AssertionError("must not replay")):
                self.assertEqual(main(args+["--resume"]),0)
            self.assertEqual(before,{p.name:p.read_bytes() for p in files})
            benchmark_before=(output/"benchmark"/"tasks.json").read_bytes()
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(args+["--resume","--max-steps","19"])
            self.assertEqual(benchmark_before,(output/"benchmark"/"tasks.json").read_bytes())

    def test_provider_body_and_call_records_do_not_contain_credential(self):
        agent=JSONHTTPAgent("https://api.moonshot.cn/v1/chat/completions","kimi-k2.6",api_key="fake_secret",budget=RunBudget())
        agent.reset("Return JSON",[],0)
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self):return json.dumps({"model":"kimi-k2.6","usage":{"prompt_tokens":8,"completion_tokens":5},"choices":[{"message":{"content":"{}"},"finish_reason":"stop"}]}).encode()
        with patch("urllib.request.urlopen",return_value=Reply()) as network:
            agent.step([{"role":"user","content":"hello"}, {"role":"system", "content":"TRUSTED_SPEC"}])
        body=json.loads(network.call_args.args[0].data)
        self.assertEqual(body["thinking"],{"type":"disabled"})
        self.assertNotIn("temperature",body)
        self.assertNotIn("fake_secret",json.dumps(agent.call_records))
        self.assertEqual(sum(m["role"] == "system" for m in body["messages"]), 1)
        self.assertIn("TRUSTED_SPEC", body["messages"][0]["content"])
