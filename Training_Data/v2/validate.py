"""Validate actual tool trajectories, expert boundaries and fresh on-policy rollouts."""
import argparse
import json
import math
from pathlib import Path
import unittest
from protocol import ROOT, VERSION, ACTION_IDS, digest, sha, rows, read_tasks, validate_observation, expected_reward, verify_runtime, write
from environment import ToolEnvironment


def validate_data():
    manifest = json.loads((ROOT/"manifest.json").read_text(encoding="utf-8"))
    catalog_hash = verify_runtime()
    if manifest["runtime_tool_catalog_hash"] != catalog_hash or manifest["schema_version"] != VERSION:
        raise ValueError("Dataset/tool version mismatch")
    for relative, checksum in manifest["artifact_sha256"].items():
        if sha(ROOT/relative) != checksum: raise ValueError("Sealed dataset file changed: "+relative)
    tasks, groups, ancestors, episodes = {}, {}, {}, []
    for split in ("train", "development", "evaluation_example"):
        for task in read_tasks(split, purpose="verification"):
            if task["task_id"] in tasks: raise ValueError("Duplicate task id")
            tasks[task["task_id"]] = task
            if groups.setdefault(task["root_group"], split) != split: raise ValueError("Task source-group leakage")
            for source in task["data_lineage"]["source_ancestor_ids"]:
                if ancestors.setdefault(source, split) != split: raise ValueError("Underlying scientific source leakage")
        episodes += rows(ROOT/"episodes"/(split+".jsonl"))
    counts = 0
    for episode in episodes:
        task = tasks[episode["task_id"]]
        if episode["policy_split"] != task["policy_split"] or episode["ppo_eligible"] is not False:
            raise ValueError("Reference split or PPO eligibility incorrect")
        previous, milestones = None, set()
        for index, step in enumerate(episode["steps"]):
            obs, after = step["observation"], step["next_observation"]
            validate_observation(obs); validate_observation(after)
            if index != step["decision_index"] or previous is not None and previous != obs:
                raise ValueError("Reference state chain broken")
            if digest(obs) != step["observation_hash"] or digest(after) != step["next_observation_hash"]:
                raise ValueError("Observation hash mismatch")
            if step["features"] != ToolEnvironment.features(None, obs) or step["next_features"] != ToolEnvironment.features(None, after):
                raise ValueError("Feature leakage or public encoder mismatch")
            action = step["action_index"]
            if step["action"] != obs["candidates"][action] or not step["action_mask"][action]: raise ValueError("Reference tool call is not a legal candidate")
            if step["action_mask"] != [row["available"] for row in obs["candidates"]]: raise ValueError("Recorded mask changed")
            if step["behavior_log_probability"] is not None or step["value_estimate"] is not None: raise ValueError("Reference probabilities were fabricated")
            if not math.isclose(step["reward"], expected_reward(step, milestones), abs_tol=1e-9): raise ValueError("Reference reward mismatch")
            if step["terminated"] != (index == len(episode["steps"])-1): raise ValueError("Incorrect terminal boundary")
            previous = after; counts += 1
    labels = rows(ROOT/"labels/bc_reference_train.jsonl")
    by_episode = {ep["episode_id"]: ep for ep in episodes}
    for row in labels:
        ep = by_episode[row["episode_id"]]; step = ep["steps"][row["decision_index"]]
        if ep["policy_split"] != "train" or row["target_action_index"] != step["action_index"] or row["target_tool_call"] != step["action"] or row["review_status"] != "pending":
            raise ValueError("BC reference source or expert status mismatch")
    return {"passed": True, "tasks": len(tasks), "episodes": len(episodes), "reference_decisions": counts,
        "bc_reference_labels": len(labels), "action_candidates": len(ACTION_IDS), "human_expert_labels": 0,
        "task_source_groups_disjoint": True, "scientific_source_ancestors_disjoint": True, "reference_traces_are_ppo_rollouts": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", action="store_true")
    args = parser.parse_args()
    value = validate_data()
    if args.tests:
        with (ROOT/"tests.log").open("w", encoding="utf-8") as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/"tests")))
        value.update(tests=result.testsRun, tests_passed=result.wasSuccessful(), passed=result.wasSuccessful())
    if (ROOT/"ppo_smoke/verification.json").exists():
        from ppo_smoke import verify_rollout
        smoke = json.loads((ROOT/"ppo_smoke/verification.json").read_text(encoding="utf-8"))
        behavior = json.loads((ROOT/"ppo_smoke/behavior_policy.json").read_text(encoding="utf-8"))
        value["ppo_rollout_verification"] = verify_rollout(rows(ROOT/"ppo_smoke/rollout.jsonl"), behavior)
        value["ppo_parameters_changed"] = smoke["parameters_changed"]
    write(ROOT/"verification.json", value)
    print(json.dumps(value, ensure_ascii=False))
    return 0 if value["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
