"""Persistent admission limits and provider-reported usage for a whole run."""
from dataclasses import dataclass, field
from pathlib import Path

from .util import canonical, write_json


class RunLimitError(RuntimeError):
    pass


@dataclass
class RunBudget:
    max_requests: int = 1200
    max_tokens: int = 3_000_000
    max_context_bytes: int = 120_000
    calls: list[dict] = field(default_factory=list)
    path: Path | None = None

    def snapshot(self) -> dict:
        return {
            "limits": {"max_requests": self.max_requests, "max_tokens": self.max_tokens,
                       "max_context_bytes": self.max_context_bytes},
            "requests": len(self.calls),
            "reported_prompt_tokens": sum(c.get("prompt_tokens", 0) for c in self.calls),
            "reported_completion_tokens": sum(c.get("completion_tokens", 0) for c in self.calls),
            "unresolved_token_reservations": sum(c["reservation"] for c in self.calls if not c.get("usage_known")),
            "accounted_tokens": sum(c.get("total_tokens", c["reservation"]) for c in self.calls),
            "monetary_cost": None, "calls": self.calls,
            "token_policy": "UTF-8 bytes plus message overhead used for admission; actual usage replaces estimate; unknown usage retains reservation",
        }

    def persist(self) -> None:
        if self.path is not None:
            write_json(self.path, self.snapshot())

    def reserve(self, body: dict, context: dict) -> dict:
        wire_bytes = len(canonical(body["messages"]).encode("utf-8"))
        reservation = wire_bytes + 64*len(body["messages"]) + body["max_tokens"]
        if wire_bytes > self.max_context_bytes:
            raise RunLimitError("Context byte limit exceeded")
        if len(self.calls) >= self.max_requests:
            raise RunLimitError("Whole-run request limit reached")
        if self.snapshot()["accounted_tokens"] + reservation > self.max_tokens:
            raise RunLimitError("Whole-run token admission limit reached")
        record = {"request_index": len(self.calls)+1, "reservation": reservation,
                  "context_bytes": wire_bytes, "status": "submitted", **context}
        self.calls.append(record)
        self.persist()
        return record

    def finish(self, record: dict, usage: dict | None, status: str, **metadata) -> None:
        record.update(status=status, **metadata)
        if isinstance(usage, dict) and all(isinstance(usage.get(k), int) and usage[k] >= 0
                                         for k in ("prompt_tokens", "completion_tokens")):
            record.update(usage_known=True, prompt_tokens=usage["prompt_tokens"], completion_tokens=usage["completion_tokens"],
                          total_tokens=usage["prompt_tokens"]+usage["completion_tokens"],
                          cached_tokens=usage.get("cached_tokens", (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)))
        self.persist()
