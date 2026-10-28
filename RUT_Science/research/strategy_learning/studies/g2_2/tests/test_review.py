from copy import deepcopy
import json
from pathlib import Path
import unittest

from lab.guard import LAB, file_hash
from lab.contracts import digest, ACTIONS
from lab.tasks import make_task
from lab.benchmark import reference_rows
from lab.review import validate_reviews, import_reviews, export_queue


class ReviewTests(unittest.TestCase):
    def record(self):
        rows = reference_rows([make_task("ordinary_comparison", "train", 1, 31)])
        source = LAB/"current_test_outputs/review_source.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")
        obs = rows[0]["observation"]
        ref = source.relative_to(LAB).as_posix()
        checksum = file_hash(source)
        return {"schema_version": "design_review_v2", "decision_id": digest([ref, checksum, 0]), "source_ref": ref,
                "source_sha256": checksum, "source_row": 0, "split": "train", "task_id": rows[0]["task_id"],
                "observation": obs, "observation_sha256": digest(obs), "proposed_action": rows[0]["action"],
                "reference_source": "synthetic_reference_not_human_expert",
                "review": {"status": "approved", "correct_action": rows[0]["action"], "reviewer": "synthetic-test-reviewer-not-an-expert",
                           "reason": "Unit-test fixture only; not imported into training", "reviewed_at": "2026-10-26T09:00:00+08:00"}}

    def test_well_formed_review_validates_without_claiming_verified_human_identity(self):
        accepted = validate_reviews([self.record()])
        self.assertEqual(len(accepted), 1)
        self.assertIn("not_independently_verified", accepted[0]["label_source"])

    def test_pending_blank_identity_and_missing_reason_are_rejected(self):
        for field, value in (("status", "pending"), ("reviewer", ""), ("reason", ""), ("reviewed_at", "2026-10-26T09:00:00")):
            record = self.record()
            record["review"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_reviews([record])

    def test_no_development_heldout_or_duplicate_labels(self):
        record = self.record()
        for split in ("development", "heldout"):
            changed = deepcopy(record); changed["split"] = split
            with self.assertRaises(ValueError):
                validate_reviews([changed])
        with self.assertRaises(ValueError):
            validate_reviews([record, record])

    def test_tampered_context_and_source_hash_rejected(self):
        for kind in ("context", "hash"):
            record = self.record()
            if kind == "context":
                record["observation"]["facts"]["response"] = "forged"
                record["observation_sha256"] = digest(record["observation"])
            else:
                record["source_sha256"] = "f"*64
            with self.assertRaises(ValueError):
                validate_reviews([record])

    def test_review_cannot_grant_execution_permission(self):
        record = self.record()
        record["review"]["correct_action"] = "execute_mock"
        with self.assertRaises(ValueError):
            validate_reviews([record])

    def test_atomic_import_failure_creates_no_label_artifact(self):
        record = self.record(); record["review"]["status"] = "pending"
        source = LAB/"current_test_outputs/invalid_review.jsonl"
        source.write_text(json.dumps(record)+"\n", encoding="utf-8")
        destination = LAB/"current_test_outputs/must_not_import.json"
        self.assertFalse(destination.exists())
        with self.assertRaises(ValueError):
            import_reviews(source, destination)
        self.assertFalse(destination.exists())

    def test_reviewed_label_set_roundtrip_and_tamper_detection_stay_in_test_outputs(self):
        from lab.review import load_reviewed_labels
        record = self.record()
        source = LAB/"current_test_outputs/synthetic_approved_fixture.jsonl"
        source.write_text(json.dumps(record)+"\n", encoding="utf-8")
        # Unit-test fixture is never included in reference training or review/pending.
        from lab.guard import write_json
        accepted = validate_reviews([record])
        labelset = LAB/"current_test_outputs/synthetic_import_fixture.json"
        write_json(labelset, {"schema_version": "reviewed_label_set_v1", "input_ref": source.relative_to(LAB).as_posix(),
                            "input_sha256": file_hash(source), "records": accepted, "records_sha256": digest(accepted), "deployed": False})
        self.assertEqual(load_reviewed_labels(labelset), accepted)
        value = json.loads(labelset.read_text(encoding="utf-8"))
        value["records"][0]["action"] = "execute_mock"
        write_json(labelset, value)
        with self.assertRaises(ValueError):
            load_reviewed_labels(labelset)
