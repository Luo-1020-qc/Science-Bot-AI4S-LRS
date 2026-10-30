"""Executable reference data, real tool parameters and expert extension forms."""
from copy import deepcopy
import json
from protocol import ROOT, VERSION, REWARD_VERSION, ACTION_SPECS, ACTION_IDS, FEATURE_NAMES, CATALOG, digest, sha, write, verify_runtime
from environment import ToolEnvironment, reference_action


def task_for(domain, fault, split, index, *, existing=False, unknown=False, job_failure=None):
    source = "source_"+{"train": "A", "development": "B", "evaluation_example": "C"}[split]
    factors = ([{"name": "predictor", "levels": ["mean_field", "ridge_field"]}] if domain == "darcy" else
        [{"name": "architecture", "levels": ["baseline_small", "candidate_small"]}, {"name": "learning_rate", "levels": ["0.0001", "0.0003"]}])
    return {"schema_version": VERSION, "task_id": f"{domain}_{split}_{index:02d}", "policy_split": split,
        "root_group": "synthetic_darcy_family_"+source,
        "data_lineage": {"source_ancestor_ids": ["synthetic_darcy_"+source], "scientific_partitions": {role: f"mock://{source}/{role}" for role in ("train", "validation", "test")},
                         "source_kind": "synthetic_reference_only"},
        "public": {"domain": domain, "user_request": ("Compare candidate minus baseline relative L2 within the declared Darcy data/experimental-unit protocol; do not claim broad generalization. "
                    + ("Inspect/reuse existing mock job before launching." if existing else "Use mock tools only.")),
            "family": "rcbd_two_arm" if domain == "darcy" else "factorial_2x2", "factors": factors,
            "unit_definition": "One predictor application within an independent data-realization block" if domain == "darcy" else "One independently seeded training run within a data-realization block",
            "response": "relative_l2", "primary_term": factors[0]["name"], "direction": "lower", "practical_margin": .01,
            "minimum_effect": .02, "sigma": None if unknown else .02, "variance_source": None if unknown else "synthetic pilot declaration; not real evidence",
            "target_power": .8, "resource_budget": 256, "max_decisions": 40},
        "simulator": {"initial_fault": fault, "outcome_scenario": ("benefit", "null", "harm")[index % 3],
            "user_variance_answer": None, "existing_job": existing, "job_failure": job_failure},
        "expert_review": {"status": "pending", "reviewer": None, "reason": None, "reviewed_at": None}}


def reference_episode(task):
    env = ToolEnvironment(task)
    obs, _ = env.reset()
    steps = []
    while not env.terminated and not env.truncated:
        action = reference_action(obs)
        candidate = deepcopy(obs["candidates"][action])
        after, reward, terminated, truncated, info = env.step(action)
        steps.append({"decision_index": len(steps), "observation": obs, "observation_hash": digest(obs),
            "features": env.features(obs), "action_mask": [row["available"] for row in obs["candidates"]],
            "action_index": action, "action": candidate, "feedback": info["feedback"], "reward": reward,
            "next_observation": after, "next_observation_hash": digest(after), "next_features": env.features(after),
            "terminated": terminated, "truncated": truncated, "classification": info["classification"],
            "behavior_log_probability": None, "value_estimate": None, "source": "scripted_reference_not_expert"})
        obs = after
    if not info["success"]:
        raise ValueError("Scripted reference failed: "+str([(r["action"]["action_id"], r["feedback"]["error"]) for r in steps]))
    return {"schema_version": VERSION, "episode_id": "reference_"+task["task_id"], "task_id": task["task_id"],
            "policy_split": task["policy_split"], "source": "scripted_reference_not_expert", "ppo_eligible": False,
            "reward_version": REWARD_VERSION, "tool_catalog_hash": env.catalog_hash,
            "classification": info["classification"], "steps": steps, "scientific_claim_verified": False}


