"""Policies select among host-legal interview actions; no tool permissions here."""
import json
from pathlib import Path
import random

from ....util import digest
from .state import FIELDS, missing_fields

FEATURE_VERSION = "design_decisions_v1"
ACTIONS = tuple("ask:"+field for field in FIELDS if field != "design")+("options:design", "resolve", "prepare", "stop")
ORDER = ("research_question", "data_path", "unit_structure", "design", "response", "unit", "provenance",
         "randomization_note", "factor", "levels", "features", "sampling_note", "missing_policy", "alpha", "seed")
FEATURE_NAMES = tuple("known:"+field for field in FIELDS)+tuple("missing:"+field for field in FIELDS)+(
    "is_independent", "is_paired", "is_prediction", "is_randomized", "has_unknown", "has_conflict",
    "ready", "has_blocker", "turn_fraction", "bias")


def observe(state):
    validation = state.get("validation") or {}
    missing = missing_fields(state)
    blockers = [c["code"] for c in validation.get("checks", []) if c["status"] == "blocked"]
    allowed = []
    if state["turns"] >= state["max_turns"] or state.get("closed_reason") == "cancelled":
        allowed = ["stop"]
    elif state["conflicts"]:
        allowed = ["resolve"]
    elif state["unknown"] or "unsupported_structure" in blockers or "design_structure_mismatch" in blockers:
        allowed = ["stop"]
    elif missing:
        allowed = ["options:design" if field == "design" else "ask:"+field for field in missing]
    elif ("missing_data_policy" in blockers and state["fields"].get("missing_policy") == "reject"
          and state["sources"].get("missing_policy", {}).get("kind") == "protocol_default"):
        allowed = ["ask:missing_policy", "stop"]
    elif validation.get("ready"):
        allowed = ["prepare"]
    else:
        allowed = ["stop"]
    fields = state["fields"]
    features = [float(field in fields) for field in FIELDS]+[float(field in missing) for field in FIELDS]+[
        float(fields.get("design") == name) for name in ("independent", "paired", "prediction")]+[
        float(fields.get("provenance") == "randomized"), float(bool(state["unknown"])), float(bool(state["conflicts"])),
        float(bool(validation.get("ready"))), float(bool(blockers)), state["turns"]/state["max_turns"], 1.0]
    return {"feature_version": FEATURE_VERSION, "features": features,
            "mask": [action in allowed for action in ACTIONS], "missing": missing,
            "blocker_codes": blockers}


class RuleInterviewPolicy:
    identity = digest({"policy": "design_rule_v1", "order": ORDER, "feature_version": FEATURE_VERSION})
    def choose(self, observation):
        legal = [action for action, mask in zip(ACTIONS, observation["mask"]) if mask]
        if not legal:
            raise ValueError("No legal interview action")
        for field in ORDER:
            action = "options:design" if field == "design" else "ask:"+field
            if action in legal:
                return action
        return legal[0]


class RandomInterviewPolicy:
    def __init__(self, seed=0):
        self.rng = random.Random(seed)
    def choose(self, observation):
        return self.rng.choice([action for action, legal in zip(ACTIONS, observation["mask"]) if legal])


class BCInterviewPolicy:
    """Read a fixed versioned JSON softmax policy; never deserialize pickle."""
    def __init__(self, folder):
        folder = Path(folder).resolve()
        path = folder/"policy.json"
        manifest_path = folder/"manifest.json"
        if path.resolve() != path or manifest_path.resolve() != manifest_path:
            raise ValueError("Policy files cannot be redirected")
        if path.stat().st_size > 1024*1024:
            raise ValueError("Policy file too large")
        self.value = json.loads(path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (self.value.get("feature_version") != FEATURE_VERSION or self.value.get("actions") != list(ACTIONS)
                or self.value.get("features") != list(FEATURE_NAMES) or digest(self.value) != manifest.get("policy_hash")):
            raise ValueError("BC policy version or hash mismatch")
        import numpy as np
        self.weights = np.asarray(self.value["weights"], dtype=float)
        if self.weights.shape != (len(FEATURE_NAMES), len(ACTIONS)) or not np.isfinite(self.weights).all():
            raise ValueError("Invalid BC policy dimensions")
        self.identity = manifest["policy_hash"]

    def choose(self, observation):
        import numpy as np
        if observation.get("feature_version") != FEATURE_VERSION or not any(observation["mask"]):
            raise ValueError("Invalid policy observation")
        scores = np.asarray(observation["features"]) @ self.weights
        scores = np.where(observation["mask"], scores, -np.inf)
        return ACTIONS[int(np.argmax(scores))]


def choose(state, *, policy=None):
    observation = observe(state)
    policy = policy or RuleInterviewPolicy()
    action = policy.choose(observation)
    if action not in ACTIONS or not observation["mask"][ACTIONS.index(action)]:
        raise ValueError("Policy proposed an action outside host constraints")
    return action, observation, getattr(policy, "identity", "unversioned")
