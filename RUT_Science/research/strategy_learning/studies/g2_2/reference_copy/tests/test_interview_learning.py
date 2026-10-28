"""Decision masks, hidden-user isolation, training and reproducible artifacts."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from rut_science.util import write_json
from rut_science.science_bot.general.interview.learning import make_tasks, DesignDecisionEnv, demonstrations, train_baseline, evaluate
from rut_science.science_bot.general.interview.policy import RuleInterviewPolicy, BCInterviewPolicy, ACTIONS, FEATURE_NAMES


class InterviewLearningTests(unittest.TestCase):
    def test_observation_does_not_expose_hidden_facts_or_task_identity(self):
        task = make_tasks("train", 2, 10)[1]
        env = DesignDecisionEnv(task)
        obs, _ = env.reset()
        self.assertEqual(set(obs), {"feature_version", "features", "mask", "missing", "blocker_codes"})
        self.assertEqual(len(obs["features"]), len(FEATURE_NAMES))
        serialized = json.dumps(obs)
        for secret in (task["id"], task["truth"]["data_path"], task["truth"]["response"]):
            self.assertNotIn(secret, serialized)

    def test_invalid_execution_like_action_is_terminal_and_never_authorizes_tools(self):
        env = DesignDecisionEnv(make_tasks("train", 1, 7)[0])
        env.reset()
        _, reward, terminated, _, info = env.step("run_shell")
        self.assertTrue(terminated)
        self.assertLess(reward, 0)
        self.assertFalse(info["execution_authorized"])
        with self.assertRaises(ValueError):
            env.step("stop")

    def test_rule_rollouts_complete_or_appropriately_stop_unknown_tasks(self):
        tasks = make_tasks("heldout", 25, 25)
        result = evaluate(RuleInterviewPolicy(), tasks)
        self.assertEqual(result["resolved_or_stopped_rate"], 1)
        self.assertGreater(result["appropriate_stop_rate"], 0)
        self.assertEqual(result["invalid_actions"], 0)

    def test_simulator_rewards_depend_on_facts_not_significance_or_metric(self):
        task = make_tasks("train", 2, 32)[1]
        states = []
        for metric in (.001, .9):
            value = deepcopy(task)
            value["unobserved_p_value"] = metric
            env = DesignDecisionEnv(value)
            obs, _ = env.reset()
            total = 0
            while not env.done:
                obs, reward, _, _, _ = env.step(RuleInterviewPolicy().choose(obs))
                total += reward
            states.append(total)
        self.assertEqual(*states)

    def test_reference_labels_are_explicitly_not_human_experts(self):
        rows = demonstrations(make_tasks("train", 4, 1))
        self.assertTrue(rows)
        self.assertTrue(all(r["label_source"] == "rule_reference_not_human_expert" for r in rows))
        self.assertTrue(all(not r["execution_authorized"] for r in rows))

    def test_small_bc_training_reloads_and_detects_weight_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            result = train_baseline(folder, train_count=30, development_count=12, heldout_count=15, epochs=40)
            policy = BCInterviewPolicy(folder)
            manifest = result["manifest"]
            self.assertFalse(manifest["ppo_trained"])
            self.assertEqual(manifest["heldout_families"], ["paired"])
            tasks = json.loads((Path(folder)/"task_manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("paired", {t["family"] for t in tasks["train"]+tasks["development"]})
            self.assertEqual(result["evaluation"]["heldout"]["bc"]["invalid_actions"], 0)
            value = json.loads((Path(folder)/"policy.json").read_text(encoding="utf-8"))
            value["weights"][0][0] += 1
            write_json(Path(folder)/"policy.json", value)
            with self.assertRaises(ValueError):
                BCInterviewPolicy(folder)


if __name__ == "__main__":
    unittest.main()
