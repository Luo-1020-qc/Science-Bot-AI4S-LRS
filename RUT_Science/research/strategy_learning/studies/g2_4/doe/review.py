"""Training-only DOE calibration review; never fabricates expert approvals."""
from datetime import datetime
from .guard import LAB, local
from .io import digest, rows, sha, write, write_rows
from .tasks import load_split, public_observation

REVIEW_KEYS = {"status", "verdict", "blocking_codes", "reviewer", "rationale", "reviewed_at"}
RECORD_KEYS = {"schema_version", "decision_id", "source_ref", "source_sha256", "source_row", "task_id",
               "split", "observation", "observation_hash", "reference_source", "review"}


def queue_records():
    source = LAB/"bank/train.jsonl"
    tasks = load_split("train", purpose="review")
    checksum, selected, result = sha(source), set(), []
    for index, task in enumerate(tasks):
        key = (task["family"], task["scenario"])
        if key in selected:
            continue
        selected.add(key)
        observation = public_observation(task)
        result.append({"schema_version": "doe_review_v1", "decision_id": digest([checksum, index, digest(observation)]),
            "source_ref": "bank/train.jsonl", "source_sha256": checksum, "source_row": index, "task_id": task["task_id"],
            "split": "train", "observation": observation, "observation_hash": digest(observation),
            "reference_source": "synthetic_protocol_case_awaiting_independent_review",
            "review": {"status": "pending", "verdict": None, "blocking_codes": [], "reviewer": None, "rationale": None, "reviewed_at": None}})
    return result


def export_queue(output=None):
    target = local(output or LAB/"review/pending.jsonl")
    records = queue_records()
    write_rows(target, records, fresh=True)
    return {"pending": len(records), "human_expert_approvals_created": 0}


def validate_reviews(records):
    if type(records) is not list or not 1 <= len(records) <= 500:
        raise ValueError("Provide 1..500 approved training reviews")
    expected = {row["decision_id"]: row for row in queue_records()}
    seen, accepted = set(), []
    for record in records:
        if type(record) is not dict or set(record) != RECORD_KEYS or record["decision_id"] not in expected or record["decision_id"] in seen:
            raise ValueError("Unknown, duplicate, open-schema or non-training review")
        seen.add(record["decision_id"])
        original = expected[record["decision_id"]]
        if {key: value for key, value in record.items() if key != "review"} != {key: value for key, value in original.items() if key != "review"}:
            raise ValueError("Review context, immutable train source or observation changed")
        review = record["review"]
        if type(review) is not dict or set(review) != REVIEW_KEYS or review["status"] != "approved" or review["verdict"] not in {"acceptable", "reject", "needs_information"}:
            raise ValueError("Only explicit approved structured reviews can be imported")
        for field in ("reviewer", "rationale", "reviewed_at"):
            if type(review[field]) is not str or not review[field].strip() or len(review[field]) > 4000:
                raise ValueError("Review requires identity, rationale and timestamp")
        if datetime.fromisoformat(review["reviewed_at"]).tzinfo is None:
            raise ValueError("Review timestamp must include timezone")
        codes = review["blocking_codes"]
        if type(codes) is not list or len(codes) > 30 or any(type(code) is not str or not code.strip() for code in codes):
            raise ValueError("Invalid expert issue codes")
        if (review["verdict"] == "acceptable" and codes) or (review["verdict"] != "acceptable" and not codes):
            raise ValueError("Verdict and blocking issues disagree")
        accepted.append({**record, "identity_status": "externally_claimed_not_independently_verified"})
    return accepted


def import_reviews(source, output=None):
    source = local(source)
    target = local(output or LAB/"review/imported_labels.json")
    if target.exists():
        raise ValueError("Never replace an existing imported review set")
    accepted = validate_reviews(rows(source))
    write(target, {"schema_version": "doe_reviewed_labels_v1", "input_ref": source.relative_to(LAB).as_posix(),
        "input_sha256": sha(source), "records": accepted, "records_hash": digest(accepted),
        "expert_identity_independently_verified": False, "automatic_training": False, "live_policy_promotion": False}, fresh=True)
    return {"imported_claimed_reviews": len(accepted), "automatic_training": False, "expert_identity_independently_verified": False}


def load_reviews(path):
    from .io import read
    value = read(local(path))
    source = local(LAB/value["input_ref"])
    if (value["schema_version"] != "doe_reviewed_labels_v1" or sha(source) != value["input_sha256"] or
            digest(value["records"]) != value["records_hash"] or value["automatic_training"] is not False or value["live_policy_promotion"] is not False):
        raise ValueError("Imported label set changed or attempts promotion")
    if validate_reviews(rows(source)) != value["records"]:
        raise ValueError("Imported labels no longer match original reviewed context")
    return value["records"]
