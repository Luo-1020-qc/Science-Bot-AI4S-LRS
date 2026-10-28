from copy import deepcopy
import os
from pathlib import Path
import socket
import unittest
from doe.guard import LAB, PROJECT, local
from doe.io import digest, read, rows, write, write_rows
from doe.review import queue_records, validate_reviews, import_reviews, load_reviews
from doe.scoring import score, selection_key
from doe.tasks import base_contract, make_case, public_observation, verify_bank, load_split


def stop(request, reason, evidence_id):
    return {"kind": "stop", "request_hash": digest(request), "reason": reason, "evidence_ids": [evidence_id]}


class ScoringTests(unittest.TestCase):
    def test_train_dev_final_call_identical_verifier_and_reward(self):
        r, c = base_contract()
        outcome = {"kind": "submit", "contract": c}
        values = [score(r, outcome, stage=s) for s in ("train", "development", "heldout")]
        self.assertEqual(values[0], values[1]); self.assertEqual(values[1], values[2])

    def test_always_stop_fails_on_designable_case(self):
        r, _ = base_contract()
        result = score(r, stop(r, "critical_fact_unavailable", "e06"))
        self.assertEqual(result["classification"], "unjustified_stop")
        self.assertLess(result["reward"], 0)

    def test_stop_needs_current_public_unavailable_evidence(self):
        task = make_case("crd_two_arm", "unavailable_fact", "train", 0)
        r = task["request"]
        row = next(row for row in r["evidence"] if row["path"] == "/analysis")
        result = score(r, stop(r, "critical_fact_unavailable", row["id"]))
        self.assertEqual(result["classification"], "correct_stop")

    def test_unanswered_question_cannot_be_treated_as_user_unable_to_answer(self):
        task = make_case("crd_two_arm", "unanswered_fact", "train", 0)
        r = task["request"]
        row = next(row for row in r["evidence"] if row["path"] == "/analysis")
        self.assertFalse(score(r, stop(r, "critical_fact_unavailable", row["id"]))["success"])

    def test_unsupported_scope_requires_its_public_scope_record(self):
        task = make_case("crd_two_arm", "unsupported_scope", "train", 0)
        r = task["request"]
        scope = next(row for row in r["evidence"] if row["path"] == "/family")
        self.assertTrue(score(r, stop(r, "unsupported_design", scope["id"]))["success"])
        self.assertFalse(score(r, stop(r, "unsupported_design", "e00"))["success"])

    def test_hidden_future_facts_cannot_be_added_to_stop_certificate(self):
        r, _ = base_contract()
        outcome = stop(r, "critical_fact_unavailable", "unobserved_future_answer")
        self.assertFalse(score(r, outcome)["success"])
        outcome["hidden_reason"] = "User would refuse later"
        self.assertFalse(score(r, outcome)["success"])

    def test_denied_execution_is_not_reason_to_omit_design_only_task(self):
        r, c = base_contract()
        self.assertEqual(r["execution_permission"], "denied")
        self.assertTrue(score(r, {"kind": "submit", "contract": c})["success"])
        self.assertFalse(score(r, stop(r, "execution_denied", "e00"))["success"])

    def test_decision_cost_cannot_dominate_correct_completion(self):
        r, c = base_contract()
        self.assertGreater(score(r, {"kind": "submit", "contract": c}, decisions=40)["reward"], 9)
        self.assertLess(score(r, stop(r, "unsupported_design", "e00"), decisions=1)["reward"], -9)

    def test_no_execution_or_scientific_claim_can_be_smuggled_into_outcome(self):
        r, c = base_contract()
        result = score(r, {"kind": "submit", "contract": c, "execution_authorized": True})
        self.assertFalse(result["success"])
        self.assertFalse(result["execution_authorized"])
        self.assertIsNone(result["scientific_success"])

    def test_selection_prefers_strict_completion_to_short_unjustified_stop(self):
        r, c = base_contract()
        good = score(r, {"kind": "submit", "contract": c}, decisions=40)
        bad = score(r, stop(r, "unsupported_design", "e00"))
        self.assertGreater(selection_key([good]), selection_key([bad]))

    def test_episode_budget_and_stage_are_closed(self):
        r, c = base_contract()
        for decisions in (0, 41, True):
            with self.assertRaises(ValueError): score(r, {"kind": "submit", "contract": c}, decisions=decisions)
        with self.assertRaises(ValueError): score(r, {"kind": "submit", "contract": c}, stage="test-and-tune")


