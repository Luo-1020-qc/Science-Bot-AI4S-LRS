"""General HTTP acceptance uses loopback sockets and mocked model HTTP only."""
from contextlib import contextmanager
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen as real_urlopen

from rut_science.science_bot.api import make_server


CONFIG = {"endpoint": "https://example.invalid/chat/completions", "api_key": "fake_http_never_display_key"}


def envelope(content="实际模型回答", calls=None):
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return {"model": "mock-http-model", "id": "mock-http-response",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "choices": [{"finish_reason": "tool_calls" if calls else "stop", "message": message}]}


class GeneralHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.project = self.base/"project 中文"
        self.project.mkdir()
        (self.project/"model.py").write_bytes(b"width = 32\n")
        self.server = make_server(self.base/"sessions", port=0, workspace=self.project)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1/sessions"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)
        self.temp.cleanup()

    def request(self, path="", body=None, key=None, *, timeout=5, auth=True):
        headers = {}
        if auth:
            headers["Authorization"] = "Bearer "+self.server.service.token
        if key is not None:
            headers["Idempotency-Key"] = key
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.url+path, data=data, headers=headers)
        try:
            with real_urlopen(request, timeout=timeout) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def create(self, *, backend="offline", **extra):
        status, result = self.request(body={"backend": backend, "planner": "adaptive", **extra}, key="create")
        self.assertEqual(status, 200, result)
        return result

    @contextmanager
    def api(self, *responses):
        queue = iter(responses)
        model_bodies = []

        def respond(request, **kwargs):
            # Test clients use the saved real_urlopen; delegate defensively if
            # another loopback caller reaches this patched provider function.
            if request.full_url.startswith("http://127.0.0.1:"):
                return real_urlopen(request, **kwargs)
            model_bodies.append(json.loads(request.data))
            response = next(queue)
            if callable(response):
                response = response(model_bodies[-1])
            if isinstance(response, Exception):
                raise response
            return io.BytesIO(json.dumps(response, ensure_ascii=False).encode("utf-8"))

        with patch("rut_science.science_bot.general.provider.load_api_config", return_value=CONFIG), \
                patch("rut_science.science_bot.general.provider.urllib.request.urlopen", side_effect=respond) as network:
            yield network, model_bodies

    def test_fresh_http_session_has_no_numeric_environment_and_restores_after_cache_drop(self):
        with patch("rut_science.science_bot.session.load_data", side_effect=AssertionError("implicit numeric data")), \
                patch("rut_science.science_bot.general.provider.load_api_config", side_effect=AssertionError("implicit API")):
            created = self.create(backend="api")
            self.assertEqual(created["engine_version"], "general_v1")
            self.assertIsNone(created["spec"])
            self.assertIsNone(created["observation"])
            self.assertIsNone(created["draft_hash"])
            self.assertFalse(created["confirmed"])
            self.assertEqual(created["resources"]["llm_requests"], 0)
            identity = created["id"]
            self.server.service.sessions.clear()
            status, restored = self.request(f"/{identity}")
            self.assertEqual(status, 200, restored)
            self.assertEqual(restored["id"], identity)
            self.assertIsNone(restored["spec"])
            self.assertFalse((self.server.service.folder/identity/"experiments").exists())
            status, error = self.request(f"/{identity}/confirm", {"draft_hash": None}, "invalid-confirm")
            self.assertEqual(status, 409, error)

    def test_explicit_numeric_spec_still_creates_reviewable_draft(self):
        created = self.create(spec={"dataset": "generated", "split": "demo", "compute_units": 2,
                                    "quality_threshold": .3})
        self.assertEqual(created["active_task"], "numeric")
        self.assertEqual(created["spec"]["dataset"], "generated")
        self.assertEqual(created["spec"]["compute_units"], 2)
        self.assertEqual(created["spec"]["quality_threshold"], .3)
        self.assertFalse(created["confirmed"])
        self.assertTrue(created["draft_hash"])
        session = self.server.service.sessions[created["id"]]
        self.assertEqual(session.env.state["attempts"], 0)
        status, result = self.request(f"/{created['id']}/confirm", {"draft_hash": created["draft_hash"]}, "confirm")
        self.assertEqual(status, 200, result)
        self.assertTrue(result["confirmed"])

    def test_full_explicit_numeric_spec_fields_are_preserved(self):
        spec = {"dataset": "generated", "split": "dev", "compute_units": 2, "quality_threshold": .3,
                "group": 17, "task_seed": 93, "tool_attempts": 4, "decision_steps": 7,
                "fault_rate": .3, "llm_requests": 9, "llm_tokens": 45000, "active_seconds": 180}
        created = self.create(spec=spec)
        for field, expected in spec.items():
            with self.subTest(field=field):
                self.assertEqual(created["spec"][field], expected)
        self.assertEqual(created["resources"]["limits"]["llm_requests"], 9)
        self.assertEqual(created["resources"]["limits"]["llm_tokens"], 45000)

    def test_idempotent_message_and_model_output_get_do_not_repeat_provider_calls(self):
        with self.api(envelope()) as (network, bodies):
            created = self.create(backend="api")
            path = f"/{created['id']}/messages"
            body = {"text": "什么是实验单位？"}
            first_status, first = self.request(path, body, "message-once")
            second_status, second = self.request(path, body, "message-once")
            self.assertEqual(first_status, 200, first)
            self.assertEqual(second_status, 200, second)
            self.assertEqual(second, first)
            self.assertEqual(first["answer"], "实际模型回答")
            self.assertEqual(network.call_count, 1)
            status, latest = self.request(f"/{created['id']}/model-output")
            self.assertEqual(status, 200, latest)
            self.assertEqual(latest["response"]["content"], "实际模型回答")
            self.assertEqual(latest["status"], "accepted")
            status, listing = self.request(f"/{created['id']}/model-output?call=list")
            self.assertEqual(status, 200, listing)
            self.assertEqual([call["request_index"] for call in listing["calls"]], [1])
            status, numbered = self.request(f"/{created['id']}/model-output?call=1")
            self.assertEqual(status, 200, numbered)
            self.assertEqual(numbered, latest)
            status, current = self.request(f"/{created['id']}")
            self.assertEqual(status, 200, current)
            self.assertEqual(current["resources"]["llm_requests"], 1)
            self.assertEqual(current["resources"]["llm_tokens"], 150)
            self.assertEqual(network.call_count, 1)
            self.assertEqual(len(bodies), 1)

    def test_reused_idempotency_key_with_changed_payload_is_rejected(self):
        with self.api(envelope()) as (network, _):
            created = self.create(backend="api")
            path = f"/{created['id']}/messages"
            status, result = self.request(path, {"text": "什么是实验单位？"}, "same-key")
            self.assertEqual(status, 200, result)
            status, conflict = self.request(path, {"text": "什么是随机化？"}, "same-key")
            self.assertEqual(status, 409, conflict)
            self.assertIn("payload mismatch", conflict["detail"])
            self.assertEqual(network.call_count, 1)
            status, replay = self.request(path, {"text": "什么是实验单位？"}, "same-key")
            self.assertEqual(status, 200, replay)
            self.assertEqual(replay, result)

    def test_failed_model_request_replays_failure_without_spending_again(self):
        with self.api(URLError("mock service unavailable")) as (network, _):
            created = self.create(backend="api")
            identity = created["id"]
            path = f"/{identity}/messages"
            body = {"text": "什么是实验单位？"}
            first_status, first = self.request(path, body, "failed-message-once")
            self.assertEqual(first_status, 503, first)
            second_status, second = self.request(path, body, "failed-message-once")
            self.assertEqual(second_status, first_status, second)
            self.assertEqual(second, first)
            self.assertEqual(network.call_count, 1)
            status, current = self.request(f"/{identity}")
            self.assertEqual(status, 200, current)
            self.assertEqual(current["resources"]["llm_requests"], 1)
            self.assertGreater(current["resources"]["llm_tokens"], 0)
            self.assertEqual(current["phase"], "paused")
            status, output = self.request(f"/{identity}/model-output")
            self.assertEqual(status, 200, output)
            self.assertEqual(output["status"], "failed")
            self.assertIsNone(output["response"])
            self.assertEqual(network.call_count, 1)

    def test_status_and_cancel_remain_responsive_while_provider_is_blocked(self):
        started, release = threading.Event(), threading.Event()
        pending_call = {"id": "call_after_cancel", "type": "function", "function": {
            "name": "project_read", "arguments": '{"path":"model.py"}'}}

        def delayed(_body):
            started.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release mocked provider")
            return envelope(None, [pending_call])

        with self.api(delayed) as (network, _):
            created = self.create(backend="api")
            identity = created["id"]
            results = []
            errors = []

            def ask():
                try:
                    results.append(self.request(f"/{identity}/messages", {"text": "读取 model.py"},
                                                "blocked-message", timeout=12))
                except BaseException as error:
                    errors.append(error)

            pending = threading.Thread(target=ask, daemon=True)
            pending.start()
            try:
                self.assertTrue(started.wait(timeout=5), "provider was never reached")
                status, current = self.request(f"/{identity}", timeout=2)
                self.assertEqual(status, 200, current)
                self.assertEqual(current["phase"], "thinking")
                self.assertEqual(current["resources"]["llm_requests"], 1)
                status, events = self.request(f"/{identity}/events", timeout=2)
                self.assertEqual(status, 200, events)
                self.assertTrue(events["events"])
                status, cancelled = self.request(f"/{identity}/cancel", {}, "cancel-while-waiting", timeout=2)
                self.assertEqual(status, 200, cancelled)
                self.assertTrue(cancelled["cancel_requested"])
                status, current = self.request(f"/{identity}", timeout=2)
                self.assertEqual(status, 200, current)
                self.assertEqual(current["phase"], "cancelled")
            finally:
                release.set()
                pending.join(timeout=5)
            self.assertFalse(pending.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0], 409, results)
            self.assertEqual(network.call_count, 1)
            status, current = self.request(f"/{identity}")
            self.assertEqual(status, 200, current)
            self.assertEqual(current["phase"], "cancelled")
            self.assertEqual(current["resources"]["tool_attempts"], 0)
            self.assertIsNone(current["spec"])
            self.assertIsNone(current["last_answer"])
            status, output = self.request(f"/{identity}/model-output")
            self.assertEqual(status, 200, output)
            self.assertEqual(output["status"], "rejected")
            self.assertEqual(output["error_type"], "TaskCancelled")
            self.assertFalse((self.server.service.folder/identity/"tool_results").exists())
            status, replay = self.request(f"/{identity}/messages", {"text": "读取 model.py"}, "blocked-message")
            self.assertEqual(status, 409, replay)
            self.assertEqual(replay, results[0][1])
            self.assertEqual(network.call_count, 1)

    def test_http_is_server_bound_and_requires_token_and_mutation_key(self):
        status, _ = self.request(body={}, key="unauthorized", auth=False)
        self.assertEqual(status, 401)
        status, _ = self.request(body={"backend": "offline"})
        self.assertEqual(status, 409)
        status, result = self.request(body={"backend": "offline", "workspace": str(self.base)}, key="invalid-workspace")
        self.assertEqual(status, 409, result)


if __name__ == "__main__":
    unittest.main()
