from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from dataset_lib import ROOT, check_observation, digest, grade, rows, read_json, validate_dataset


class TrainingDataTests(unittest.TestCase):
    def test_full_dataset_is_internally_consistent(self):
        result = validate_dataset()
        self.assertEqual(result["tasks"], 12)
        self.assertEqual(result["episodes"], 12)
        self.assertEqual(result["policy_task_splits"], {"train": 8, "development": 2, "evaluation_example": 2})
        self.assertEqual(result["human_expert_labels"], 0)
        self.assertEqual(result["blind_heldout_tasks"], 0)

    def test_darcy_and_cvit_show_different_units_and_designs(self):
        darcy = read_json(ROOT/"examples/darcy_full_example.json")
        cvit = read_json(ROOT/"examples/cvit_full_example.json")
        a = darcy["episode"]["steps"][-1]["observation"]["draft"]
        b = cvit["episode"]["steps"][-1]["observation"]["draft"]
        self.assertEqual(a["design"], "randomized_complete_block_two_arm")
        self.assertEqual(b["design"], "blocked_full_factorial_2x2")
        self.assertIn("architecture:learning_rate", b["analysis_terms"])
        self.assertNotEqual(a["experimental_unit"], b["experimental_unit"])
        self.assertIsNone(a["sample_size_basis"]["achieved_power"])

    def test_actor_observation_excludes_oracle_and_curator_metadata(self):
        observation = deepcopy(rows(ROOT/"tasks/train.jsonl")[0]["initial_observation"])
        for field in ("expected_action", "scenario", "policy_split", "root_group", "hidden"):
            bad = {**observation, field: "oracle"}
            with self.assertRaises(ValueError): check_observation(bad)

    def test_stop_cannot_cite_future_or_irrelevant_evidence(self):
        ep = next(ep for ep in rows(ROOT/"episodes/train.jsonl") if ep["classification"] == "appropriate_scoped_stop")
        step = deepcopy(ep["steps"][-1])
        step["action"]["arguments"]["evidence_ids"] = ["future_answer_not_observed"]
        with self.assertRaises(ValueError): grade(step["observation"], step["action"], step["feedback"], step["next_observation"], True)
        step["action"]["arguments"]["evidence_ids"] = [step["observation"]["evidence"][0]["id"]]
        with self.assertRaises(ValueError): grade(step["observation"], step["action"], step["feedback"], step["next_observation"], True)

    def test_error_proposals_are_preserved_but_excluded_from_bc_targets(self):
        episodes = rows(ROOT/"episodes/train.jsonl")
        negatives = {(ep["episode_id"], s["decision_index"]) for ep in episodes for s in ep["steps"] if not s["reference_action_is_recommended"]}
        self.assertEqual(len(negatives), 4)
        labels = {(r["episode_id"], r["decision_index"]) for r in rows(ROOT/"labels/bc_train.jsonl")}
        self.assertFalse(negatives & labels)
        self.assertEqual(len(rows(ROOT/"labels/preferences_train.jsonl")), 4)

    def test_reference_probabilities_are_null_and_not_ppo_rollouts(self):
        for ep in rows(ROOT/"episodes/train.jsonl"):
            self.assertFalse(ep["ppo_eligible"])
            for step in ep["steps"]:
                self.assertIsNone(step["behavior_log_probability"])
                self.assertIsNone(step["value_estimate"])
        schema = read_json(ROOT/"schemas/ppo_rollout.schema.json")
        self.assertEqual(schema["properties"]["behavior_log_probability"]["type"], "number")

    def test_pending_reviews_are_not_expert_labels(self):
        for record in rows(ROOT/"review/pending.jsonl"):
            self.assertEqual(record["review"]["status"], "pending")
            self.assertIsNone(record["review"]["reviewer"])
            self.assertIsNone(record["review"]["verdict"])

    def test_hash_tamper_fails_before_loading_training_records(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            folder = Path(directory)
            shutil.copy2(ROOT/"manifest.json", folder/"manifest.json")
            with self.assertRaises((ValueError, FileNotFoundError)):
                validate_dataset(folder)

    def test_scientific_source_group_leakage_is_rejected_even_with_updated_file_hash(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            folder = Path(directory)
            manifest = read_json(ROOT/"manifest.json")
            for relative in manifest["artifact_sha256"]:
                target = folder/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT/relative, target)
            source = folder/"tasks/development.jsonl"
            tasks = rows(source)
            tasks[0]["root_group"] = rows(ROOT/"tasks/train.jsonl")[0]["root_group"]
            source.write_text("".join(json.dumps(task)+"\n" for task in tasks), encoding="utf-8")
            manifest["artifact_sha256"]["tasks/development.jsonl"] = hashlib.sha256(source.read_bytes()).hexdigest()
            (folder/"manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source group leakage"):
                validate_dataset(folder)

    def test_mock_completion_and_design_are_never_scientific_results(self):
        for ep in rows(ROOT/"episodes/train.jsonl"):
            self.assertEqual(ep["real_tool_executions"], 0)
            self.assertIsNone(ep["scientific_outcome"])
            for step in ep["steps"]:
                self.assertFalse(step["feedback"]["real_execution"])
                self.assertIsNone(step["feedback"]["scientific_metric"])
