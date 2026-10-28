import copy
from dataclasses import replace
import unittest

from rut_science.agents import message
from rut_science.benchmark import build_tasks, build_dialogues
from rut_science.contracts import DialogueSpec
from rut_science.environment import ScientificMLEnvironment, make_initial_state
from rut_science.research_spec import ResearchSpec
from rut_science.runtime import run_episode
from rut_science.util import digest


class ResearchSpecTests(unittest.TestCase):
    def setUp(self):
        self.env = ScientificMLEnvironment()
        self.spec = ResearchSpec.from_task(build_tasks()[0], self.env.snapshot())
        self.env.invoke("inspect_dataset", {"dataset_name": "Materials-A"})
        self.env.invoke("validate_dataset", {"dataset_id": "ds_1", "target": "conductivity"})
        self.split = {"dataset_id": "ds_1", "target": "conductivity", "train_fraction": 0.6, "seed": 11}

    def confirm(self):
        self.env.confirm_research_spec(self.spec, source="operator_config", reference="user:1")

    def test_schema_advertises_exact_models_and_bounds(self):
        schemas = {t["name"]: t["parameters"] for t in self.env.available_tools()}
        self.assertEqual(schemas["train_model"]["properties"]["model"]["enum"], ["linear", "mean"])
        self.assertEqual(schemas["split_dataset"]["properties"]["train_fraction"]["maximum"], 0.7)
        for name, args in [("train_model", {"split_id": "x", "model": "ridge"}),
                           ("split_dataset", {**self.split, "train_fraction": 0.8}),
                           ("split_dataset", {**self.split, "seed": -1}),
                           ("split_dataset", {**self.split, "seed": True}),
                           ("split_dataset", {**self.split, "extra": 1})]:
            before = self.env.snapshot()
            self.assertEqual(self.env.invoke(name, args)["error_code"], "schema_error")
            self.assertEqual(before, self.env.snapshot())

    def test_writes_require_trusted_confirmation_and_model_cannot_confirm(self):
        self.assertEqual(self.env.invoke("split_dataset", self.split)["error_code"], "research_spec_required")
        self.assertEqual(self.env.invoke("confirm_research_spec", self.spec.to_dict())["error_code"], "unknown_tool")
        with self.assertRaises(ValueError):
            self.env.confirm_research_spec(self.spec, source="model", reference="self")

    def test_legal_but_unconfirmed_parameters_rejected_atomically(self):
        self.confirm()
        for args in ({**self.split, "seed": 12}, {**self.split, "train_fraction": 0.65}):
            before = self.env.snapshot()
            self.assertEqual(self.env.invoke("split_dataset", args)["error_code"], "research_spec_mismatch")
            self.assertEqual(self.env.snapshot(), before)
        split_id = self.env.invoke("split_dataset", self.split)["split_id"]
        before = self.env.snapshot()
        self.assertEqual(self.env.invoke("train_model", {"split_id": split_id, "model": "mean"})["error_code"], "research_spec_mismatch")
        self.assertEqual(self.env.snapshot(), before)

    def test_dataset_identity_and_units_are_bound(self):
        for spec in (replace(self.spec, dataset_hash="0"*64), replace(self.spec, unit="GPa")):
            with self.assertRaises(ValueError):
                self.env.confirm_research_spec(spec, source="operator_config", reference="user")
        self.confirm()
        altered = self.env.snapshot()
        altered["datasets"]["ds_1"]["rows"][0]["y"] += 1
        self.env.reset(altered)
        self.assertEqual(self.env.invoke("split_dataset", self.split)["error_code"], "stale_reference")

    def test_cannot_replace_spec_after_split(self):
        self.confirm()
        self.env.invoke("split_dataset", self.split)
        before = self.env.snapshot()
        with self.assertRaises(ValueError):
            self.env.confirm_research_spec(replace(self.spec, model="mean"), source="operator_config", reference="new")
        self.assertEqual(self.env.snapshot(), before)

    def test_invalid_spec_values_rejected(self):
        for fields in ({"split_seed": True}, {"train_fraction": float("nan")}, {"model": "ridge"},
                       {"max_train_calls": 2}, {"max_test_calls": True}, {"validation_fraction": 0.1}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                replace(self.spec, **fields)

    def test_confirmation_not_exposed_before_bound_turn(self):
        class Observer:
            def reset(self, *args):
                self.seen = []
            def step(self, messages):
                self.seen.append(messages)
                return message("等待确认")
        agent = Observer()
        dialogue = build_dialogues(build_tasks()[0])[0]
        episode = run_episode(agent, ScientificMLEnvironment(), dialogue, research_spec=self.spec)
        self.assertNotIn(self.spec.spec_hash, str(agent.seen[0]))
        self.assertIn(self.spec.spec_hash, str(agent.seen[1]))
        event = next(e for e in episode["events"] if e["event_type"] == "research_spec_confirmed")
        self.assertEqual(event["turn_index"], 1)
        with self.assertRaises(ValueError):
            run_episode(Observer(), ScientificMLEnvironment(), dialogue, research_spec=self.spec, confirmation_turn=0)
