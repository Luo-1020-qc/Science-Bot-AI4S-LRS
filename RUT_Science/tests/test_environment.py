import copy
import unittest

from rut_science.benchmark import build_tasks
from rut_science.environment import ScientificMLEnvironment
from rut_science.validation import replay_oracle


class EnvironmentTests(unittest.TestCase):
    def test_failed_calls_are_atomic(self):
        env = ScientificMLEnvironment()
        before = env.snapshot()
        for name, args in [
            ("inspect_dataset", {"dataset_name": "absent"}),
            ("train_model", {"split_id": "invented", "model": "linear"}),
            ("edit_test_labels", {"dataset_id": "ds_1"}),
            ("instant-perfect-model", {}),
            ("split_dataset", {"dataset_id": "ds_1", "target": "conductivity", "train_fraction": float("nan"), "seed": 0}),
        ]:
            with self.subTest(name=name):
                self.assertEqual(env.invoke(name, args)["status"], "error")
                self.assertEqual(env.snapshot(), before)

    def test_entity_specific_precondition(self):
        env = ScientificMLEnvironment()
        env.invoke("inspect_dataset", {"dataset_name": "Materials-A"})
        result = env.invoke("validate_dataset", {"dataset_id": "ds_2", "target": "modulus"})
        self.assertEqual(result["error_code"], "precondition_failed")

    def test_sealed_score_not_exposed_and_no_repeated_test(self):
        replay = replay_oracle(build_tasks()[0])
        evaluation_event = replay["events"][-2]
        output = evaluation_event["tool_result"]
        self.assertTrue(output["sealed"])
        self.assertNotIn("value", output)
        self.assertNotIn("predictions", output)
        env = ScientificMLEnvironment(replay["final_state"])
        before = env.snapshot()
        result = env.invoke("evaluate_model", evaluation_event["arguments"])
        self.assertEqual(result["error_code"], "budget_exhausted")
        self.assertEqual(env.snapshot(), before)
        model_event = replay["events"][3]
        self.assertEqual(env.invoke("train_model", model_event["arguments"])["error_code"], "sealed_test_locked")

    def test_train_uses_only_training_rows(self):
        final = replay_oracle(build_tasks()[0])["final_state"]
        model = next(iter(final["models"].values()))
        split = final["splits"][model["split_id"]]
        self.assertEqual(set(model["fit_row_ids"]), set(split["train_ids"]))
        self.assertFalse(set(model["fit_row_ids"]) & set(split["test_ids"]))

    def test_snapshots_are_copies_and_reset_reproducible(self):
        env = ScientificMLEnvironment()
        initial = env.snapshot()
        changed = copy.deepcopy(initial)
        changed["datasets"].clear()
        self.assertEqual(env.snapshot(), initial)
        env.invoke("inspect_dataset", {"dataset_name": "Materials-A"})
        env.reset(initial)
        self.assertEqual(env.snapshot(), initial)
        task = build_tasks()[0]
        self.assertEqual(replay_oracle(task)["final_state"], replay_oracle(task)["final_state"])
