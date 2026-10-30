from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from protocol import ROOT, ACTION_IDS, digest, rows, read_tasks, validate_task, validate_observation, expected_reward, write
from environment import ToolEnvironment, reference_action
from expert_import import import_tasks, import_decisions
from preflight import preflight
from ppo_smoke import gae, verify_rollout


class RLDataTests(unittest.TestCase):
    def setUp(self):
        self.task = deepcopy(read_tasks("train", purpose="training")[0])

    def env(self, task=None):
        env = ToolEnvironment(task or self.task)
        env.reset()
        return env

    def test_actual_tool_names_and_parameters_follow_pinned_catalog(self):
        obs = self.env().observe()
        validate_observation(obs)
        names = {r["tool"] for r in obs["candidates"]}
        self.assertIn("plan_patch", names); self.assertIn("plan_freeze", names)
        self.assertNotIn("cvit_train_real", names)

    def test_semantically_wrong_model_choices_are_not_hidden_by_mask(self):
        obs = self.env().observe()
        self.assertTrue(all(obs["candidates"][ACTION_IDS.index("model_"+m)]["available"] for m in ("two_arm", "additive_blocks", "full_factorial", "blocked_full_factorial")))

    def test_observation_has_no_task_id_split_or_hidden_mock_outcome(self):
        obs = self.env().observe()
        for key in ("task_id", "simulator", "root_group", "policy_split", "expected_action"):
            with self.subTest(key=key), self.assertRaises(ValueError): validate_observation({**obs, key: "hidden"})
        candidate = obs["candidates"][ACTION_IDS.index("run_mock")]
        self.assertEqual(candidate["arguments"]["scenario"], {"$host": "private_mock_fixture"})

    def test_unobserved_future_unavailability_cannot_reward_stop(self):
        task = next(t for t in read_tasks("train", purpose="training") if t["public"]["sigma"] is None)
        env = self.env(task)
        _, reward, terminated, _, info = env.step(ACTION_IDS.index("stop"))
        self.assertTrue(terminated); self.assertLess(reward, 0)
        self.assertEqual(info["classification"], "unjustified_stop")

    def test_asking_then_observed_unavailable_supports_scoped_stop(self):
        task = next(t for t in read_tasks("train", purpose="training") if t["public"]["sigma"] is None)
        env = self.env(task)
        env.step(ACTION_IDS.index("ask_variance"))
        _, reward, _, _, info = env.step(ACTION_IDS.index("stop"))
        self.assertGreater(reward, 0); self.assertEqual(info["classification"], "justified_stop")

    def test_unknown_variance_cannot_use_template_default_to_pass_review(self):
        task = next(t for t in read_tasks("train", purpose="training") if t["public"]["sigma"] is None)
        env = self.env(task)
        _, reward, terminated, _, info = env.step(ACTION_IDS.index("review"))
        self.assertLess(reward, 0); self.assertFalse(terminated)
        self.assertIn("unresolved", info["feedback"]["error"])

    def test_reference_tool_loop_completes_and_negative_science_does_not_change_success(self):
        from build_dataset import reference_episode
        rewards = []
        for scenario in ("benefit", "harm"):
            task = deepcopy(self.task); task["simulator"]["outcome_scenario"] = scenario
            episode = reference_episode(task)
            self.assertEqual(episode["classification"], "completed_mock_research_loop")
            rewards.append(sum(s["reward"] for s in episode["steps"]))
        self.assertEqual(rewards[0], rewards[1])

    def test_new_episode_reset_does_not_reuse_previous_episode_workspace(self):
        env = self.env(); first = env.library.store.folder
        env.reset()
        self.assertNotEqual(first, env.library.store.folder)

    def test_business_decision_budget_is_terminal_not_external_truncation(self):
        task = deepcopy(self.task); task["public"]["max_decisions"] = 8
        env = self.env(task)
        for _ in range(8): after, _, term, trunc, info = env.step(ACTION_IDS.index("read_plan"))
        self.assertTrue(term); self.assertFalse(trunc)
        self.assertEqual(info["classification"], "decision_budget_exhausted")

    def test_external_truncation_is_distinct(self):
        env = self.env(); env.truncate()
        self.assertFalse(env.terminated); self.assertTrue(env.truncated)
        with self.assertRaises(ValueError): env.step(0)

    def test_gae_bootstraps_truncation_but_not_termination(self):
        a, _ = gae([1], [2], [5], [True], [False])
        b, _ = gae([1], [2], [5], [False], [True])
        self.assertAlmostEqual(a[0], -1)
        self.assertAlmostEqual(b[0], 3.95)
        c, _ = gae([1, 100], [2, 0], [5, 0], [False, True], [True, False])
        self.assertAlmostEqual(c[0], b[0])

    def test_ppo_log_probabilities_recompute_from_real_behavior_snapshot(self):
        records = rows(ROOT/"ppo_smoke/rollout.jsonl")
        policy = json.loads((ROOT/"ppo_smoke/behavior_policy.json").read_text(encoding="utf-8"))
        self.assertTrue(verify_rollout(records, policy)["all_behavior_log_probs_recomputed"])
        altered = deepcopy(records[:1]); altered[0]["behavior_log_probability"] += .1
        with self.assertRaises(ValueError): verify_rollout(altered, policy)

    def test_ppo_rejects_null_or_reference_probabilities(self):
        records = rows(ROOT/"ppo_smoke/rollout.jsonl")[:1]
        policy = json.loads((ROOT/"ppo_smoke/behavior_policy.json").read_text(encoding="utf-8"))
        altered = deepcopy(records); altered[0]["behavior_log_probability"] = None
        with self.assertRaises(ValueError): verify_rollout(altered, policy)

    def test_rollout_rejects_cross_task_join_and_changed_task_hash(self):
        records = rows(ROOT/"ppo_smoke/rollout.jsonl")
        policy = json.loads((ROOT/"ppo_smoke/behavior_policy.json").read_text(encoding="utf-8"))
        altered = deepcopy(records[:1]); altered[0]["task_hash"] = "0"*64
        with self.assertRaises(ValueError): verify_rollout(altered, policy)
        altered = deepcopy(records); altered[1]["episode_index"] += 1
        with self.assertRaises(ValueError): verify_rollout(altered, policy)

    def test_rollout_mask_must_match_observed_host_permissions(self):
        records = rows(ROOT/"ppo_smoke/rollout.jsonl")[:1]
        policy = json.loads((ROOT/"ppo_smoke/behavior_policy.json").read_text(encoding="utf-8"))
        altered = deepcopy(records); altered[0]["action_mask"][0] = not altered[0]["action_mask"][0]
        with self.assertRaises(ValueError): verify_rollout(altered, policy)
        altered = deepcopy(records); altered[0]["source"] = "scripted_reference_not_expert"
        with self.assertRaises(ValueError): verify_rollout(altered, policy)

    def test_hidden_features_and_disabled_action_injection_are_rejected(self):
        records = rows(ROOT/"ppo_smoke/rollout.jsonl")[:1]
        policy = json.loads((ROOT/"ppo_smoke/behavior_policy.json").read_text(encoding="utf-8"))
        altered = deepcopy(records); altered[0]["features"][0] += .5
        with self.assertRaises(ValueError): verify_rollout(altered, policy)
        obs = self.env().observe(); obs["candidates"][0]["tool"] = "cvit_train_real"
        with self.assertRaises(ValueError): validate_observation(obs)

    def test_dev_and_evaluation_examples_cannot_enter_training(self):
        for split in ("development", "evaluation_example"):
            with self.assertRaises(PermissionError): read_tasks(split, purpose="ppo")

    def approved_task(self):
        task = deepcopy(self.task)
        task["task_id"] = "synthetic_unit_test_extension_not_a_human_task"
        task["root_group"] = "unit_test_new_training_group"
        task["data_lineage"]["source_ancestor_ids"] = ["unit_test_new_training_source"]
        task["expert_review"].update(status="approved", reviewer="synthetic-test-fixture-not-an-expert", reason="Importer unit test only", reviewed_at="2026-10-28T15:00:00+08:00")
        return task

    def test_expert_extension_requires_review_and_no_cross_split_ancestors(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            target = Path(tmp)/"extension.json"
            task = self.approved_task(); task["expert_review"]["status"] = "pending"
            with self.assertRaises(ValueError): import_tasks([task], target)
            task = self.approved_task(); task["data_lineage"]["source_ancestor_ids"] = read_tasks("development", purpose="verification")[0]["data_lineage"]["source_ancestor_ids"]
            with self.assertRaises(ValueError): import_tasks([task], target)
            self.assertFalse(target.exists())

    def test_expert_extension_preflight_then_training_loader_roundtrip(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp)/"extension.json"
            result = import_tasks([self.approved_task()], path)
            self.assertFalse(result["automatic_training"])
            with self.assertRaises(FileNotFoundError): read_tasks("train", purpose="ppo", extension=path)
            self.assertTrue(preflight(path)["passed"])
            self.assertEqual(len(read_tasks("train", purpose="ppo", extension=path)), 9)

    def approved_decision(self):
        row = deepcopy(rows(ROOT/"expert/pending_decisions.jsonl")[0])
        candidates = [r["action_id"] for r in row["observation"]["candidates"] if r["available"]]
        row["review"].update(status="approved", acceptable_action_ids=candidates[:2], rejected_action_ids=[],
            reviewer="synthetic-test-fixture-not-expert", reason="Unit test permits alternative valid host actions", reviewed_at="2026-10-28T15:00:00+08:00")
        return row

    def test_expert_multiple_acceptable_actions_validate_without_fabricated_identity(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp)/"labels.json"
            result = import_decisions([self.approved_decision()], path)
            self.assertEqual(result["accepted_reviewed_decisions"], 1)
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("not_independently_verified", value["identity_status"])

    def test_expert_cannot_change_observation_or_grant_missing_permissions(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp)/"labels.json"
            row = self.approved_decision(); row["observation"]["goal"]["sigma"] = 999
            with self.assertRaises(ValueError): import_decisions([row], path)
            row = self.approved_decision(); row["review"]["acceptable_action_ids"] = ["run_mock"]
            with self.assertRaises(ValueError): import_decisions([row], path)
            self.assertFalse(path.exists())

    def test_terminal_completion_reward_and_step_rewards_recompute(self):
        episodes = rows(ROOT/"episodes/train.jsonl")
        for ep in episodes:
            milestones = set()
            for step in ep["steps"]:
                self.assertAlmostEqual(step["reward"], expected_reward(step, milestones))
