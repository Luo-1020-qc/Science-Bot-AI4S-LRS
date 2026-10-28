"""Offline annotation export/import with source hashes and split quarantine."""
from datetime import datetime
import json
from .contracts import ACTIONS, VERSION, digest, strict_json
from .guard import LAB, ensure_local, file_hash, write_json


def _new_output(path, default):
    path = ensure_local(path or LAB/default)
    if path.exists():
        raise ValueError("Never replace an existing review queue or imported label set")
    return path


def export_queue(source=None, output=None):
    source = ensure_local(source or LAB/"training/reference_train.jsonl")
    output = _new_output(output, "review/pending.jsonl")
    if not source.is_file():
        raise ValueError("Run the benchmark first to generate reference trajectories")
    records = [strict_json(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
    checksum = file_hash(source)
    rows = []
    # A bounded diverse sample, not every near-duplicate training decision.
    selected = {}
    for index, record in enumerate(records):
        key = record["action"]
        if record.get("split") != "train" or selected.get(key, 0) >= 3:
            continue
        selected[key] = selected.get(key, 0)+1
        decision_id = digest([source.relative_to(LAB).as_posix(), checksum, index])
        rows.append({"schema_version": "design_review_v2", "decision_id": decision_id,
                     "source_ref": source.relative_to(LAB).as_posix(), "source_sha256": checksum, "source_row": index,
                     "split": "train", "task_id": record["task_id"], "observation": record["observation"],
                     "observation_sha256": digest(record["observation"]), "proposed_action": record["action"],
                     "reference_source": "synthetic_reference_not_human_expert",
                     "review": {"status": "pending", "correct_action": None, "reviewer": None, "reason": None, "reviewed_at": None}})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")
    return {"exported": len(rows), "output": str(output), "human_labels_created": 0}


def validate_reviews(records):
    if type(records) is not list or not records or len(records) > 5000:
        raise ValueError("Provide 1..5000 reviewed rows")
    seen, sources, accepted = set(), {}, []
    for record in records:
        expected = {"schema_version", "decision_id", "source_ref", "source_sha256", "source_row", "split", "task_id", "observation", "observation_sha256", "proposed_action", "reference_source", "review"}
        if type(record) is not dict or set(record) != expected or record["schema_version"] != "design_review_v2":
            raise ValueError("Unsupported or open review schema")
        if record["split"] != "train" or record["decision_id"] in seen:
            raise ValueError("Reviews must use unique training decisions; development/heldout labels are quarantined")
        seen.add(record["decision_id"])
        source = ensure_local(LAB/record["source_ref"])
        if source.suffix != ".jsonl" or source.resolve() != source or file_hash(source) != record["source_sha256"]:
            raise ValueError("Source trace changed or redirected")
        if str(source) not in sources:
            sources[str(source)] = [strict_json(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
        index = record["source_row"]
        if type(index) is not int or not 0 <= index < len(sources[str(source)]):
            raise ValueError("Invalid source row")
        original = sources[str(source)][index]
        if (original["split"] != "train" or original["task_id"] != record["task_id"]
                or original["observation"] != record["observation"] or original["action"] != record["proposed_action"]
                or record["observation_sha256"] != digest(record["observation"])
                or record["decision_id"] != digest([record["source_ref"], record["source_sha256"], index])):
            raise ValueError("Review does not match immutable source context")
        review = record["review"]
        if type(review) is not dict or set(review) != {"status", "correct_action", "reviewer", "reason", "reviewed_at"}:
            raise ValueError("Invalid reviewer fields")
        if review["status"] != "approved" or review["correct_action"] not in ACTIONS:
            raise ValueError("Unreviewed rows are never imported as expert labels")
        for key in ("reviewer", "reason", "reviewed_at"):
            if type(review[key]) is not str or not review[key].strip() or len(review[key]) > 2000:
                raise ValueError("Approved review requires reviewer, reason and timestamp")
        timestamp = datetime.fromisoformat(review["reviewed_at"])
        if timestamp.tzinfo is None:
            raise ValueError("Review timestamp requires an explicit timezone")
        observation = record["observation"]
        if observation.get("version") != VERSION or not observation["mask"][ACTIONS.index(review["correct_action"])]:
            raise ValueError("Reviewer action exceeds host permissions in original context")
        accepted.append({"decision_id": record["decision_id"], "task_id": record["task_id"], "split": "train",
                         "observation": observation, "action": review["correct_action"], "source_sha256": record["source_sha256"],
                         "review": review, "label_source": "externally_claimed_expert_review_identity_not_independently_verified"})
    return accepted


def import_reviews(source, output=None):
    if source is None:
        raise ValueError("--input must select a reviewed file inside this test folder")
    source = ensure_local(source)
    output = _new_output(output, "review/imported_labels.json")
    records = [strict_json(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
    accepted = validate_reviews(records)
    write_json(output, {"schema_version": "reviewed_label_set_v1", "input_ref": source.relative_to(LAB).as_posix(), "input_sha256": file_hash(source),
                        "records": accepted, "records_sha256": digest(accepted), "deployed": False, "automatic_training": False})
    return {"accepted": len(accepted), "output": str(output), "deployed": False, "automatic_training": False}


def load_reviewed_labels(path):
    path = ensure_local(path)
    value = strict_json(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "reviewed_label_set_v1" or value.get("deployed") is not False:
        raise ValueError("Invalid imported label set")
    original = ensure_local(LAB/value["input_ref"])
    if file_hash(original) != value["input_sha256"] or digest(value["records"]) != value["records_sha256"]:
        raise ValueError("Reviewed source or imported labels changed")
    rechecked = validate_reviews([strict_json(line) for line in original.read_text(encoding="utf-8").splitlines() if line])
    if rechecked != value["records"]:
        raise ValueError("Imported labels no longer match reviewed context")
    return rechecked
