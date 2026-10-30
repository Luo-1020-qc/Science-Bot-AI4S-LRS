"""Validate human-authored extensions and reviewed decisions; never auto-trains."""
from datetime import datetime
import json
from pathlib import Path
from protocol import ROOT, ACTION_IDS, canonical, digest, rows, validate_task, write


def review_metadata(review):
    if review["status"] != "approved": raise ValueError("Only explicitly approved records can enter an approved extension")
    for key in ("reviewer", "reason", "reviewed_at"):
        if type(review[key]) is not str or not review[key].strip(): raise ValueError("Reviewer, rationale and timestamp required")
    if datetime.fromisoformat(review["reviewed_at"]).tzinfo is None: raise ValueError("Explicit timezone required")


def import_tasks(records, output):
    if type(records) is not list or not records or len(records) > 500:
        raise ValueError("Provide 1..500 reviewed task records")
    existing = [task for split in ("train", "development", "evaluation_example") for task in rows(ROOT/"tasks"/(split+".jsonl"))]
    ids = {t["task_id"] for t in existing}
    groups, ancestors = {}, {}
    for task in existing:
        groups[task["root_group"]] = task["policy_split"]
        for source in task["data_lineage"]["source_ancestor_ids"]: ancestors[source] = task["policy_split"]
    for task in records:
        validate_task(task); review_metadata(task["expert_review"])
        if task["task_id"] in ids: raise ValueError("Existing/duplicate task identity; assign a new versioned task id")
        ids.add(task["task_id"])
        if task["policy_split"] != "train": raise ValueError("Expert training extension may not import development/evaluation tasks")
        if task["root_group"] in groups and groups[task["root_group"]] != "train": raise ValueError("Source group crosses a frozen split")
        for source in task["data_lineage"]["source_ancestor_ids"]:
            if source in ancestors and ancestors[source] != "train": raise ValueError("Underlying scientific source crosses policy splits")
            ancestors[source] = "train"
        groups[task["root_group"]] = "train"
    value = {"version": "expert_task_extension_v2", "records": records, "records_hash": digest(records),
        "identity_status": "externally_claimed_expertise_not_independently_verified", "automatic_training": False,
        "must_pass_environment_preflight_before_training": True}
    write(output, value, fresh=True)
    return {"accepted_task_records": len(records), "automatic_training": False, "preflight_required": True}


def import_decisions(records, output):
    if type(records) is not list or not records: raise ValueError("Reviewed decision records required")
    pending = {row["review_id"]: row for row in rows(ROOT/"expert/pending_decisions.jsonl")}
    seen = set()
    for row in records:
        if type(row) is not dict or row.get("review_id") not in pending or row["review_id"] in seen:
            raise ValueError("Unknown/duplicate decision id")
        seen.add(row["review_id"])
        expected = pending[row["review_id"]]
        if {k: v for k, v in row.items() if k != "review"} != {k: v for k, v in expected.items() if k != "review"}:
            raise ValueError("Observation or source decision changed")
        review = row["review"]
        if set(review) != {"status", "acceptable_action_ids", "rejected_action_ids", "reason", "reviewer", "reviewed_at"}:
            raise ValueError("Closed review schema required")
        review_metadata(review)
        good, bad = review["acceptable_action_ids"], review["rejected_action_ids"]
        if type(good) is not list or not good or type(bad) is not list or any(type(x) is not str for x in good+bad):
            raise ValueError("One or more acceptable action ids required; alternative orders are allowed")
        if len(set(good)) != len(good) or len(set(bad)) != len(bad) or set(good)&set(bad) or set(good+bad)-set(ACTION_IDS):
            raise ValueError("Duplicate/conflicting/unregistered action ids")
        available = {r["action_id"] for r in row["observation"]["candidates"] if r["available"]}
        if set(good)-available: raise ValueError("Expert labels cannot grant unavailable host permissions")
    value = {"version": "expert_decision_labels_v2", "records": records, "records_hash": digest(records),
        "identity_status": "externally_claimed_expertise_not_independently_verified", "automatic_training": False}
    write(output, value, fresh=True)
    return {"accepted_reviewed_decisions": len(records), "automatic_training": False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["tasks", "decisions"])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = (args.input if args.input.is_absolute() else ROOT/args.input).absolute()
    target = (args.output if args.output.is_absolute() else ROOT/args.output).absolute()
    if source.resolve() != source or not source.is_relative_to(ROOT): raise ValueError("Select an explicit v2-local JSONL")
    print(json.dumps((import_tasks if args.kind == "tasks" else import_decisions)(rows(source), target), ensure_ascii=False))
