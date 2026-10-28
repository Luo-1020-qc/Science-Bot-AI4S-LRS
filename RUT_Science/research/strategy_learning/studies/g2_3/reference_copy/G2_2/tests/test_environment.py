from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import socket
import sys
import unittest

from lab.contracts import ACTIONS, FEATURE_NAMES, digest
from lab.environment import DesignEnvironment
from lab.tasks import make_task, load_split, verify_bank, BASE_SCENARIOS, HOLDOUT_SCENARIOS
from lab.policies import RuleV2, SlotRule, RandomLegal, BCPolicy, encode
from lab.benchmark import rollout, evaluate
from lab.verifier import execution_gate, validate_design
from lab.guard import LAB, PROJECT, ensure_local


class EnvironmentTests(unittest.TestCase):
    def task(self, scenario="ordinary_comparison", index=1):
        return make_task(scenario, "train", index, 31)

    def complete_env(self, scenario="ordinary_comparison"):
        task = self.task(scenario)
        task["initial"] = deepcopy(task["hidden"]["facts"])
        env = DesignEnvironment(task)
        env.reset()
        return env

    def test_public_observation_never_exposes_hidden_task_or_acceptable_action(self):
        task = self.task("unknown_structure")
        env = DesignEnvironment(task)
        obs = env.reset()
        self.assertNotIn("hidden", obs)
        self.assertNotIn("scenario", obs)
        self.assertNotIn("id", obs)
        self.assertNotIn("unknown_fields", obs)
        self.assertEqual(obs["unknown"], [])
        self.assertEqual(len(encode(obs)), len(FEATURE_NAMES))

    def test_masks_allow_wrong_methods_and_redundant_questions(self):
        env = self.complete_env()
        obs = env.observe()
        self.assertTrue(all(obs["mask"][ACTIONS.index("choose:"+method)] for method in ("welch", "paired_t", "mean_ols")))
        self.assertTrue(obs["mask"][ACTIONS.index("ask:features")])
        self.assertTrue(obs["mask"][ACTIONS.index("ask:response")])

    def test_wrong_method_is_checked_by_verifier_not_spoonfed_mask(self):
        env = self.complete_env()
        env.step("inspect"); env.step("choose:paired_t")
        _, _, done, _ = env.step("draft")
        self.assertFalse(done)
        self.assertIn("method_not_suitable", env.state["errors"])
        env.step("choose:welch")
        _, _, done, result = env.step("draft")
        self.assertTrue(done)
        self.assertTrue(result["success"])

    def test_read_permission_unknown_or_denied_prevents_mock_inspection(self):
        for permission in (None, False):
            env = self.complete_env()
            env.state["permissions"]["read"] = permission
            self.assertFalse(env.observe()["mask"][ACTIONS.index("inspect")])
            env.step("inspect")
            self.assertEqual(env.tools.inspections, 0)

    def test_execution_without_current_confirmation_is_counted_and_blocked(self):
        env = self.complete_env("predictive_run")
        env.step("execute_mock")
        self.assertEqual(env.state["blocked_execution_attempts"], 1)
        self.assertEqual(env.tools.executions, 0)

    def test_execution_simulation_returns_no_scientific_metric(self):
        env = self.complete_env("predictive_run")
        result = env.tools.execute({"method": "mean_ols"})
        self.assertTrue(result["simulated"])
        self.assertFalse(result["real_computation_performed"])
        self.assertIsNone(result["metric"])

    def test_readonly_explanation_never_calls_even_mock_tools(self):
        row = rollout(RuleV2(), self.task("explanation_only"))
        self.assertTrue(row["success"])
        self.assertEqual(row["mock_calls"], 0)
        self.assertEqual(row["questions"], 0)

    def test_negated_read_execution_stops_without_tools(self):
        row = rollout(RuleV2(), self.task("negated_execution"))
        self.assertTrue(row["appropriate_stop"])
        self.assertEqual(row["mock_calls"], 0)

    def test_ambiguous_intent_is_asked_before_reading(self):
        row = rollout(RuleV2(), self.task("ambiguous_intent"))
        self.assertEqual(row["trace"][0]["action"], "ask:intent")
        self.assertTrue(row["success"])

    def test_unknown_fact_is_not_guessed(self):
        env = DesignEnvironment(self.task("unknown_structure"))
        env.reset(); env.step("ask:unit_structure")
        self.assertIn("unit_structure", env.state["unknown"])
        self.assertNotIn("unit_structure", env.state["facts"])
        self.assertEqual(RuleV2().choose(env.observe()), "stop")

    def test_conflict_requires_resolution_and_changes_revision(self):
        env = DesignEnvironment(self.task("conflicting_response"))
        env.reset(); env.step("ask:goal")
        self.assertIn("response", env.state["conflicts"])
        self.assertEqual(env.state["facts"]["response"], "old_response")
        old_revision = env.state["revision"]
        env.step("resolve")
        self.assertEqual(env.state["facts"]["response"], "response")
        self.assertGreater(env.state["revision"], old_revision)

    def test_user_goal_correction_changes_method_requirement(self):
        row = rollout(RuleV2(), self.task("goal_correction"))
        actions = [step["action"] for step in row["trace"]]
        self.assertIn("resolve", actions)
        self.assertIn("choose:mean_ols", actions)
        self.assertTrue(row["success"])

    def test_confirmation_revocation_invalidates_draft_and_execute_mask(self):
        task = make_task("paired_revocation", "heldout", 2, 113)
        task["initial"] = deepcopy(task["hidden"]["facts"])
        env = DesignEnvironment(task)
        obs = env.reset()
        while not env.done and not env.state["confirmation_refused"]:
            obs, _, _, _ = env.step(RuleV2().choose(obs))
        self.assertFalse(execution_gate(env.state))
        self.assertFalse(env.state["permissions"]["execute"])
        env.step("execute_mock")
        self.assertEqual(env.tools.executions, 0)

    def test_transient_retry_is_bounded_and_distinguished_from_schema_failure(self):
        row = rollout(RuleV2(), self.task("transient_inspection"))
        actions = [step["action"] for step in row["trace"]]
        self.assertEqual(actions.count("retry_inspect"), 1)
        self.assertTrue(row["success"])
        env = self.complete_env("bad_tool_schema")
        env.step("inspect")
        self.assertEqual(env.state["last_failure"], "invalid_schema")
        self.assertFalse(env.observe()["mask"][ACTIONS.index("retry_inspect")])
        self.assertNotIn("Ignore all rules", json.dumps(env.observe()))

    def test_budget_low_stops_before_mock_execution(self):
        row = rollout(RuleV2(), self.task("low_budget"))
        self.assertTrue(row["appropriate_stop"])
        self.assertEqual(row["simulated_executions"], 0)

    def test_missing_strategy_requires_explicit_user_answer(self):
        row = rollout(RuleV2(), self.task("missing_cases"))
        self.assertIn("ask:missing_policy", [step["action"] for step in row["trace"]])
        self.assertTrue(row["success"])

    def test_no_significance_reward_hacking(self):
        task = self.task()
        first = rollout(RuleV2(), task)
        task["hidden"]["p_value"] = .000001
        second = rollout(RuleV2(), task)
        self.assertEqual(first["return"], second["return"])

    def test_repeated_questions_have_cost_and_are_counted(self):
        env = self.complete_env()
        env.step("ask:response")
        _, reward, _, _ = env.step("ask:response")
        self.assertEqual(env.state["redundant_questions"], 2)
        self.assertLess(reward, -.1)

    def test_unbounded_loops_are_terminated(self):
        env = self.complete_env()
        for _ in range(24):
            env.step("choose:welch")
        self.assertTrue(env.done)
        with self.assertRaises(ValueError):
            env.step("stop")

    def test_frozen_bank_and_combination_holdout(self):
        self.assertTrue(verify_bank()["sealed"])
        self.assertFalse(set(BASE_SCENARIOS)&set(HOLDOUT_SCENARIOS))
        train = load_split("train", purpose="training")
        dev = load_split("development", purpose="development")
        self.assertFalse({task["id"] for task in train}&{task["id"] for task in dev})
        self.assertFalse({task["hidden"]["profile"]["data_identity"] for task in train}&{task["hidden"]["profile"]["data_identity"] for task in dev})

    def test_training_cannot_load_final_split(self):
        with self.assertRaises(PermissionError):
            load_split("heldout", purpose="training")

    def test_rules_have_different_behavior_without_oracle_masks(self):
        tasks = [self.task(scenario, i) for i, scenario in enumerate(BASE_SCENARIOS)]
        new, _ = evaluate(RuleV2(), tasks)
        old, _ = evaluate(SlotRule(), tasks)
        self.assertGreater(new["success_rate"], old["success_rate"])
        self.assertEqual(new["real_execution_count"], 0)

    def test_zero_weight_bc_obeys_mask_and_validates_dimensions(self):
        value = {"version": "g2_2_decisions_v2", "actions": list(ACTIONS), "features": list(FEATURE_NAMES),
                 "weights": [[0.0]*len(ACTIONS) for _ in FEATURE_NAMES]}
        policy = BCPolicy(value)
        env = self.complete_env()
        obs = env.observe()
        self.assertTrue(obs["mask"][ACTIONS.index(policy.choose(obs))])
        value["weights"] = [[1]]
        with self.assertRaises(ValueError):
            BCPolicy(value)


