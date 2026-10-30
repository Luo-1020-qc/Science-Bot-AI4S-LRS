"""Read-only annotation review plus isolated mock counterexamples; no import/training.

Run from the project root using the existing venv and a fresh --output directory.
The original inbox, training tasks and code are hashed before and after. The
trusted v2 environment writes new audit sessions only into its normal sandbox.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
BASE = PROJECT/"Training_Data/v2"
INBOX = HERE.parent/"inbox"
sys.path.insert(0, str(BASE))
from protocol import ACTION_IDS, digest, rows, validate_observation
import expert_import
from environment import ToolEnvironment, reference_action


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def hashes():
    files = list(INBOX.glob("*"))+[BASE/name for name in (
        "protocol.py", "environment.py", "expert_import.py", "expert/pending_decisions.jsonl",
        "tasks/train.jsonl", "tool_runtime/core.py", "tool_runtime/catalog.py",
        "tool_runtime/doe_adapter.py", "tool_runtime/source_manifest.json")]
    return {p.relative_to(PROJECT).as_posix(): sha(p) for p in files if p.is_file()}


def dry_import(records):
    """Exercise the official record validator with its output writer captured in RAM.

    This deliberately does not invoke the CLI or create an approved extension.
    The original CLI also requires its selected input to be inside v2.
    """
    original, captured = expert_import.write, []
    expert_import.write = lambda *args, **kwargs: captured.append(args[1])
    try:
        result = expert_import.import_decisions(deepcopy(records), BASE/"expert/imports/NOT_WRITTEN.json")
        return {"record_validator_passed": True, "records": result["accepted_reviewed_decisions"],
                "filesystem_import_performed": False, "captured_in_memory": len(captured)}
    except (ValueError, KeyError, TypeError) as exc:
        return {"record_validator_passed": False, "error": str(exc), "filesystem_import_performed": False}
    finally:
        expert_import.write = original


def replay(row, tasks, run, action):
    env = ToolEnvironment(tasks[row["task_id"]], run_id=run)
    observation, _ = env.reset()
    for _ in range(row["observation"]["turn"]):
        observation, _, terminal, truncated, _ = env.step(reference_action(observation))
        if terminal or truncated:
            raise ValueError("Replay ended before the reviewed state")
    reproduced = digest(observation) == row["observation_hash"]
    if not reproduced:
        raise ValueError("Replay differs from the original reviewed observation")
    candidate = observation["candidates"][ACTION_IDS.index(action)]
    after, reward, terminal, truncated, info = env.step(ACTION_IDS.index(action))
    return {"exact_observation_reproduced": reproduced, "task_id": row["task_id"],
        "action": action, "candidate_available": candidate["available"],
        "error": info["feedback"]["error"], "result": info["feedback"]["result"],
        "reward": reward, "classification": info["classification"],
        "freeze_before": "freeze" in observation["artifact_refs"],
        "freeze_after": "freeze" in after["artifact_refs"],
        "plan_changed": observation["artifact_refs"]["plan"] != after["artifact_refs"]["plan"],
        "model_after": after["current_contract"]["analysis"]["model"],
        "budget_after": after["current_contract"]["resources"]["budget"],
        "audit_session": env.library.store.folder.relative_to(PROJECT).as_posix(),
        "real_execution": info["feedback"]["real_execution"]}


def audit(output):
    if output.exists():
        raise ValueError("Audit output must be a fresh directory")
    before = hashes()
    pending = rows(BASE/"expert/pending_decisions.jsonl")
    lookup = {r["review_id"]: r for r in pending}
    ordinal = {r["review_id"]: i for i, r in enumerate(pending)}
    tasks = {t["task_id"]: t for t in rows(BASE/"tasks/train.jsonl")}
    batches, combined, locations, corrupt, changed, observation_errors = [], [], {}, [], [], []
    for path in sorted(INBOX.glob("*_decisions.jsonl")):
        records = rows(path)
        batches.append({"file": path.name, "records": len(records), "sha256": sha(path),
            "statuses": dict(Counter(r["review"]["status"] for r in records)),
            "official_in_memory_validation": dry_import(records)})
        for line, row in enumerate(records, 1):
            combined.append(row)
            source_index = ordinal.get(row["review_id"])
            locations[row["review_id"]] = {"file": path.name, "line": line, "source_index": source_index}
            if source_index is None or {k: v for k, v in row.items() if k != "review"} != {
                    k: v for k, v in lookup[row["review_id"]].items() if k != "review"}:
                changed.append(locations[row["review_id"]])
            try:
                validate_observation(row["observation"])
                if digest(row["observation"]) != row["observation_hash"]:
                    raise ValueError("Observation hash differs")
            except (ValueError, KeyError, TypeError) as exc:
                observation_errors.append({**locations[row["review_id"]], "error": str(exc)})
            reason = row["review"]["reason"]
            cjk = sum("\u4e00" <= c <= "\u9fff" for c in reason)
            if reason.count("?") > 10 and cjk == 0:
                corrupt.append({**locations[row["review_id"]], "literal_question_marks": reason.count("?"),
                    "cjk_characters": cjk, "ascii_escaped_prefix": reason[:65].encode("unicode_escape").decode()})
    ordered = sorted(combined, key=lambda r: ordinal[r["review_id"]])
    good = Counter(a for r in combined for a in r["review"]["acceptable_action_ids"])
    bad = Counter(a for r in combined for a in r["review"]["rejected_action_ids"])
    extras = [ordinal[r["review_id"]] for r in combined if len(set(r["review"]["acceptable_action_ids"])-{"read_plan"}) > 1]
    prefix = "annotation_audit_"+uuid.uuid4().hex[:10]
    probes = []
    for source_index, action in ((22, "review"), (24, "repair_budget"),
                                 (5, "repair_response"), (9, "repair_budget"),
                                 (17, "model_blocked_full_factorial")):
        row = next(r for r in ordered if ordinal[r["review_id"]] == source_index)
        probes.append({"source_index": source_index, **replay(row, tasks, prefix+"_"+str(source_index), action)})
    # Counterexample to scoring only membership in acceptable_action_ids.
    env = ToolEnvironment(tasks[ordered[0]["task_id"]], run_id=prefix+"_always_read")
    observation, _ = env.reset()
    total_reward, steps, errors = 0, 0, 0
    while True:
        observation, reward, terminal, truncated, info = env.step(ACTION_IDS.index("read_plan"))
        steps += 1
        total_reward += reward
        errors += info["feedback"]["error"] is not None
        if terminal or truncated:
            break
    constant = {"action": "read_plan", "annotation_membership_score": good["read_plan"]/len(combined),
        "replayed_task": ordered[0]["task_id"], "steps": steps, "success": info["success"],
        "classification": info["classification"], "errors": errors, "reward": total_reward,
        "scope": "One full-episode counterexample, not a trained-policy evaluation",
        "audit_session": env.library.store.folder.relative_to(PROJECT).as_posix()}
    frozen = [r for r in ordered if "freeze" in r["observation"]["artifact_refs"]]
    budget = []
    for row in ordered:
        obs = row["observation"]
        if obs["goal"]["resource_budget"] != obs["current_contract"]["resources"]["budget"]:
            c = obs["current_contract"]
            budget.append({"source_index": ordinal[row["review_id"]], "task_id": row["task_id"],
                "contract_budget": c["resources"]["budget"], "user_budget": obs["goal"]["resource_budget"],
                "planned_cost": len(c["run_plan"])*c["resources"]["per_run"]})
    result = {"version": "expert_batch_review_2026_10_30_v1", "checked_utc": datetime.now(timezone.utc).isoformat(),
        "batches": batches, "combined_records": len(combined), "unique_review_ids": len({r["review_id"] for r in combined}),
        "pending_source_records": len(pending), "pending_source_sha256": sha(BASE/"expert/pending_decisions.jsonl"),
        "uncovered_source_records": sorted(set(lookup)-{r["review_id"] for r in combined}),
        "non_review_changes": changed, "observation_errors": observation_errors,
        "policy_splits": dict(Counter(r["policy_split"] for r in combined)),
        "tasks": sorted({r["task_id"] for r in combined}),
        "source_kinds": dict(Counter(tasks[t]["data_lineage"]["source_kind"] for t in {r["task_id"] for r in combined})),
        "acceptable_counts": dict(good), "rejected_counts": dict(bad),
        "reviewers_as_declared": sorted({r["review"]["reviewer"] for r in combined}),
        "reviewer_identity_verified": False,
        "corrupted_rationales": corrupt, "non_read_multisolution_source_indices": sorted(extras),
        "all_original_script_actions_accepted": all(r["observation"]["candidates"][r["proposed_action_index"]]["action_id"] in r["review"]["acceptable_action_ids"] for r in combined),
        "frozen_states": len(frozen), "frozen_states_with_current_patch_hash": sum(
            next(c for c in r["observation"]["candidates"] if c["action_id"] == "repair_budget")["arguments"]["expected_contract_hash"] == digest(r["observation"]["current_contract"]) for r in frozen),
        "budget_mismatches": budget, "action_probes": probes, "constant_read_counterexample": constant,
        "formal_import": False, "training_started": False, "real_scientific_executions": 0,
        "model_api_calls": 0, "source_sha256_before": before,
        "input_cli_location_supported": INBOX.resolve().is_relative_to(BASE.resolve()),
        "verdict": "Structurally compatible review candidates; correct text corruption and execution-semantic labels before BC. Not a multi-turn clarification or PPO dataset."}
    if hashes() != before:
        raise ValueError("Source data or trusted implementation changed during audit")
    result["sources_unchanged"] = True
    result["audit_script_sha256"] = sha(Path(__file__))
    output.mkdir(parents=True, exist_ok=False)
    write(output/"audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.output)
    print(json.dumps({k: result[k] for k in ("combined_records", "unique_review_ids", "sources_unchanged",
        "non_read_multisolution_source_indices", "frozen_states", "frozen_states_with_current_patch_hash",
        "constant_read_counterexample", "formal_import", "training_started")}, ensure_ascii=False, indent=2))
    print("Action probes:", json.dumps([{k: p[k] for k in ("source_index", "action", "exact_observation_reproduced", "error", "freeze_after")} for p in result["action_probes"]], ensure_ascii=False))
