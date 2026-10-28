"""Reference rules and BC policies consume only the public observation."""
from .contracts import ACTIONS, FIELDS, FEATURE_NAMES, VERSION, digest, finite_vector
import random


def encode(obs):
    facts, profile, permissions = obs["facts"], obs["profile"] or {}, obs["permissions"]
    values = [float(name in facts) for name in FIELDS]+[float(name in obs["unknown"]) for name in FIELDS]
    values += [float(facts.get("intent") == value) for value in ("chat", "design", "run")]
    values += [float(facts.get("goal") == value) for value in ("compare_means", "prediction", "causal_effect")]
    values += [float(facts.get("unit_structure") == value) for value in ("independent_rows", "paired_units", "clustered", "temporal")]
    values += [float(permissions["read"] is True), float(permissions["read"] is False), float(permissions["read"] is None),
               float(permissions["execute"] is True), float(permissions["execute"] is False), float(permissions["execute"] is None)]
    values += [float(bool(profile)), float(profile.get("rows_per_unit", 1) > 1), float(profile.get("missing_fraction", 0) > 0),
               float(profile.get("missing_fraction", 0) > .3), float(obs["last_failure"] == "invalid_schema"),
               float(profile.get("estimated_execution_cost", 0) > obs["remaining_resource"])]
    values += [float(bool(obs["conflicts"])), float(obs["last_failure"] == "transient_timeout"),
               float(obs["last_failure"] == "invalid_schema"), float(obs["draft_valid"]), float(obs["draft_valid"]), float(obs["confirmed_current"])]
    values += [float(obs["method"] == method) for method in ("welch", "paired_t", "mean_ols")]
    values += [float(facts.get("missing_policy") == value) for value in ("reject", "drop_complete_case")]
    values += [float(facts.get("sample_basis") == "available_exploratory"), obs["remaining_resource"]/12, obs["turn"]/24,
               float(obs["confirmation_refused"]), 1.0]
    finite_vector(values, len(FEATURE_NAMES))
    return values


class RuleV2:
    name = "context_rule_v2"
    def choose(self, obs):
        facts = obs["facts"]
        if obs["remaining_questions"] == 0:
            return "stop"
        if obs["conflicts"]:
            return "resolve"
        if "intent" not in facts:
            return "ask:intent"
        if facts["intent"] == "chat":
            return "respond"
        if obs["permissions"]["read"] is None:
            return "ask:read_permission"
        if obs["permissions"]["read"] is False or obs["confirmation_refused"]:
            return "stop"
        for field in ("goal", "unit_structure"):
            if field in obs["unknown"]:
                return "stop"
            if field not in facts:
                return "ask:"+field
        if facts["goal"] == "causal_effect" or facts["unit_structure"] in {"clustered", "temporal"}:
            return "stop"
        if facts["goal"] == "prediction" and facts["unit_structure"] != "independent_rows":
            return "stop"
        if obs["profile"] is None:
            if obs["last_failure"] == "invalid_schema":
                return "stop"
            return "retry_inspect" if obs["last_failure"] == "transient_timeout" else "inspect"
        if facts["intent"] == "run":
            if obs["permissions"]["execute"] is None:
                return "ask:execution_permission"
            if obs["permissions"]["execute"] is False or obs["remaining_resource"] < obs["profile"]["estimated_execution_cost"]:
                return "stop"
        needed = ["response", "unit", "provenance", "sample_basis"]+( ["features"] if facts["goal"] == "prediction" else ["factor", "levels"])
        for field in needed:
            if field in obs["unknown"]:
                return "stop"
            if field not in facts:
                return "ask:"+field
        if obs["profile"]["missing_fraction"] and facts.get("missing_policy") != "drop_complete_case":
            return "stop" if obs["asked"].get("missing_policy") else "ask:missing_policy"
        method = "mean_ols" if facts["goal"] == "prediction" else "paired_t" if facts["unit_structure"] == "paired_units" else "welch"
        if obs["method"] != method:
            return "choose:"+method
        if not obs["draft_valid"]:
            return "draft"
        if not obs["confirmed_current"]:
            return "request_confirmation"
        return "execute_mock"


class SlotRule:
    """V1-style slot-order ablation, not an exact replay of the G2.1 policy."""
    name = "slot_order_ablation"
    def choose(self, obs):
        for name in FIELDS:
            if name in obs["unknown"]:
                return "stop"
            if name not in obs["facts"]:
                return "ask:"+name
        if obs["profile"] is None:
            if obs["permissions"]["read"] is None:
                return "ask:read_permission"
            if obs["permissions"]["read"] is False:
                return "stop"
            return "retry_inspect" if obs["last_failure"] == "transient_timeout" else "inspect"
        if obs["method"] != "welch":
            return "choose:welch"
        if not obs["draft_valid"]:
            return "draft"
        if obs["facts"]["intent"] == "run" and not obs["confirmed_current"]:
            return "request_confirmation"
        return "execute_mock" if obs["facts"]["intent"] == "run" else "draft"


class RandomLegal:
    name = "random_legal"
    def __init__(self, seed=41):
        self.rng = random.Random(seed)
    def choose(self, obs):
        return self.rng.choice([action for action, allowed in zip(ACTIONS, obs["mask"]) if allowed])


class BCPolicy:
    name = "bc"
    def __init__(self, value):
        import numpy as np
        if value.get("version") != VERSION or value.get("actions") != list(ACTIONS) or value.get("features") != list(FEATURE_NAMES):
            raise ValueError("Incompatible lab policy")
        self.weights = np.asarray(value["weights"], dtype=float)
        if self.weights.shape != (len(FEATURE_NAMES), len(ACTIONS)) or not np.isfinite(self.weights).all():
            raise ValueError("Invalid policy weights")
        self.identity = digest(value)
    def choose(self, obs):
        import numpy as np
        scores = np.asarray(encode(obs)) @ self.weights
        return ACTIONS[int(np.argmax(np.where(obs["mask"], scores, -1e9)))]
