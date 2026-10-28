"""Portable JSON Schemas. Semantic lineage checks live in dataset_lib.py."""
from dataset_lib import ACTIONS, OBSERVATION_KEYS, VERSION


def object_schema(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required,
            "additionalProperties": False}


STRING = {"type": "string", "minLength": 1}
HASH = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
OBS = object_schema({key: {"type": "array" if key in {"user_messages", "unknown", "evidence", "history"} else ["object", "null"] if key == "draft" else "object"}
                     for key in sorted(OBSERVATION_KEYS)})
ACTION = object_schema({"name": {"enum": list(ACTIONS)}, "arguments": {"type": "object"}})
META = {"$schema": "https://json-schema.org/draft/2020-12/schema"}
TASK_SCHEMA = {**META, "title": "Harness illustrative task envelope; actor receives initial_observation only", **object_schema({
    "schema_version": {"const": VERSION}, "task_id": STRING, "root_group": STRING, "domain": {"enum": ["darcy", "cvit"]},
    "policy_split": {"enum": ["train", "development", "evaluation_example"]}, "scenario_for_curator_only": STRING,
    "data_lineage": {"type": "object"}, "initial_observation": OBS, "training_target": STRING,
    "expert_status": {"const": "pending"}, "origin": {"const": "hand_authored_scripted_example"}})}
TRANSITION_SCHEMA = {**META, "title": "Reference transition, not eligible for PPO", **object_schema({
    "decision_index": {"type": "integer", "minimum": 0}, "observation": OBS, "observation_hash": HASH,
    "action": ACTION, "feedback": object_schema({"source": {"const": "scripted_mock_feedback"}, "message": STRING,
        "blocking_codes": {"type": "array", "items": STRING}, "real_execution": {"const": False}, "scientific_metric": {"type": "null"}}),
    "next_observation": OBS, "next_observation_hash": HASH, "reward": {"type": "number"},
    "terminated": {"type": "boolean"}, "truncated": {"type": "boolean"},
    "behavior_log_probability": {"type": "null"}, "value_estimate": {"type": "null"},
    "reference_action_is_recommended": {"type": "boolean"}})}
PPO_SCHEMA = {**META, "title": "Future fresh on-policy PPO rollout contract; no such data generated here", **object_schema({
    "schema_version": {"const": "harness_ppo_rollout_v1"}, "task_id": STRING, "policy_hash": HASH,
    "rollout_batch_id": STRING, "observation": OBS, "action": ACTION,
    "behavior_log_probability": {"type": "number"}, "value_estimate": {"type": "number"},
    "next_value_estimate": {"type": "number"}, "reward": {"type": "number"},
    "terminated": {"type": "boolean"}, "truncated": {"type": "boolean"}, "on_policy": {"const": True},
    "mask_version": STRING, "reward_version": STRING})}
