import json
import unittest
from lab.guard import LAB
from lab.suite_tasks import cvit_task, tabular_task
from lab.adapter_v3 import SuiteEnvironment
from lab.reporting_v3 import stop_evidence, execution_eligible


class ReportingTests(unittest.TestCase):
    def test_hidden_unknown_seed_cannot_justify_unelicited_stop(self):
        task = cvit_task("pilot_seed_unknown", "unit_test", 1, 900)
        env = SuiteEnvironment(task)
        obs = env.reset()
        self.assertFalse(stop_evidence(obs))
        obs, _, _, _ = env.step("cvit:ask:seed")
        self.assertTrue(stop_evidence(obs))

    def test_hidden_future_confirmation_refusal_is_not_public_evidence(self):
        task = cvit_task("full_confirmation_revoked", "unit_test", 1, 900)
        env = SuiteEnvironment(task)
        self.assertFalse(stop_evidence(env.reset()))
        self.assertFalse(execution_eligible(task))

    def test_actual_visible_read_denial_is_a_valid_stop(self):
        task = cvit_task("denied_read", "unit_test", 1, 900)
        env = SuiteEnvironment(task)
        self.assertTrue(stop_evidence(env.reset()))

    def test_oom_and_unknown_facts_are_not_missed_execution_denominator(self):
        for case in ("job_oom", "pilot_seed_unknown", "full_memory_low"):
            with self.subTest(case=case):
                self.assertFalse(execution_eligible(cvit_task(case, "unit_test", 1, 900)))

    def test_selection_freeze_has_not_been_changed_for_reporting_correction(self):
        if not (LAB/"evidence/selection_freeze.json").exists():
            self.skipTest("Selection not completed")
        from lab.evaluation_v3 import check_selection
        self.assertEqual(check_selection()["model_selection"], "development_only")