class ReviewTests(unittest.TestCase):
    def approved_fixture(self):
        record = deepcopy(queue_records()[0])
        record["review"].update(status="approved", verdict="acceptable", reviewer="synthetic-unit-test-reviewer-not-an-expert",
            rationale="Synthetic test of import validation only", reviewed_at="2026-10-27T12:00:00+08:00")
        return record

    def test_pending_queue_does_not_create_approvals_or_leak_reference_answers(self):
        records = queue_records()
        self.assertEqual(len(records), 42)
        self.assertTrue(all(row["review"]["verdict"] is None and row["review"]["status"] == "pending" for row in records))
        for row in records:
            self.assertEqual(set(row["observation"]), {"request", "candidate"})
            self.assertNotIn("expected", row["observation"])

    def test_pending_review_cannot_be_imported(self):
        with self.assertRaises(ValueError): validate_reviews([queue_records()[0]])

    def test_approved_fixture_is_claimed_identity_not_verified_expertise(self):
        imported = validate_reviews([self.approved_fixture()])
        self.assertEqual(imported[0]["identity_status"], "externally_claimed_not_independently_verified")

    def test_context_and_source_tampering_are_rejected(self):
        for field in ("source_sha256", "source_ref", "split", "task_id", "observation_hash"):
            record = self.approved_fixture(); record[field] = "forged"
            with self.subTest(field=field), self.assertRaises(ValueError): validate_reviews([record])
        record = self.approved_fixture(); record["observation"]["candidate"]["revision"] += 1
        with self.assertRaises(ValueError): validate_reviews([record])

    def test_missing_identity_reason_timezone_and_duplicate_reviews_rejected(self):
        for field, value in (("reviewer", ""), ("rationale", ""), ("reviewed_at", "2026-10-27T12:00:00")):
            record = self.approved_fixture(); record["review"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate_reviews([record])
        record = self.approved_fixture()
        with self.assertRaises(ValueError): validate_reviews([record, record])

    def test_review_cannot_grant_tool_permission(self):
        record = self.approved_fixture(); record["review"]["execution_allowed"] = True
        with self.assertRaises(ValueError): validate_reviews([record])

    def test_import_roundtrip_and_tamper_detection_are_study_local(self):
        source = LAB/"current_test_outputs/review.jsonl"
        target = LAB/"current_test_outputs/imported.json"
        if target.exists(): target.unlink()
        write_rows(source, [self.approved_fixture()])
        result = import_reviews(source, target)
        self.assertFalse(result["automatic_training"])
        self.assertEqual(len(load_reviews(target)), 1)
        with self.assertRaises(ValueError): import_reviews(source, target)
        value = read(target); value["records"][0]["review"]["verdict"] = "reject"
        write(target, value)
        with self.assertRaises(ValueError): load_reviews(target)


class IsolationTests(unittest.TestCase):
    def test_live_import_network_process_and_external_write_are_blocked(self):
        with self.assertRaises(PermissionError): __import__("rut_science")
        with self.assertRaises(PermissionError): __import__("dynamic_cvit")
        with self.assertRaises(PermissionError): socket.socket()
        with self.assertRaises(PermissionError): os.system("echo never-run")
        outside = PROJECT/"g24_forbidden_write.txt"
        self.assertFalse(outside.exists())
        with self.assertRaises(PermissionError): outside.write_text("never", encoding="utf-8")
        self.assertFalse(outside.exists())

    def test_path_traversal_and_sibling_writes_rejected(self):
        for path in (LAB/"../outside.json", LAB.parent/"g2_3/evidence/final_evaluation.json", PROJECT/"API_key_Agent.json"):
            with self.assertRaises(PermissionError): local(path)

    def test_split_hashes_and_source_groups_are_sealed(self):
        result = verify_bank()
        self.assertEqual(result["counts"], {"train": 84, "development": 42, "heldout": 42})
        self.assertTrue(result["source_groups_disjoint"])

    def test_heldout_records_and_development_labels_are_not_training_inputs(self):
        for split, purpose in (("heldout", "training"), ("heldout", "development"), ("development", "training"), ("development", "review")):
            with self.assertRaises(PermissionError): load_split(split, purpose=purpose)

    def test_actor_observation_has_no_split_scenario_or_reference_label(self):
        task = make_case("crd_two_arm", "valid", "train", 0)
        observation = public_observation(task)
        self.assertEqual(set(observation), {"request", "candidate"})
        for key in ("split", "scenario", "expected", "root_group", "task_id"):
            self.assertNotIn(key, observation)

    def test_copied_reference_files_are_hash_checked_without_import(self):
        from doe.io import sha
        value = read(LAB/"evidence/copied_files.json")
        self.assertEqual(len(value["files"]), 5)
        self.assertTrue(all(sha(LAB/row["copy"]) == row["sha256"] for row in value["files"]))
