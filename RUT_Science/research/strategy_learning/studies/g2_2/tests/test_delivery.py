from copy import deepcopy
import json
import unittest
from lab.guard import LAB, file_hash
from lab.tasks import make_task
from lab.delivery import eligible_for_execution


class ReportingTests(unittest.TestCase):
    def test_declined_confirmation_is_not_counted_as_missed_authorized_execution(self):
        for scenario in ("paired_revocation", "comparison_confirmation_denied", "paired_unknown_source", "missing_read_denied", "temporal_prediction"):
            with self.subTest(scenario=scenario):
                self.assertFalse(eligible_for_execution(make_task(scenario, "heldout", 1, 113)))

    def test_supported_authorized_tasks_are_eligible(self):
        for scenario in ("predictive_run", "paired_conflict", "prediction_transient"):
            with self.subTest(scenario=scenario):
                self.assertTrue(eligible_for_execution(make_task(scenario, "heldout", 1, 113)))

    def test_low_budget_or_unanswerable_tasks_are_not_execution_eligible(self):
        task = make_task("predictive_run", "train", 1, 31)
        task["resource_budget"] = 1
        self.assertFalse(eligible_for_execution(task))
        task["resource_budget"] = 12
        task["hidden"]["unknown_fields"] = ["provenance"]
        self.assertFalse(eligible_for_execution(task))

    def test_frozen_selections_precede_final_evaluation(self):
        if not (LAB/"evidence/freeze.json").exists():
            self.skipTest("Run benchmark to create the frozen selection record")
        from lab.benchmark import verify_freeze
        self.assertTrue(verify_freeze())
        freeze = json.loads((LAB/"evidence/freeze.json").read_text(encoding="utf-8"))
        self.assertEqual(freeze["stage"], "models_selected_before_final_heldout_loading")
        self.assertEqual(freeze["seeds_fixed_in_advance"], [21, 37, 59])

