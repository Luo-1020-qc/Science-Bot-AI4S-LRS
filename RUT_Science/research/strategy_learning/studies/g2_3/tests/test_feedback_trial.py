import json
import unittest
import torch
import numpy as np
from lab.feedback_trial import FeedbackEnv, TRIAL_CONFIG, update_kl, collect_feedback
from lab.suite_tasks import cvit_task, tabular_task
from lab.ppo import ActorCritic, load_policy, policy_value, setup_seed
from lab.guard import LAB


class CorrectedFeedbackTests(unittest.TestCase):
    def test_unobserved_unknown_fact_is_not_rewarded_for_stopping(self):
        task = cvit_task("pilot_seed_unknown", "unit", 1, 7051)
        env = FeedbackEnv(task)
        env.reset()
        _, reward, done, info = env.step("stop")
        self.assertTrue(done)
        self.assertFalse(info["success"])
        self.assertLess(reward, -4.)

    def test_elicited_unknown_fact_allows_correct_stop(self):
        task = cvit_task("pilot_seed_unknown", "unit", 1, 7051)
        env = FeedbackEnv(task)
        env.reset(); env.step("cvit:ask:seed")
        _, reward, done, info = env.step("stop")
        self.assertTrue(info["success"])
        self.assertGreater(reward, 0.)

    def test_repeated_known_question_is_costly(self):
        task = cvit_task("pilot_run", "unit", 1, 7051)
        env = FeedbackEnv(task)
        env.reset(); env.step("cvit:ask:seed")
        _, reward, _, _ = env.step("cvit:ask:seed")
        self.assertLess(reward, 0.)

    def test_kl_regularized_update_is_finite_and_changes_policy(self):
        setup_seed(12)
        network = ActorCritic()
        reference = load_policy(policy_value(network))
        tasks = [cvit_task("pilot_run", "unit", 1, 7051)]
        # Use a small unit-test batch; formal recorded budgets exclude tests.
        from lab.training_v3 import collect
        batch = collect(network, tasks, 12, 1, 16)
        before = policy_value(network)
        loss = update_kl(network, reference, torch.optim.Adam(network.parameters(), lr=.001), batch)
        self.assertTrue(np.isfinite(loss))
        self.assertNotEqual(policy_value(network)["parameters"], before["parameters"])

    def test_corrective_trial_is_separate_and_selected_without_final_tasks(self):
        path = LAB/"experiments/feedback_v2/selection.json"
        if not path.exists():
            self.skipTest("Corrective trial not selected")
        selection = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(selection["stage"], "selected_before_loading_trial_final")
        self.assertTrue(selection["first_experiment_preserved"])
        self.assertEqual(selection["total_ppo_transitions"], 36864)
