import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from rut_science.agents import JSONHTTPAgent, ModelServiceError
from rut_science.analysis import clustered_gap, summarize
from rut_science.contracts import SYSTEM_PROMPT
from rut_science.environment import ScientificMLEnvironment


class Response:
    def __init__(self, value):
        self.content = json.dumps(value).encode("utf-8")

    def read(self, *args):
        return self.content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class AnalysisAndAPITests(unittest.TestCase):
    def test_pair_intersection_and_task_clusters(self):
        records = [
            {"task_id": "a", "seed": 0, "behavior": "ideal", "score": {"execution_success": True}},
            {"task_id": "a", "seed": 0, "behavior": "underspecification", "score": {"execution_success": False}},
            {"task_id": "b", "seed": 0, "behavior": "ideal", "score": {"execution_success": False}},
            {"task_id": "b", "seed": 0, "behavior": "underspecification", "score": {"execution_success": None}},
        ]
        gap = clustered_gap(records, "underspecification")
        self.assertEqual(gap["gap_pp"], 100)
        self.assertEqual(gap["paired_runs"], 1)
        self.assertEqual(gap["task_clusters"], 1)

    def test_json_adapter_records_usage_without_credentials_in_payload(self):
        reply = {"model": "mock-version", "usage": {"prompt_tokens": 13, "completion_tokens": 7},
                 "choices": [{"message": {"content": '{"type":"message","content":"ready"}'}}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "API_key_Agent.json"
            path.write_text(json.dumps({"API": "fake_local_test_key", "endpoint": "https://example.invalid/chat/completions"}), encoding="utf-8")
            agent = JSONHTTPAgent("https://example.invalid/chat/completions", "mock", api_config=path)
        agent.reset(SYSTEM_PROMPT, ScientificMLEnvironment().available_tools(), 0)
        with patch("urllib.request.urlopen", return_value=Response(reply)) as mocked:
            decision = agent.step([{"role": "user", "content": "hello"}])
        self.assertEqual(decision["type"], "message")
        self.assertEqual(agent.usage, {"prompt_tokens": 13, "completion_tokens": 7})
        self.assertEqual(agent.actual_model, "mock-version")
        self.assertNotIn("fake_local_test_key", mocked.call_args.args[0].data.decode("utf-8"))

    def test_service_error_has_no_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "API_key_Agent.json"
            path.write_text(json.dumps({"API": "fake_local_test_key", "endpoint": "https://example.invalid/chat/completions"}), encoding="utf-8")
            agent = JSONHTTPAgent("https://example.invalid/chat/completions", "mock", api_config=path)
        agent.reset(SYSTEM_PROMPT, [], 0)
        with patch("urllib.request.urlopen", side_effect=TimeoutError("fake_local_test_key")):
            with self.assertRaises(ModelServiceError) as raised:
                agent.step([])
        self.assertNotIn("fake_local_test_key", str(raised.exception))

    def test_service_failure_excluded_but_counted(self):
        episode = {"events": [], "termination": "service_error", "elapsed_seconds": 0.1,
                   "tokens": {"prompt_tokens": 0, "completion_tokens": 0}}
        record = {"agent": "api_direct", "task_id": "a", "seed": 0, "behavior": "ideal", "suite": "paired_core",
                  "episode": episode, "score": {"execution_success": None, "interaction_success": None}}
        summary = summarize([record])["api_direct"]
        self.assertEqual(summary["core_runs"], 1)
        self.assertEqual(summary["scored_core_runs"], 0)
        self.assertEqual(summary["infrastructure_errors"], 1)
        self.assertIsNone(summary["overall_execution_sr"])

    def test_http_credential_transport_requires_actual_localhost(self):
        with self.assertRaises(ValueError):
            JSONHTTPAgent("http://localhost.example.invalid/chat", "mock")
