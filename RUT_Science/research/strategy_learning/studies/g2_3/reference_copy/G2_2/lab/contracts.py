"""Frozen lab action space and public feature protocol."""
import hashlib
import json
import math

VERSION = "g2_2_decisions_v2"
FIELDS = ("intent", "goal", "unit_structure", "response", "unit", "provenance", "sample_basis", "factor", "levels", "features", "missing_policy")
METHODS = ("welch", "paired_t", "mean_ols")
ACTIONS = tuple("ask:"+name for name in FIELDS)+("ask:read_permission", "ask:execution_permission", "inspect", "retry_inspect", "resolve")+tuple("choose:"+name for name in METHODS)+("draft", "request_confirmation", "execute_mock", "respond", "stop")
FEATURE_NAMES = tuple("known:"+name for name in FIELDS)+tuple("unknown:"+name for name in FIELDS)+(
    "intent_chat", "intent_design", "intent_run", "goal_compare", "goal_prediction", "goal_causal",
    "structure_independent", "structure_paired", "structure_clustered", "structure_temporal",
    "read_allowed", "read_denied", "read_unknown", "execution_allowed", "execution_denied", "execution_unknown",
    "has_profile", "profile_repeated", "profile_missing", "profile_high_missing", "profile_bad_schema", "profile_budget_high",
    "has_conflict", "transient_failure", "permanent_failure", "revision_current", "draft_valid", "confirmed_current",
    "method_welch", "method_paired_t", "method_mean_ols", "missing_reject", "missing_drop", "sample_exploratory",
    "budget_fraction", "turn_fraction", "confirmation_refused", "bias")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def strict_json(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("Non-finite JSON value")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def validate_action(action):
    if type(action) is not str or action not in ACTIONS:
        raise ValueError("Unknown simulated action")


def finite_vector(values, length):
    if type(values) is not list or len(values) != length or any(type(x) not in {int, float} or not math.isfinite(x) for x in values):
        raise ValueError("Invalid feature vector")
