"""Bounded local repair; never retry uncertain or state-changing failures."""
from dataclasses import asdict, dataclass

RETRYABLE_CODES = ("transient_unavailable", "timeout_before_start")


@dataclass(frozen=True)
class RecoveryPolicy:
    enabled: bool = False
    max_total_retries: int = 2
    max_retries_per_node: int = 1

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.max_total_retries) is not int or type(self.max_retries_per_node) is not int:
            raise ValueError("Recovery policy types are invalid")
        if not 0 <= self.max_total_retries <= 3 or not 0 <= self.max_retries_per_node <= self.max_total_retries:
            raise ValueError("Recovery retry limits must be bounded by 0..3")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value=None):
        return cls(**value) if value is not None else cls()

    def permits(self, event, history, total_retries):
        count = sum(e.get("event") == "recovery_decision" and e.get("node_id") == event["node_id"] for e in history)
        return (self.enabled and total_retries < self.max_total_retries and count < self.max_retries_per_node
            and event["tool_result"].get("status") == "error" and event["tool_result"].get("error_code") in RETRYABLE_CODES
            and event["state_before"] == event["state_after"])


def recovery_checks(manifest, episode, history):
    policy = RecoveryPolicy.from_dict(manifest.get("recovery_policy"))
    calls = [e for e in episode["events"] if e["event_type"] == "tool_call"]
    failures = [e for e in calls if e["tool_result"].get("status") != "ok"]
    decisions = [e for e in history if e.get("event") == "recovery_decision"]
    checks = {"retries_within_budget": len(decisions) <= policy.max_total_retries,
              "failed_calls_atomic": all(e["state_before"] == e["state_after"] for e in failures),
              "only_transient_retries": all(e["tool_result"].get("error_code") in RETRYABLE_CODES for e in failures),
              "retry_preserves_arguments": True, "recovery_evidence_complete": len(failures) == len(decisions)}
    per_node = {}
    for event in failures:
        per_node[event["node_id"]] = per_node.get(event["node_id"], 0)+1
        index = calls.index(event)
        next_call = calls[index+1] if index+1 < len(calls) else None
        matching = [d for d in decisions if d.get("failed_call_id") == event["call_id"]]
        valid = bool(next_call and next_call["node_id"] == event["node_id"] and next_call["arguments"] == event["arguments"]
                     and next_call["plan_version"] > event["plan_version"] and len(matching) == 1)
        checks["retry_preserves_arguments"] &= valid
        if matching:
            checks["recovery_evidence_complete"] &= (matching[0].get("from_plan_hash") == event["plan_hash"] and
                next_call is not None and matching[0].get("to_plan_hash") == next_call["plan_hash"])
    checks["retries_within_budget"] &= all(n <= policy.max_retries_per_node for n in per_node.values())
    checks["recovery_authorized"] = policy.enabled or not failures
    checks["attempt_budget_preserved"] = len(calls) <= manifest["max_tool_calls"]
    return {k: bool(v) for k, v in checks.items()}


def apply_recovery_score(strict, manifest, episode, history):
    policy = RecoveryPolicy.from_dict(manifest.get("recovery_policy"))
    if not policy.enabled:
        return strict
    checks = recovery_checks(manifest, episode, history)
    science_passed = all(value for key, value in strict["checks"].items() if key != "logical_compliance")
    success = science_passed and all(checks.values()) and episode["termination"] == "completed_dialogue"
    return {"execution_success": bool(success), "strict_execution_success": strict["execution_success"],
            "recovery_success": bool(success), "checks": strict["checks"], "recovery_checks": checks,
            "score_protocol": "scientific_recovery_v1", "strict_score": strict,
            "failure_count": sum(e["event_type"] == "tool_call" and e["tool_result"].get("status") != "ok" for e in episode["events"])}