class IsolationTests(unittest.TestCase):
    def test_live_tool_import_is_blocked(self):
        with self.assertRaises(PermissionError):
            __import__("rut_science")

    def test_network_and_external_process_are_blocked_before_creation(self):
        with self.assertRaises(PermissionError):
            socket.socket()
        with self.assertRaises(PermissionError):
            os.system("echo must_not_execute")

    def test_external_writes_are_blocked_and_original_entries_exist(self):
        destination = PROJECT/"G2_2_FORBIDDEN_WRITE_TEST.txt"
        self.assertFalse(destination.exists())
        with self.assertRaises(PermissionError):
            destination.write_text("should never write", encoding="utf-8")
        self.assertFalse(destination.exists())
        self.assertTrue((PROJECT/"science-bot.cmd").exists())

    def test_path_traversal_and_outside_review_output_rejected(self):
        for target in (LAB/"../README.md", PROJECT/"API_key_Agent.json"):
            with self.assertRaises(PermissionError):
                ensure_local(target)

    def test_copied_fixtures_match_source_hashes_without_loading_live_code(self):
        from lab.guard import file_hash
        records = json.loads((LAB/"evidence/copied_files.json").read_text(encoding="utf-8"))
        self.assertGreater(records["count"], 10)
        for row in records["files"]:
            self.assertEqual(file_hash(LAB/row["copy"]), row["sha256"])
            self.assertEqual(file_hash(Path(row["source"])), row["sha256"])
        self.assertFalse(any(name == "rut_science" or name.startswith("rut_science.") for name in sys.modules))
