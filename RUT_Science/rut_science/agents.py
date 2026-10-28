"""Offline protocol controls and an optional JSON-action HTTP model adapter.

Rule controls exercise the harness; their differences are authored behavior and
are NOT evidence that an LLM planner improves performance.
"""
import json
import re
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .util import canonical
from .util import digest
from .budget import RunBudget
from .configuration import load_api_config


def message(content: str, mode: str = "answer") -> dict:
    return {"type": "message", "content": content, "response_mode": mode}


def tool(name: str, **arguments) -> dict:
    return {"type": "tool_call", "name": name, "arguments": arguments}


class RuleAgent:
    def __init__(self, mode: str = "context"):
        if mode not in {"latest", "context", "dag"}:
            raise ValueError("Rule mode must be latest, context, or dag")
        self.mode = mode

    def reset(self, system_prompt: str, tools: list[dict], seed: int) -> None:
        self.plan = []

    def step(self, messages: list[dict]) -> dict:
        users = [m["content"] for m in messages if m["role"] == "user"]
        latest = users[-1]
        text = latest if self.mode == "latest" else "\n".join(users)
        # These are public research parameters in the user request, not gold labels.
        patterns = {
            "dataset": r"数据：([^；]+)", "target": r"预测目标：([^；]+)",
            "model": r"基线：([^；]+)", "fraction": r"训练比例：(\d+)%", "seed": r"划分种子：(\d+)",
        }
        slots = {k: re.search(p, text) for k, p in patterns.items()}
        if "禁止训练" in latest or ("先不要训练" in latest and "新训练模型" in latest):
            return message("训练约束与新模型结果要求存在冲突。请确认：是否允许训练后再给出真实报告？", "clarify")
        if not all(slots.values()):
            return message("请提供或确认数据、预测目标、基线方法及划分协议？", "clarify")
        values = {k: v.group(1).strip() for k, v in slots.items()}
        successful = [m for m in messages if m["role"] == "tool" and m["result"].get("status") == "ok"]
        observed = {}
        for event in successful:
            observed[event["name"]] = event["result"]
        if "inspect_dataset" not in observed:
            return tool("inspect_dataset", dataset_name=values["dataset"])
        dataset_id = observed["inspect_dataset"]["dataset_id"]
        if "validate_dataset" not in observed:
            return tool("validate_dataset", dataset_id=dataset_id, target=values["target"])
        if "允许训练" not in latest:
            return message("数据已核查；等待你确认训练与一次封存测试。")
        actions = [
            ("split_dataset", {"dataset_id": dataset_id, "target": values["target"],
                               "train_fraction": int(values["fraction"])/100, "seed": int(values["seed"])}),
            ("train_model", {"split_id": observed.get("split_dataset", {}).get("split_id"), "model": values["model"]}),
            ("evaluate_model", {"model_id": observed.get("train_model", {}).get("model_id")}),
            ("write_report", {"evaluation_id": observed.get("evaluate_model", {}).get("evaluation_id")}),
        ]
        if self.mode == "dag":
            # A public, deterministic dependency schedule, not a learned planner.
            self.plan = [{"tool": name, "depends_on": [actions[i-1][0]] if i else ["validate_dataset"]}
                         for i, (name, _) in enumerate(actions)]
        for name, arguments in actions:
            if name not in observed:
                return tool(name, **arguments)
        suffix = " 系统没有 instant-perfect-model 功能。" if "instant-perfect-model" in text else ""
        return message(f"报告已由真实计算生成：{observed['write_report']['report_id']}。测试指标封存在报告中。" + suffix)


class ModelServiceError(RuntimeError):
    """Transport/service failures are reported separately from task failures."""


