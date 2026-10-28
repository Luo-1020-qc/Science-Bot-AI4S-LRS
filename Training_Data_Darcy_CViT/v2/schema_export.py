"""Machine-readable task, expert-review and on-policy transition schemas."""
from protocol import ROOT, VERSION, ACTION_IDS, write


def obj(props): return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
def arr(item, minimum=0): return {"type": "array", "items": item, "minItems": minimum}
S = {"type": "string", "minLength": 1}
N = {"type": "number"}
B = {"type": "boolean"}
H = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
META = {"$schema": "https://json-schema.org/draft/2020-12/schema"}
REVIEW = obj({"status": {"enum": ["pending", "approved", "rejected"]}, "reviewer": {"type": ["string", "null"]},
    "reason": {"type": ["string", "null"]}, "reviewed_at": {"type": ["string", "null"]}})
PUBLIC = obj({"domain": {"enum": ["darcy", "cvit"]}, "user_request": S,
    "family": {"enum": ["crd_two_arm", "rcbd_two_arm", "factorial_2x2"]}, "factors": arr(obj({"name": S, "levels": {"type": "array", "items": S, "minItems": 2, "maxItems": 2}}), 1),
    "unit_definition": S, "response": S, "primary_term": S, "direction": {"enum": ["lower", "higher"]},
    "practical_margin": {"type": "number", "minimum": 0}, "minimum_effect": {"type": "number", "exclusiveMinimum": 0},
    "sigma": {"type": ["number", "null"]}, "variance_source": {"type": ["string", "null"]},
    "target_power": {"type": "number", "minimum": .5, "maximum": .9999}, "resource_budget": {"type": "number", "exclusiveMinimum": 0},
    "max_decisions": {"type": "integer", "minimum": 8, "maximum": 80}})
TASK = {**META, **obj({"schema_version": {"const": VERSION}, "task_id": S, "policy_split": {"enum": ["train", "development", "evaluation_example"]},
    "root_group": S, "data_lineage": obj({"source_ancestor_ids": arr(S, 1), "scientific_partitions": obj({"train": S, "validation": S, "test": S}),
        "source_kind": {"enum": ["synthetic_reference_only", "expert_authored_metadata_no_raw_arrays"]}}),
    "public": PUBLIC, "simulator": obj({"initial_fault": {"enum": ["none", "wrong_model", "wrong_response", "low_budget", "stale_review"]},
        "outcome_scenario": {"enum": ["benefit", "null", "harm"]}, "user_variance_answer": {"type": "null"},
        "existing_job": B, "job_failure": {"enum": [None, "mock_oom"]}}), "expert_review": REVIEW})}
PPO = {**META, **obj({"schema_version": {"const": "ppo_transition_v2"}, "source": {"const": "fresh_on_policy_cpu_smoke"}, "policy_split": {"const": "train"},
    "task_id": S, "task_hash": H, "episode_index": {"type": "integer"}, "sampling_index": {"type": "integer"},
    "environment_version": {"const": VERSION}, "reward_version": S, "tool_catalog_hash": H, "behavior_policy_hash": H,
    "observation": {"type": "object"}, "observation_hash": H, "features": arr(N, 32), "action_mask": arr(B, 23),
    "action_index": {"type": "integer", "minimum": 0, "maximum": len(ACTION_IDS)-1}, "action": {"type": "object"},
    "behavior_log_probability": N, "value_estimate": N, "reward": N, "next_observation": {"type": "object"},
    "next_observation_hash": H, "next_features": arr(N, 32), "next_value_estimate": N,
    "terminated": B, "truncated": B, "classification": S})}


if __name__ == "__main__":
    write(ROOT/"schemas/task.schema.json", TASK)
    write(ROOT/"schemas/ppo_transition.schema.json", PPO)
    write(ROOT/"schemas/review_fields.schema.json", {**META, **REVIEW})
    print("Exported v2 task, PPO transition and review-field schemas")
