"""Native tool calls, failure accounting and replay, using mock HTTP only."""
import copy
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from rut_science.agents import ModelServiceError
from rut_science.budget import RunBudget, RunLimitError
from rut_science.science_bot.general.provider import GeneralProvider
from rut_science.science_bot.model_output import read_output
from rut_science.util import digest, write_json


CONFIG = {"endpoint": "https://example.invalid/chat/completions", "api_key": "fake_never_save_this_key"}
TOOLS = [{"type": "function", "function": {"name": "read_file", "description": "Read project text",
          "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]
MESSAGES = [{"role": "system", "content": "Use registered tools."}, {"role": "user", "content": "Read README"}]


def envelope(content="Answer", calls=None, usage=True, finish_reason=None):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = calls
    value = {"model": "mock-actual-model", "id": "mock-response", "choices": [{
        "finish_reason": finish_reason or ("tool_calls" if calls else "stop"), "message": message}]}
    if usage:
        value["usage"] = {"prompt_tokens": 100, "completion_tokens": 50}
    return value


def native_call(call_id="call_actual_id", arguments='{"path":"README.md"}'):
    return {"id": call_id, "type": "function", "function": {"name": "read_file", "arguments": arguments}}


class GeneralProviderTests(unittest.TestCase):
    def provider(self, folder, **kwargs):
        return GeneralProvider(folder, **kwargs)

    def request(self, response):
        def respond(request, **kwargs):
            if isinstance(response, Exception):
                raise response
            return io.BytesIO(json.dumps(response).encode("utf-8"))
        return patch("rut_science.science_bot.general.provider.urllib.request.urlopen", side_effect=respond)

    def setUp(self):
        self.config = patch("rut_science.science_bot.general.provider.load_api_config", return_value=CONFIG)
        self.config.start()
        self.addCleanup(self.config.stop)

    def test_native_calls_round_trip_real_id_and_host_status(self):
        with tempfile.TemporaryDirectory() as folder:
            provider = self.provider(folder)
            events = []
            provider.event_callback = events.append
            with self.request(envelope(None, [native_call()])) as network:
                result = provider.complete(MESSAGES, TOOLS, role="project_qa")
            self.assertEqual(result, {"content": None, "tool_calls": [{"id": "call_actual_id",
                "name": "read_file", "arguments": {"path": "README.md"}}], "actual_model": "mock-actual-model"})
            body = json.loads(network.call_args.args[0].data)
            self.assertEqual(body["tools"], TOOLS)
            self.assertEqual(body["max_tokens"], 1800)
            self.assertNotIn("response_format", body)
            self.assertEqual(read_output(folder)["status"], "pending_validation")
            provider.mark_validation("accepted")
            self.assertEqual(read_output(folder)["status"], "accepted")
            self.assertEqual([e["kind"] for e in events], ["model_output", "model_validation"])
            history = MESSAGES + [{"role": "assistant", "content": None, "tool_calls": [native_call()]},
                                  {"role": "tool", "tool_call_id": "call_actual_id", "content": '{"text":"Evidence"}'}]
            with self.request(envelope("Based on Evidence")) as network:
                provider.complete(history, TOOLS)
            self.assertEqual(json.loads(network.call_args.args[0].data)["messages"][-1]["tool_call_id"], "call_actual_id")
            self.assertEqual(provider.snapshot()["requests"], 2)
            self.assertEqual(provider.snapshot()["accounted_tokens"], 300)
            all_saved = "\n".join(path.read_text(encoding="utf-8") for path in provider.folder.rglob("*.json"))
            self.assertNotIn(CONFIG["api_key"], all_saved)
            self.assertNotIn("Authorization", all_saved)

    def test_restoration_preserves_ledger_and_numbering(self):
        with tempfile.TemporaryDirectory() as folder:
            first = self.provider(folder, max_requests=2)
            with self.request(envelope()):
                first.complete(MESSAGES)
            restored = self.provider(folder, max_requests=2)
            self.assertEqual(restored.snapshot()["requests"], 1)
            with self.request(envelope()):
                restored.complete(MESSAGES)
            self.assertEqual(read_output(folder, "list")["calls"][-1]["request_index"], 2)
            with self.request(envelope()) as network, self.assertRaises(RunLimitError):
                restored.complete(MESSAGES)
            network.assert_not_called()

    def test_long_lived_provider_reloads_shared_numeric_spend_and_call_numbers(self):
        with tempfile.TemporaryDirectory() as folder:
            provider = self.provider(folder)
            with self.request(envelope()):
                provider.complete(MESSAGES)
            provider.mark_validation("accepted")
            numeric_budget = RunBudget(max_requests=12, max_tokens=60000,
                calls=json.loads(provider.ledger_path.read_text(encoding="utf-8"))["calls"],
                path=provider.ledger_path)
            external = numeric_budget.reserve({"messages": MESSAGES, "max_tokens": 1800}, {"model": "numeric-model"})
            numeric_budget.finish(external, {"prompt_tokens": 500, "completion_tokens": 200}, "ok")
            response = {"numeric_result": "preserve this evidence"}
            write_json(provider.folder / "model_calls/0002_response.json", {"role": "numeric",
                "request_index": 2, "model": "numeric-model", "response": response,
                "response_hash": digest(response)})
            external_bytes = (provider.folder / "model_calls/0002_response.json").read_bytes()
            self.assertEqual(provider.snapshot()["requests"], 2)
            self.assertEqual(provider.snapshot()["accounted_tokens"], 850)
            with self.request(envelope()):
                provider.complete(MESSAGES)
            self.assertEqual(provider.snapshot()["requests"], 3)
            self.assertEqual(provider.snapshot()["accounted_tokens"], 1000)
            self.assertEqual(read_output(folder)["request_index"], 3)
            self.assertEqual(external_bytes, (provider.folder / "model_calls/0002_response.json").read_bytes())
            self.assertEqual(provider.snapshot()["calls"][1]["model"], "numeric-model")

    def test_transport_http_invalid_json_and_unknown_usage_keep_reservation(self):
        failures = [URLError("do not print private service details"),
                    HTTPError(CONFIG["endpoint"], 429, "error", None, None)]
        for failure in failures:
            with self.subTest(error=type(failure).__name__), tempfile.TemporaryDirectory() as folder:
                provider = self.provider(folder)
                with self.request(failure), self.assertRaises(ModelServiceError):
                    provider.complete(MESSAGES)
                snapshot = provider.snapshot()
                self.assertEqual(snapshot["requests"], 1)
                self.assertGreater(snapshot["unresolved_token_reservations"], 0)
                self.assertEqual(read_output(folder)["status"], "failed")
                self.assertTrue((provider.folder / "model_calls/0001_request.json").exists())
                self.assertIsNone(read_output(folder)["response"])
        with tempfile.TemporaryDirectory() as folder:
            provider = self.provider(folder)
            with patch("rut_science.science_bot.general.provider.urllib.request.urlopen", return_value=io.BytesIO(b"bad json")), self.assertRaises(ValueError):
                provider.complete(MESSAGES)
            self.assertGreater(provider.snapshot()["unresolved_token_reservations"], 0)
            self.assertEqual(read_output(folder)["status"], "schema_rejected")
        with tempfile.TemporaryDirectory() as folder:
            provider = self.provider(folder)
            with self.request(envelope(usage=False)):
                provider.complete(MESSAGES)
            self.assertGreater(provider.snapshot()["unresolved_token_reservations"], 0)

    def test_malformed_tool_calls_rejected_without_inventing_arguments(self):
        malformed = [
            [native_call(arguments="{bad")], [native_call(arguments="[]")],
            [native_call(arguments='{"path":"a","path":"b"}')],
            [native_call(arguments='{"path":NaN}')], [native_call(), native_call()],
            [{**native_call(), "id": ""}],
            [{**native_call(), "function": {"name": "shell", "arguments": "{}"}}],
        ]
        for calls in malformed:
            with self.subTest(calls=calls), tempfile.TemporaryDirectory() as folder:
                provider = self.provider(folder)
                with self.request(envelope(None, calls)), self.assertRaises(ValueError):
                    provider.complete(MESSAGES, TOOLS)
                self.assertEqual(read_output(folder)["status"], "schema_rejected")
                self.assertIsNone(read_output(folder)["response"])
                self.assertEqual(provider.snapshot()["accounted_tokens"], 150)
                provider.mark_validation("accepted")
                self.assertEqual(read_output(folder)["status"], "schema_rejected")

    def test_invalid_output_or_truncation_is_rejected(self):
        values = [envelope(None), envelope(""), envelope("partial", finish_reason="length"),
                  envelope(None, [native_call()], finish_reason="length"), {"choices": []},
                  envelope(123), envelope(calls="invalid")]
        for response in values:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as folder:
                provider = self.provider(folder)
                with self.request(response), self.assertRaises(ValueError):
                    provider.complete(MESSAGES, TOOLS)
                self.assertEqual(read_output(folder)["status"], "schema_rejected")

    def test_native_message_validation_prevents_mismatched_ids_before_network(self):
        bad_histories = [
            MESSAGES + [{"role": "tool", "tool_call_id": "invented", "content": "text"}],
            MESSAGES + [{"role": "assistant", "content": None, "tool_calls": [native_call()]}],
            MESSAGES + [{"role": "assistant", "content": None, "tool_calls": [native_call()]},
                        {"role": "tool", "tool_call_id": "different", "content": "text"}],
        ]
        for history in bad_histories:
            with self.subTest(history=history), tempfile.TemporaryDirectory() as folder:
                provider = self.provider(folder)
                events = []
                provider.event_callback = events.append
                with self.request(envelope()) as network, self.assertRaises(ValueError):
                    provider.complete(history, TOOLS)
                network.assert_not_called()
                self.assertEqual(provider.snapshot()["requests"], 0)
                self.assertEqual(events[-1]["kind"], "model_call_failed")

    def test_budget_admission_includes_tool_schemas(self):
        large_tools = copy.deepcopy(TOOLS)
        large_tools[0]["function"]["description"] = "x" * 50_000
        with tempfile.TemporaryDirectory() as folder:
            provider = self.provider(folder)
            with self.request(envelope()) as network, self.assertRaises(RunLimitError):
                provider.complete(MESSAGES, large_tools)
            network.assert_not_called()
            self.assertEqual(provider.snapshot()["requests"], 0)
        with tempfile.TemporaryDirectory() as folder:
            provider = self.provider(folder, max_tokens=10)
            with self.request(envelope()) as network, self.assertRaises(RunLimitError):
                provider.complete(MESSAGES)
            network.assert_not_called()

    def test_response_cannot_reuse_previous_tool_call_id(self):
        history = MESSAGES + [{"role": "assistant", "content": None, "tool_calls": [native_call()]},
                              {"role": "tool", "tool_call_id": "call_actual_id", "content": "text"}]
        with tempfile.TemporaryDirectory() as folder:
            provider = self.provider(folder)
            with self.request(envelope(None, [native_call()])), self.assertRaises(ValueError):
                provider.complete(history, TOOLS)
            self.assertEqual(read_output(folder)["status"], "schema_rejected")


if __name__ == "__main__":
    unittest.main()