class JSONHTTPAgent:
    """Generic chat-completions JSON transport. No native function-call claim."""
    def __init__(self, endpoint: str, model: str, policy: str = "direct",
                 api_key: str | None = None, budget: RunBudget | None = None, episode_id: str = "",
                 api_config=None, profile: int = 0, credential_field: str = "API",
                 max_output_tokens: int = 1024, protocol: str = "actions"):
        parsed = urlsplit(endpoint)
        if not parsed.hostname or not (parsed.scheme == "https" or
                (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})):
            raise ValueError("Use HTTPS, or localhost for a local model server.")
        if policy not in {"direct", "clarify", "dag"}:
            raise ValueError("Unknown model policy")
        if type(max_output_tokens) is not int or max_output_tokens < 1 or protocol not in {"actions", "plan"}:
            raise ValueError("Positive output token limit and actions/plan protocol required")
        self.max_output_tokens, self.protocol = max_output_tokens, protocol
        self.endpoint, self.model, self.policy = endpoint, model, policy
        if api_key is None:
            config = load_api_config(api_config, profile, credential_field)
            if endpoint != config["endpoint"]:
                raise ValueError("Agent endpoint must match API_key_Agent.json configuration")
            api_key = config["api_key"]
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("API_key_Agent.json must provide a nonempty credential")
        self.api_key = api_key
        self.timeout = 20.0
        self.budget = budget
        self.episode_id = episode_id

    def reset(self, system_prompt: str, tools: list[dict], seed: int) -> None:
        additions = {
            "direct": "", "clarify": "Explicitly resolve critical missing slots and conflicts; recover already stated slots from history.",
            "dag": "Maintain a research specification and dependency plan; only execute ready steps; retain valid evidence after errors.",
        }
        self.system = system_prompt + (additions[self.policy] if self.protocol == "actions" else "") + "\nTool registry (JSON):\n" + canonical(tools)
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self.actual_model = None
        self.call_records = []

    def step(self, messages: list[dict]) -> dict:
        wire = [{"role": "system", "content": self.system}]
        for event in messages:
            if event["role"] == "system":
                # Trusted runtime context is only present after its bound turn.
                # Keep one leading system message for provider compatibility.
                wire[0]["content"] += "\n" + event["content"]
            elif event["role"] == "tool":
                # A user-role envelope supports providers without native tool messages.
                wire.append({"role": "user", "content": "TOOL_RESULT_JSON: " + canonical({
                    "name": event["name"], "result": event["result"], "call_id": event["call_id"],
                })})
            else:
                wire.append({"role": event["role"], "content": event["content"]})
        body = {"model": self.model, "messages": wire, "temperature": 0,
                "max_tokens": self.max_output_tokens, "response_format": {"type": "json_object"}}
        host = urlsplit(self.endpoint).hostname
        if host in {"api.moonshot.cn", "api.moonshot.ai"}:
            # K2.6 supports non-thinking; sampling defaults are provider-specific.
            body.pop("temperature")
            body["thinking"] = {"type": "disabled"}
        elif host == "api.deepseek.com":
            body["thinking"] = {"type": "disabled"}
        context = {"episode_id": self.episode_id, "model": self.model,
                   "submitted_utc": datetime.now(timezone.utc).isoformat(),
                   "request_body_hash": digest(body)}
        record = self.budget.reserve(body, context) if self.budget is not None else dict(context)
        # Full body is retained for reproducibility; headers and secrets are omitted.
        record = {**record, "request_body": body}
        self.call_records.append(record)
        ledger_record = self.budget.calls[-1] if self.budget is not None else record
        started = time.monotonic()
        request = urllib.request.Request(self.endpoint, data=canonical(body).encode("utf-8"), headers={
            "Authorization": "Bearer " + self.api_key, "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            # Do not print response bodies, request headers, or credentials.
            record.update(status="http_error", http_status=exc.code)
            if self.budget is not None:
                self.budget.finish(ledger_record, None, "http_error", http_status=exc.code)
            raise ModelServiceError(f"HTTP model service status {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            record.update(status="transport_error", exception_type=type(exc).__name__)
            if self.budget is not None:
                self.budget.finish(ledger_record, None, "transport_error")
            raise ModelServiceError(f"Model transport failed: {type(exc).__name__}") from None
        except json.JSONDecodeError:
            record.update(status="invalid_provider_response")
            if self.budget is not None:
                self.budget.finish(ledger_record, None, "invalid_provider_response")
            raise ModelServiceError("Provider returned invalid JSON") from None
        if not isinstance(result, dict):
            if self.budget is not None:
                self.budget.finish(ledger_record, None, "invalid_provider_response")
            raise ModelServiceError("Provider response is not a JSON object")
        usage = result.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        for key in self.usage:
            self.usage[key] += int(usage.get(key, 0) or 0)
        self.actual_model = result.get("model", self.model)
        record.update(status="ok", usage=usage, actual_model=self.actual_model,
                      latency_ms=(time.monotonic()-started)*1000, response_id=result.get("id"),
                      finish_reason=(result.get("choices") or [{}])[0].get("finish_reason"))
        if self.budget is not None:
            self.budget.finish(ledger_record, usage, "ok", actual_model=self.actual_model,
                               latency_ms=record["latency_ms"], response_id=record["response_id"])
        try:
            return json.loads(result["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            return {"type": "invalid", "reason": "Model returned no valid JSON action"}
