from copy import deepcopy
import json
import unittest

from lab.cvit_mock import CViTMockEnvironment, CViTRule, CV_ACTIONS
from lab.suite_tasks import cvit_task
from lab.guard import LAB


class CViTMockTests(unittest.TestCase):
    def env(self, scenario="pilot_run", complete=True):
        task = cvit_task(scenario, "train", 1, 200)
        if complete:
            task["initial"] = deepcopy(task["hidden"]["facts"])
        env = CViTMockEnvironment(task)
        env.reset()
        return env

    def finish(self, env):
        obs = env.observe()
        actions = []
        while not env.done:
            action = CViTRule().choose(obs)
            self.assertTrue(obs["mask"][CV_ACTIONS.index(action)], action)
            obs, _, _, info = env.step(action)
            actions.append(action)
        return info, actions

    def test_unconfirmed_launch_is_blocked(self):
        env = self.env()
        env.step("cvit:launch_mock")
        self.assertEqual(env.state["launches"], 0)
        self.assertEqual(env.state["blocked_launches"], 1)

    def test_wrong_configuration_is_not_silently_substituted(self):
        env = self.env()
        env.step("cvit:inspect"); env.step("cvit:choose:full")
        self.assertIn("configuration_not_user_requested", env.validate())
        env.step("cvit:draft")
        self.assertIsNone(env.state["draft"])

    def test_rule_stops_for_insufficient_budget_memory_unknown_or_unsupported(self):
        for case in ("insufficient_budget", "memory_low", "unknown_dataset", "unsupported_target"):
            env = self.env(case, complete=False)
            info, _ = self.finish(env)
            with self.subTest(case=case):
                self.assertTrue(info["success"])
                self.assertEqual(env.state["launches"], 0)

    def test_new_mock_job_has_exactly_one_launch_and_no_numeric_metric(self):
        env = self.env()
        info, actions = self.finish(env)
        self.assertTrue(info["success"])
        self.assertEqual(actions.count("cvit:launch_mock"), 1)
        self.assertIsNone(info["metric"])
        self.assertEqual(info["real_gpu_jobs"], 0)

    def test_existing_running_job_is_reconciled_and_not_launched_again(self):
        env = self.env("existing_running")
        info, actions = self.finish(env)
        self.assertTrue(info["success"])
        self.assertIn("cvit:reconcile", actions)
        self.assertNotIn("cvit:launch_mock", actions)
        self.assertEqual(env.state["launches"], 0)

    def test_completed_job_is_reused_and_mismatched_job_is_not_reused(self):
        for scenario in ("existing_completed", "job_mismatch"):
            env = self.env(scenario)
            info, _ = self.finish(env)
            self.assertTrue(info["success"])
            self.assertEqual(env.state["launches"], 0)

    def test_confirmed_data_change_invalidates_confirmation_and_requires_new_draft(self):
        env = self.env("data_change")
        env.step("cvit:inspect"); env.step("cvit:choose:pilot"); env.step("cvit:draft")
        old = env.state["draft"]
        env.step("cvit:confirm")
        self.assertIsNone(env.state["confirmation"])
        self.assertIsNone(env.state["draft"])
        self.assertNotEqual(env.identity(), old)
        info, _ = self.finish(env)
        self.assertTrue(info["success"])
        self.assertEqual(env.state["launches"], 1)

    def test_oom_stops_without_repeated_launch(self):
        env = self.env("job_oom")
        info, actions = self.finish(env)
        self.assertTrue(info["success"])
        self.assertEqual(actions.count("cvit:launch_mock"), 1)
        self.assertEqual(env.state["last_failure"], "mock_oom")

    def test_denied_confirmation_and_read_only_questions_never_launch(self):
        for scenario in ("confirmation_denied", "explain_only", "denied_read", "full_confirmation_revoked"):
            env = self.env(scenario)
            info, _ = self.finish(env)
            self.assertTrue(info["success"])
            self.assertEqual(env.state["launches"], 0)

    def test_pause_restore_reconciles_job_without_new_launch(self):
        env = self.env("existing_running")
        obs = env.observe()
        while not env.state["reconciled"]:
            obs, _, _, _ = env.step(CViTRule().choose(obs))
        saved = json.loads(json.dumps(env.snapshot()))
        restored = CViTMockEnvironment.restore(saved)
        info, _ = self.finish(restored)
        self.assertTrue(info["success"])
        self.assertEqual(restored.state["launches"], 0)

    def test_hidden_task_data_never_enter_public_observation(self):
        env = self.env(complete=False)
        obs = env.observe()
        self.assertNotIn("hidden", obs)
        self.assertNotIn("existing_job", obs)
        self.assertEqual(obs["job"], "not_queried")

    def test_duplicate_launch_is_blocked_even_before_poll(self):
        env = self.env()
        obs = env.observe()
        while not env.state["launches"]:
            obs, _, _, _ = env.step(CViTRule().choose(obs))
        env.step("cvit:launch_mock")
        self.assertEqual(env.state["launches"], 1)
        self.assertEqual(env.state["blocked_launches"], 1)
