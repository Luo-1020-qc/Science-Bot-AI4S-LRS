"""Native function-call transport with the existing credential and budget rules.

Only the host executes tools. Provider messages remain proposals until the host
marks their saved output as accepted or rejected.
"""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from ...agents import JSONHTTPAgent, ModelServiceError
from ...budget import RunBudget
from ...configuration import load_api_config
from ...util import canonical, digest, write_json


MAX_CONTEXT_BYTES = 50_000
MAX_OUTPUT_TOKENS = 1800


def _strict_json(value):
    """Reject duplicate keys and non-JSON numeric constants in tool arguments."""
    def object_pairs(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate JSON argument key")
            result[key] = item
        return result

    def invalid_constant(_value):
        raise ValueError("Non-finite JSON argument")

    return json.loads(value, object_pairs_hook=object_pairs, parse_constant=invalid_constant)


def _messages(messages):
    if not isinstance(messages, list) or not messages:
        raise ValueError("A nonempty message list is required")
    wire, seen_ids, pending_ids = [], set(), set()
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"system", "user", "assistant", "tool"}:
            raise ValueError("Unsupported message role")
        role = message["role"]
        content = message.get("content")
        if role == "assistant":
            if content is not None and not isinstance(content, str):
                raise ValueError("Assistant content must be text or null")
            item = {"role": role, "content": content}
            calls = message.get("tool_calls", [])
            if not isinstance(calls, list):
                raise ValueError("Assistant tool_calls must be a list")
            if calls:
                if pending_ids:
                    raise ValueError("Previous tool calls need results first")
                item["tool_calls"] = []
                for call in calls:
                    if not isinstance(call, dict) or call.get("type") != "function":
                        raise ValueError("Only native function calls are supported")
                    function = call.get("function")
                    call_id = call.get("id")
                    if not isinstance(call_id, str) or not call_id or call_id in seen_ids:
                        raise ValueError("Tool call IDs must be nonempty and unique")
                    if not isinstance(function, dict) or not isinstance(function.get("name"), str) or not function["name"]:
                        raise ValueError("Tool call name is required")
                    if not isinstance(function.get("arguments"), str) or not isinstance(_strict_json(function["arguments"]), dict):
                        raise ValueError("Tool arguments must encode a JSON object")
                    item["tool_calls"].append({"id": call_id, "type": "function", "function": {
                        "name": function["name"], "arguments": function["arguments"]}})
                    seen_ids.add(call_id)
                    pending_ids.add(call_id)
            elif pending_ids:
                raise ValueError("Tool results must precede the next assistant message")
        elif role == "tool":
            call_id = message.get("tool_call_id")
            if not isinstance(content, str) or not isinstance(call_id, str) or call_id not in pending_ids:
                raise ValueError("Tool result must match a pending native call ID")
            pending_ids.remove(call_id)
            item = {"role": "tool", "content": content, "tool_call_id": call_id}
        else:
            if not isinstance(content, str) or pending_ids:
                raise ValueError("Text is required and pending calls need tool results")
            item = {"role": role, "content": content}
        wire.append(item)
    if pending_ids:
        raise ValueError("All tool results are required before requesting another completion")
    return wire, seen_ids


def _tools(tools):
    if tools is None:
        return []
    if not isinstance(tools, list):
        raise ValueError("Tools must be a native function-schema list")
    result, names = [], set()
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            raise ValueError("Only native function tools are supported")
        function = tool.get("function")
        if not isinstance(function, dict):
            raise ValueError("Tool function schema is required")
        name, parameters = function.get("name"), function.get("parameters")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Tool names must be nonempty and unique")
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            raise ValueError("Tool parameters need an object schema")
        if "description" in function and not isinstance(function["description"], str):
            raise ValueError("Tool description must be text")
        canonical(tool)
        names.add(name)
        result.append(copy.deepcopy(tool))
    return result


