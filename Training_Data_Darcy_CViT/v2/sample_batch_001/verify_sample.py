"""Verify batch provenance, real-tool reference rewards, and actual PPO samples."""
import ast
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE.parent))
from protocol import digest, sha, rows, read_tasks, expected_reward, validate_observation, write
from ppo_smoke import verify_rollout
from validate import validate_data


def main():
    manifest = json.loads((HERE/"manifest.json").read_text(encoding="utf-8"))
    for name, checksum in manifest["artifact_sha256"].items():
        if name.endswith(".preflight.json"): continue  # Regenerated when the environment is rechecked.
        if sha(HERE/name) != checksum: raise ValueError("Batch artifact changed: "+name)
    wanted = {t["task_id"] for t in rows(HERE/"tasks.jsonl")}
    tasks = [t for t in read_tasks("train", purpose="ppo", extension=HERE/"tasks_imported.json") if t["task_id"] in wanted]
    if len(tasks) != 3: raise ValueError("Sample extension loading mismatch")
    for episode in rows(HERE/"reference_episodes.jsonl"):
        milestones = set()
        for step in episode["steps"]:
            validate_observation(step["observation"]); validate_observation(step["next_observation"])
            if step["behavior_log_probability"] is not None or step["value_estimate"] is not None:
                raise ValueError("Static reference is pretending to be PPO data")
            if abs(step["reward"]-expected_reward(step, milestones)) > 1e-9: raise ValueError("Reference reward mismatch")
    behavior = json.loads((HERE/"ppo_run_001/behavior_policy.json").read_text(encoding="utf-8"))
    updated = json.loads((HERE/"ppo_run_001/updated_policy.json").read_text(encoding="utf-8"))
    records = rows(HERE/"ppo_run_001/rollout.jsonl")
    verified = verify_rollout(records, behavior, tasks=tasks)
    if {r["task_id"] for r in records} != wanted or any(sum(r["task_id"] == name for r in records) != 32 for name in wanted):
        raise ValueError("The new sample tasks did not all receive their declared policy samples")
    proof = json.loads((HERE/"ppo_run_001/verification.json").read_text(encoding="utf-8"))
    if digest(behavior) != proof["behavior_policy_hash"] or digest(updated) != proof["updated_policy_hash"] or digest(behavior) == digest(updated):
        raise ValueError("Policy snapshot/update mismatch")
    base = validate_data()
    # Write before verifying README's link to this report.
    result = {"passed": True, "tasks": len(tasks), "reference_decisions": manifest["reference_decisions"],
        "bc_scripted_labels": manifest["bc_scripted_labels"], "human_expert_labels": 0, "ppo": verified,
        "parameters_changed": True, "base_v2_dataset_still_valid": base["passed"], "default_policy_promoted": False}
    write(HERE/"verification.json", result)
    links = 0
    for path in HERE.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" not in target and not (path.parent/target.split("#")[0]).exists(): raise ValueError("Broken sample link: "+target)
            links += 1
    for path in HERE.glob("*.py"): ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result["local_links_checked"] = links
    write(HERE/"verification.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__": main()
