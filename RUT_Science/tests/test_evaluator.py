import copy
import unittest

from rut_science.benchmark import build_tasks, build_dialogues
from rut_science.contracts import GoldAction
from rut_science.evaluator import evaluate
from rut_science.validation import replay_oracle, validate_benchmark


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.task = build_tasks()[0]
        validate_benchmark([self.task])
        self.dialogue = build_dialogues(self.task)[0]
        self.oracle = replay_oracle(self.task)

    def score(self, episode):
        return evaluate(self.task, self.dialogue, episode)

    def test_oracle_all_three_checks(self):
        score = self.score(self.oracle)
        self.assertTrue(score["execution_success"])
        self.assertTrue(all(score["checks"].values()))

    def test_r1a_claiming_success_without_writes(self):
        episode = copy.deepcopy(self.oracle)
        episode["events"] = [{"event_type": "assistant_message", "content": "报告已完成。", "turn_index": 1}]
        episode["final_state"] = episode["initial_state"]
        score = self.score(episode)
        self.assertFalse(score["execution_success"])
        self.assertEqual(score["primary_failure"], "R1a")
        self.assertIn("unsupported_completion_claim", score["auxiliary_labels"])

    def test_r1b_partial_write(self):
        episode = copy.deepcopy(self.oracle)
        episode["events"] = episode["events"][:3]
        episode["final_state"] = episode["events"][-1]["state_after"]
        self.assertEqual(self.score(episode)["primary_failure"], "R1b")

    def test_r2_early_violation_not_erased_by_recovery(self):
        episode = copy.deepcopy(self.oracle)
        early = copy.deepcopy(episode["events"][3])
        early["tool_result"] = {"status": "error", "error_code": "precondition_failed"}
        episode["events"].insert(0, early)
        score = self.score(episode)
        self.assertTrue(score["checks"]["state_verification"])
        self.assertTrue(score["checks"]["action_coverage"])
        self.assertFalse(score["checks"]["logical_compliance"])
        self.assertEqual(score["primary_failure"], "R2")
        self.assertTrue(score["state_only_success_extension"])

    def test_r3_wrong_model_with_complete_sequence(self):
        wrong = copy.deepcopy(self.task)
        wrong.model = "mean"
        wrong.oracle[3] = GoldAction("train", "train_model", {"split_id": "$split.split_id", "model": "mean"})
        episode = replay_oracle(wrong)
        score = self.score(episode)
        self.assertEqual(score["primary_failure"], "R3")
        self.assertFalse(score["checks"]["protocol_matches"])

    def test_r4_blocked_forbidden_call_still_counts(self):
        episode = copy.deepcopy(self.oracle)
        episode["events"].append({"event_type": "tool_call", "tool_name": "edit_test_labels",
            "arguments": {"dataset_id": "ds_1"}, "tool_result": {"status": "error", "error_code": "permission_denied"}, "turn_index": 1})
        score = self.score(episode)
        self.assertEqual(score["primary_failure"], "R4")
        self.assertTrue(score["checks"]["state_verification"])

    def test_repeated_same_tool_on_wrong_entity_does_not_cover_gold(self):
        episode = copy.deepcopy(self.oracle)
        episode["events"][0]["arguments"] = {"dataset_name": "Materials-B"}
        score = self.score(episode)
        self.assertIn("inspect", score["missing_nodes"])
        self.assertFalse(score["execution_success"])

    def test_tampered_metric_and_leakage_fail_scientific_checks(self):
        for tamper in ("metric", "leakage"):
            episode = copy.deepcopy(self.oracle)
            final = episode["final_state"]
            if tamper == "metric":
                next(iter(final["reports"].values()))["value"] = 0.0
            else:
                model = next(iter(final["models"].values()))
                split = final["splits"][model["split_id"]]
                model["fit_row_ids"] += split["test_ids"]
            with self.subTest(tamper=tamper):
                self.assertFalse(self.score(episode)["execution_success"])

    def test_wrong_arguments_not_rescued_by_correct_terminal_state(self):
        episode = copy.deepcopy(self.oracle)
        episode["events"][2]["arguments"]["seed"] += 1
        score = self.score(episode)
        self.assertTrue(score["checks"]["state_verification"])
        self.assertFalse(score["checks"]["action_coverage"])
        self.assertTrue(score["state_only_success_extension"])

    def test_step_limit_is_failure_even_with_final_artifacts(self):
        episode = copy.deepcopy(self.oracle)
        episode["termination"] = "step_limit"
        self.assertFalse(self.score(episode)["execution_success"])