class _NativeHTTPAgent(JSONHTTPAgent):
    """Keep endpoint validation and credentials; replace only the wire protocol."""
    def step(self, messages, tools=None):
        wire, previous_ids = _messages(messages)
        schemas = _tools(tools)
        body = {"model": self.model, "messages": wire, "temperature": 0,
                "max_tokens": self.max_output_tokens}
        if schemas:
            body.update(tools=schemas, tool_choice="auto")
        host = urlsplit(self.endpoint).hostname
        if host in {"api.moonshot.cn", "api.moonshot.ai"}:
            body.pop("temperature")
            body["thinking"] = {"type": "disabled"}
        elif host == "api.deepseek.com":
            body["thinking"] = {"type": "disabled"}

        # RunBudget counts messages. Include schemas in its admission estimate,
        # while sending and persisting only the actual native provider body.
        accounting = dict(body)
        if schemas:
            accounting["messages"] = wire + [{"role": "system", "content": canonical(schemas)}]
        context = {"episode_id": self.episode_id, "model": self.model,
                   "submitted_utc": datetime.now(timezone.utc).isoformat(),
                   "request_body_hash": digest(body)}
        ledger_record = self.budget.reserve(accounting, context)
        record = {**ledger_record, "request_body": body}
        self.call_records.append(record)
        started = time.monotonic()
        request = urllib.request.Request(self.endpoint, data=canonical(body).encode("utf-8"), headers={
            "Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
        usage = None
        try:
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    result = json.load(response)
            except urllib.error.HTTPError as exc:
                record.update(http_status=exc.code)
                raise ModelServiceError(f"HTTP model service status {exc.code}") from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                record.update(exception_type=type(exc).__name__)
                raise ModelServiceError(f"Model transport failed: {type(exc).__name__}") from None
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ValueError("Provider returned invalid JSON") from None
            if not isinstance(result, dict):
                raise ValueError("Provider response is not a JSON object")
            usage = result.get("usage")
            if not isinstance(usage, dict):
                usage = None
            actual = result.get("model", self.model)
            if not isinstance(actual, str) or not actual:
                raise ValueError("Provider model identity is invalid")
            self.actual_model = actual
            choices = result.get("choices")
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                raise ValueError("Exactly one provider choice is required")
            choice = choices[0]
            record.update(response_id=result.get("id"), finish_reason=choice.get("finish_reason"))
            message = choice.get("message")
            if not isinstance(message, dict) or message.get("role", "assistant") != "assistant":
                raise ValueError("Provider assistant message is missing")
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError("Provider content must be text or null")
            calls = message.get("tool_calls", [])
            if not isinstance(calls, list):
                raise ValueError("Provider tool_calls must be a list")
            parsed, seen = [], set(previous_ids)
            allowed_names = {tool["function"]["name"] for tool in schemas}
            for call in calls:
                if not isinstance(call, dict) or call.get("type") != "function":
                    raise ValueError("Provider returned an unsupported tool call")
                call_id, function = call.get("id"), call.get("function")
                if not isinstance(call_id, str) or not call_id or call_id in seen:
                    raise ValueError("Provider tool call ID is missing or duplicated")
                if not isinstance(function, dict) or function.get("name") not in allowed_names:
                    raise ValueError("Provider selected an unregistered tool")
                arguments = function.get("arguments")
                if not isinstance(arguments, str):
                    raise ValueError("Provider arguments must be a JSON string")
                try:
                    arguments = _strict_json(arguments)
                except (ValueError, TypeError):
                    raise ValueError("Provider tool arguments are invalid JSON") from None
                if not isinstance(arguments, dict):
                    raise ValueError("Provider tool arguments must be a JSON object")
                seen.add(call_id)
                parsed.append({"id": call_id, "name": function["name"], "arguments": arguments})
            if not parsed and (content is None or not content.strip()):
                raise ValueError("Provider returned no content or tool calls")
            if choice.get("finish_reason") not in ({"tool_calls"} if parsed else {"stop"}):
                raise ValueError("Provider response did not finish normally")
            output = {"content": content, "tool_calls": parsed, "actual_model": actual}
            self.budget.finish(ledger_record, usage, "ok", actual_model=actual,
                               latency_ms=(time.monotonic()-started)*1000,
                               response_id=record.get("response_id"))
            record.update(status="ok", usage=usage, actual_model=actual)
            return output
        except Exception as exc:
            status = "http_error" if "http_status" in record else (
                "transport_error" if isinstance(exc, ModelServiceError) else "invalid_provider_response")
            record.update(status=status, exception_type=type(exc).__name__)
            self.budget.finish(ledger_record, usage, status, actual_model=self.actual_model,
                               latency_ms=(time.monotonic()-started)*1000,
                               **({"http_status": record["http_status"]} if "http_status" in record else {}))
            raise


class GeneralProvider:
    def __init__(self, folder, model="deepseek-flash", max_requests=12, max_tokens=60_000):
        self.folder = Path(folder).resolve()
        self.model = model
        self.event_callback = None
        self.last_output = None
        self.ledger_path = self.folder / "llm_ledger.json"
        calls = json.loads(self.ledger_path.read_text(encoding="utf-8"))["calls"] if self.ledger_path.exists() else []
        self.budget = RunBudget(max_requests=max_requests, max_tokens=max_tokens,
                                max_context_bytes=MAX_CONTEXT_BYTES, calls=calls, path=self.ledger_path)

    def snapshot(self):
        self._reload_calls()
        return copy.deepcopy(self.budget.snapshot())

    def _reload_calls(self):
        # General and registered numerical tools share one ledger. A long-lived
        # provider must not reuse the call numbers from its earlier snapshot.
        # The session serializes execution while this file is read and updated.
        if self.ledger_path.exists():
            saved = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict) or not isinstance(saved.get("calls"), list):
                raise ValueError("Invalid shared model-call ledger")
            self.budget.calls = saved["calls"]

    def _status(self, index, role, status, *, error_type=None, response_hash=None, model=None):
        value = {"request_index": index, "role": role, "status": status, "model": model or self.model}
        if error_type:
            value["error_type"] = error_type
        if response_hash:
            value["response_hash"] = response_hash
        write_json(self.folder / "model_calls" / f"{index:04d}_status.json", value)
        return value

    def _emit(self, kind, payload):
        if self.event_callback:
            self.event_callback({"kind": kind, "payload": payload})

    def complete(self, messages, tools=None, role="general"):
        self._reload_calls()
        # Load credentials only at the point where a real call is requested.
        config = load_api_config()
        agent = _NativeHTTPAgent(config["endpoint"], self.model, api_key=config["api_key"],
                                 budget=self.budget, episode_id=self.folder.name,
                                 max_output_tokens=MAX_OUTPUT_TOKENS)
        agent.reset("", [], 0)
        before = len(self.budget.calls)
        try:
            response = agent.step(messages, tools)
        except Exception as exc:
            if len(self.budget.calls) > before:
                index = len(self.budget.calls)
                value = self._status(index, role, "failed" if isinstance(exc, ModelServiceError) else "schema_rejected",
                                     error_type=type(exc).__name__, model=agent.actual_model)
                self.last_output = (index, role)
                self._emit("model_output", value)
            else:
                self._emit("model_call_failed", {"role": role, "error_type": type(exc).__name__})
            raise
        else:
            index = len(self.budget.calls)
            response_hash = digest(response)
            write_json(self.folder / "model_calls" / f"{index:04d}_response.json", {
                "request_index": index, "role": role, "model": agent.actual_model,
                "response": response, "response_hash": response_hash})
            value = self._status(index, role, "pending_validation", response_hash=response_hash,
                                 model=agent.actual_model)
            self.last_output = (index, role)
            self._emit("model_output", value)
            return response
        finally:
            for record in agent.call_records:
                write_json(self.folder / "model_calls" / f"{record['request_index']:04d}_request.json",
                           {"role": role, **record})

    def mark_validation(self, status, error_type=None):
        if status not in {"accepted", "rejected", "needs_input"}:
            raise ValueError("Unsupported host validation status")
        if self.last_output is None:
            return
        index, role = self.last_output
        status_path = self.folder / "model_calls" / f"{index:04d}_status.json"
        previous = json.loads(status_path.read_text(encoding="utf-8"))
        if previous["status"] != "pending_validation":
            return
        value = self._status(index, role, status, error_type=error_type,
                             response_hash=previous["response_hash"], model=previous["model"])
        self._emit("model_validation", value)