def main():
    if (ROOT/"manifest.json").exists():
        raise ValueError("Dataset already sealed; create a new version or validated expert extension")
    verify_runtime()
    train = [task_for("darcy", "wrong_model", "train", 0), task_for("darcy", "wrong_response", "train", 1),
        task_for("darcy", "low_budget", "train", 2), task_for("darcy", "none", "train", 3),
        task_for("cvit", "wrong_model", "train", 4), task_for("cvit", "none", "train", 5, unknown=True),
        task_for("cvit", "stale_review", "train", 6), task_for("cvit", "none", "train", 7, existing=True)]
    dev = [task_for("darcy", "wrong_model", "development", 8), task_for("cvit", "none", "development", 9, job_failure="mock_oom")]
    examples = [task_for("darcy", "wrong_response", "evaluation_example", 10), task_for("cvit", "wrong_model", "evaluation_example", 11)]
    all_episodes, all_tasks, labels = [], [], []
    for split, tasks in (("train", train), ("development", dev), ("evaluation_example", examples)):
        episodes = []
        for task in tasks:
            ep = reference_episode(task)
            episodes.append(ep)
            print(json.dumps({"task": task["task_id"], "decisions": len(ep["steps"]), "classification": ep["classification"]}), flush=True)
        write(ROOT/"tasks"/(split+".jsonl"), tasks, lines=True)
        write(ROOT/"episodes"/(split+".jsonl"), episodes, lines=True)
        all_episodes += episodes; all_tasks += tasks
        if split == "train":
            for ep in episodes:
                for step in ep["steps"]:
                    labels.append({"task_id": ep["task_id"], "episode_id": ep["episode_id"], "decision_index": step["decision_index"],
                        "observation_hash": step["observation_hash"], "features": step["features"], "action_mask": step["action_mask"],
                        "target_action_index": step["action_index"], "target_tool_call": step["action"],
                        "source": "scripted_reference_not_expert", "review_status": "pending"})
    write(ROOT/"labels/bc_reference_train.jsonl", labels, lines=True)
    pending = []
    for ep in all_episodes:
        if ep["policy_split"] != "train": continue
        for step in ep["steps"]:
            if step["decision_index"] % 3: continue
            pending.append({"schema_version": "expert_decision_review_v2", "review_id": digest([ep["episode_id"], step["decision_index"], step["observation_hash"]]),
                "task_id": ep["task_id"], "policy_split": "train", "episode_id": ep["episode_id"], "decision_index": step["decision_index"],
                "observation": step["observation"], "observation_hash": step["observation_hash"], "proposed_action_index": step["action_index"],
                "review": {"status": "pending", "acceptable_action_ids": [], "rejected_action_ids": [], "reason": None, "reviewer": None, "reviewed_at": None}})
    write(ROOT/"expert/pending_decisions.jsonl", pending, lines=True)
    write(ROOT/"expert/task_template.json", deepcopy(train[0]))
    write(ROOT/"expert/decision_review_template.json", pending[0])
    for domain in ("darcy", "cvit"):
        task = next(row for row in train if row["public"]["domain"] == domain)
        episode = next(row for row in all_episodes if row["task_id"] == task["task_id"])
        write(ROOT/"examples"/(domain+"_full_example.json"), {"version": VERSION, "task": task, "episode": episode})
    write(ROOT/"tool_catalog.json", {"version": VERSION, "catalog_hash": digest(CATALOG), "tools": CATALOG,
        "action_candidates": [{"index": i, "action_id": row[0], "tool": row[1]} for i, row in enumerate(ACTION_SPECS)],
        "note": "Candidates are parameterized real offline tools plus two explicit host controls; no disabled tool can be sampled"})
    protected = []
    for folder in ("tasks", "episodes", "labels", "examples", "expert"):
        protected += list((ROOT/folder).glob("*.json*"))
    protected += [ROOT/"tool_catalog.json"]
    write(ROOT/"manifest.json", {"schema_version": VERSION, "date": "2026-10-28", "task_counts": {"train": len(train), "development": len(dev), "evaluation_example": len(examples)},
        "episodes": len(all_episodes), "reference_steps": sum(len(e["steps"]) for e in all_episodes), "bc_reference_labels": len(labels),
        "pending_expert_decisions": len(pending), "human_expert_labels": 0, "blind_heldout_tasks": 0,
        "all_examples_public": True, "shared_synthetic_mechanisms": True, "runtime_tool_catalog_hash": digest(CATALOG),
        "action_ids": list(ACTION_IDS), "feature_names": list(FEATURE_NAMES), "reward_version": REWARD_VERSION,
        "real_model_requests": 0, "real_scientific_executions": 0, "formal_policy_training": False,
        "rl_environment_available": True, "reference_traces_are_ppo_rollouts": False,
        "artifact_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path) for path in protected}})


if __name__ == "__main__": main()
