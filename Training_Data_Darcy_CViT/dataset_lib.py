"""Typed illustrative Harness data; local JSON only, no Agent/tool imports."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "harness_examples_v1"
ACTIONS = ("ask", "inspect_mock", "propose_design", "check_design_mock", "revise_design",
           "reconcile_job_mock", "resume_job_mock", "stop_with_evidence", "submit_for_review")
OBSERVATION_KEYS = {"user_messages", "facts", "unknown", "evidence", "draft", "permissions", "budget", "job", "history", "action_mask"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def read_json(path):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value
    def invalid(_):
        raise ValueError("Nonfinite JSON")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=invalid)


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def save(relative, value, *, jsonl=False):
    path = ROOT/relative
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError("Output must stay in the dedicated data folder")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(canonical(row)+"\n" for row in value) if jsonl else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
    path.write_text(content, encoding="utf-8")


def check_observation(obs):
    if type(obs) is not dict or set(obs) != OBSERVATION_KEYS:
        raise ValueError("Public observation contains missing fields or evaluator metadata")
    mask = obs["action_mask"]
    if type(mask) is not dict or set(mask) != set(ACTIONS) or any(type(v) is not bool for v in mask.values()):
        raise ValueError("Invalid host-permission mask")
    if obs["permissions"] != {"inspect_mock": True, "design": True, "run_mock_job": True, "real_execution": False}:
        raise ValueError("No real execution permission in illustrative data")
    ids = [item["id"] for item in obs["evidence"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate public evidence ids")
    canonical(obs)


def grade(obs, action, feedback, after, terminated):
    """Documented toy reward, not the G2.4 scientific verifier."""
    if action["name"] not in ACTIONS or not obs["action_mask"].get(action["name"]):
        raise ValueError("Action exceeds host mask")
    if feedback["source"] != "scripted_mock_feedback" or feedback["real_execution"] is not False:
        raise ValueError("Examples only accept mock feedback")
    if action["name"] == "stop_with_evidence":
        certificate = action["arguments"].get("evidence_ids", [])
        available = {row["id"]: row for row in obs["evidence"]}
        if not certificate or any(key not in available for key in certificate):
            raise ValueError("Stop depends on unobserved evidence")
        if any(available[key]["kind"] not in {"user_unavailable", "mock_job_failure", "unsupported_scope"} for key in certificate):
            raise ValueError("Cited evidence does not justify a terminal stop")
    if terminated:
        if action["name"] == "submit_for_review":
            current = obs["draft"]
            accepted = bool(current and any(row["kind"] == "design_check_passed" and row["value"]["draft_hash"] == digest(current)
                                            for row in obs["evidence"]))
            return (10.0 if accepted else -10.0)-.02
        if action["name"] == "stop_with_evidence":
            return 10.0-.02
        raise ValueError("Unsupported example terminal action")
    # First observed answer/fix gets a small reward; invalid candidate costs more.
    new_evidence = len(after["evidence"])-len(obs["evidence"])
    return (-1.0 if feedback["blocking_codes"] else .1 if new_evidence > 0 else 0.0)-.02


def validate_dataset(folder=ROOT):
    folder = Path(folder)
    manifest = read_json(folder/"manifest.json")
    if manifest["schema_version"] != VERSION or manifest["human_expert_labels"] != 0 or manifest["blind_heldout_tasks"] != 0:
        raise ValueError("Invalid provenance or blind-test claim")
    for relative, checksum in manifest["artifact_sha256"].items():
        path = folder/relative
        if not path.resolve().is_relative_to(folder.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError("Artifact identity changed: "+relative)
    partitions, tasks, episodes, labels = {}, {}, [], []
    for split in ("train", "development", "evaluation_example"):
        records = rows(folder/"tasks"/(split+".jsonl"))
        partitions[split] = {row["root_group"] for row in records}
        for task in records:
            if task["task_id"] in tasks or task["policy_split"] != split:
                raise ValueError("Duplicate task or split mismatch")
            tasks[task["task_id"]] = task
            check_observation(task["initial_observation"])
        episodes += rows(folder/"episodes"/(split+".jsonl"))
    names = list(partitions)
    if any(partitions[a]&partitions[b] for i, a in enumerate(names) for b in names[i+1:]):
        raise ValueError("Task source group leakage")
    data_splits = {}
    for task in tasks.values():
        for identity in task["data_lineage"]["underlying_source_ids"]:
            previous = data_splits.setdefault(identity, task["policy_split"])
            if previous != task["policy_split"]:
                raise ValueError("Same underlying scientific data crosses policy splits")
        ml = task["data_lineage"]["within_experiment_partition"]
        if set(ml) != {"train", "validation", "test"} or len(set(ml.values())) != 3:
            raise ValueError("Scientific training/validation/test references overlap")
    seen_episodes = set()
    for episode in episodes:
        task = tasks[episode["task_id"]]
        if episode["episode_id"] in seen_episodes or episode["policy_split"] != task["policy_split"]:
            raise ValueError("Duplicate episode or episode/task split mismatch")
        seen_episodes.add(episode["episode_id"])
        if episode["source"] != "scripted_reference_not_human_expert" or episode["ppo_eligible"] is not False:
            raise ValueError("Reference traces are not on-policy PPO rollouts")
        before = task["initial_observation"]
        for index, step in enumerate(episode["steps"]):
            check_observation(step["observation"]); check_observation(step["next_observation"])
            if step["observation"] != before or step["decision_index"] != index:
                raise ValueError("Broken state chain")
            if step["behavior_log_probability"] is not None or step["value_estimate"] is not None:
                raise ValueError("No invented policy probabilities or critic values")
            expected = grade(step["observation"], step["action"], step["feedback"], step["next_observation"], step["terminated"])
            if not math.isclose(step["reward"], expected, abs_tol=1e-12):
                raise ValueError("Recorded reward differs from declared toy rubric")
            if step["terminated"] != (index == len(episode["steps"])-1) or step["truncated"]:
                raise ValueError("Invalid terminal boundaries")
            if digest(step["observation"]) != step["observation_hash"] or digest(step["next_observation"]) != step["next_observation_hash"]:
                raise ValueError("Step identity mismatch")
            before = step["next_observation"]
        if not episode["steps"] or not episode["steps"][-1]["terminated"]:
            raise ValueError("Incomplete reference episode")
    labels = rows(folder/"labels/bc_train.jsonl")
    episode_by_id = {ep["episode_id"]: ep for ep in episodes}
    for label in labels:
        ep = episode_by_id[label["episode_id"]]
        step = ep["steps"][label["decision_index"]]
        if ep["policy_split"] != "train" or label["observation"] != step["observation"] or label["target_action"] != step["action"]:
            raise ValueError("BC label is not from the matching training decision")
        if not step["reference_action_is_recommended"] or label["expert_review_status"] != "pending":
            raise ValueError("Invalid BC source or fabricated expert review")
    pending = rows(folder/"review/pending.jsonl")
    if any(row["review"] != {"status": "pending", "reviewer": None, "verdict": None, "reason": None, "reviewed_at": None} for row in pending):
        raise ValueError("Example reviewer approval was fabricated")
    return {"passed": True, "tasks": len(tasks), "episodes": len(episodes),
            "steps": sum(len(ep["steps"]) for ep in episodes), "bc_training_decisions": len(labels),
            "policy_task_splits": {name: sum(t["policy_split"] == name for t in tasks.values()) for name in names},
            "pending_reviews": len(pending), "human_expert_labels": 0, "blind_heldout_tasks": 0,
            "real_model_requests": 0, "real_tool_executions": 0, "real_cvit_jobs": 0}
