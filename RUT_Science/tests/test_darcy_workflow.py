"""Small generated fixtures test mechanics; real MAT evidence is saved separately."""
import copy
from dataclasses import replace
import io
import contextlib
import json
from pathlib import Path
import tempfile
import unittest

try:
    import numpy as np
    import scipy
    from rut_science.darcy_workflow import (DATASET_NAME, WORKFLOW_VERSION, DarcyEnvironment, DarcyControlAgent,
        file_hash, independent_reference, load_bundle, score_episode, run_workflow, verify_run)
except ImportError:
    np = None

from rut_science.research_spec import ResearchSpec
from rut_science.contracts import DialogueSpec
from rut_science.runtime import run_episode
from rut_science.util import canonical, digest, write_json


@unittest.skipIf(np is None, "Optional Darcy dependencies not installed")
class DarcyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name) / "data"
        cls.folder.mkdir()
        rng = np.random.default_rng(16)
        bundles = {}
        for split, n in (("train", 160), ("test", 32)):
            coeff = rng.uniform(3, 12, (n, 15, 15))
            # Known finite positive fields with zero boundaries; explicitly test fixtures.
            sol = np.broadcast_to(0.01 + coeff[:, 6, 6, None, None]*0.001, (n, 15, 15)).copy()
            sol[:, [0, -1], :] = 0
            sol[:, :, [0, -1]] = 0
            path = cls.folder / (split + ".npz")
            np.savez_compressed(path, coeff=coeff, sol=sol)
            bundles[split] = {"file": path.name, "sha256": file_hash(path), "shape": [n, 15, 15]}
        metadata = {"workflow_version": WORKFLOW_VERSION, "name": DATASET_NAME, "source": "generated_unit_test_fixture",
                    "bundles": bundles, "provenance": {"train": {"sha256": "a"*64}, "test": {"sha256": "b"*64}}}
        metadata["dataset_hash"] = digest(metadata)
        write_json(cls.folder / "dataset.json", metadata)
        cls.spec = ResearchSpec(DATASET_NAME, metadata["dataset_hash"], "pressure_field", "nondimensional",
                               "ridge_field", 0.8, 2026, split_policy="published_train_test",
                               metric="mean_relative_l2", model_parameters={"alpha": 1.0})
        cls.reference = independent_reference(cls.folder, cls.spec)
        dialogue = DialogueSpec("darcy_cpu_001", "ideal", ("ResearchSpec_JSON:\n" + canonical(cls.spec.to_dict()),), no_write_turns=())
        cls.episode = run_episode(DarcyControlAgent(), DarcyEnvironment(cls.folder), dialogue, research_spec=cls.spec,
                                 confirmation_turn=0, confirmation_source="operator_config")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_workflow_independent_reference_and_json_score(self):
        score = score_episode(self.folder, self.spec, self.episode, self.reference)
        self.assertTrue(score["execution_success"])
        self.assertTrue(all(score["checks"].values()))
        json.dumps(score, allow_nan=False)
        self.assertLess(self.reference["validation"]["mean_relative_l2"], self.reference["mean_field_validation_relative_l2"])

    def test_sealed_data_and_reference_not_exposed_to_agent(self):
        wire = str(self.episode["messages"])
        self.assertNotIn("per_sample_errors", wire)
        self.assertNotIn("weights", wire)
        self.assertNotIn("predictions", wire)
        self.assertNotIn("reference.json", wire)
        event = next(e for e in self.episode["events"] if e.get("tool_name") == "evaluate_model")
        self.assertNotIn("value", event["tool_result"])

    def test_train_validation_and_test_sources_are_separate(self):
        final = self.episode["final_state"]
        split = next(iter(final["splits"].values()))
        self.assertEqual(len(split["train_ids"]), 128)
        self.assertEqual(len(split["validation_ids"]), 32)
        self.assertEqual(len(split["test_ids"]), 32)
        self.assertFalse(set(split["train_ids"]) & set(split["validation_ids"]))
        self.assertTrue(all(i.startswith("test:") for i in split["test_ids"]))

    def test_post_test_training_and_repeated_test_are_blocked(self):
        env = DarcyEnvironment(self.folder)
        env.reset(self.episode["final_state"])
        before = env.snapshot()
        model_id = next(iter(before["models"]))
        split_id = next(iter(before["splits"]))
        self.assertEqual(env.invoke("evaluate_model", {"model_id": model_id})["error_code"], "budget_exhausted")
        self.assertEqual(env.invoke("train_model", {"split_id": split_id, "model": "ridge_field"})["error_code"], "sealed_test_locked")
        self.assertEqual(env.snapshot(), before)

    def test_scientific_tampering_is_detected(self):
        for kind in ("metric", "prediction", "preprocessing", "report", "spec", "reference"):
            episode, reference = copy.deepcopy(self.episode), copy.deepcopy(self.reference)
            final = episode["final_state"]
            if kind == "metric":
                next(iter(final["evaluations"].values()))["value"] = 0
            elif kind == "prediction":
                next(iter(final["evaluations"].values()))["predictions"][0][10] += 1
            elif kind == "preprocessing":
                next(iter(final["models"].values()))["x_mean"][0] += 1
            elif kind == "report":
                next(iter(final["reports"].values()))["research_spec_hash"] = "0"*64
            elif kind == "spec":
                final["research_spec"]["spec"]["split_seed"] += 1
            else:
                reference["spec_hash"] = "0"*64
            with self.subTest(kind=kind):
                self.assertFalse(score_episode(self.folder, self.spec, episode, reference)["execution_success"])

    def test_failed_call_not_erased_by_successful_final_state(self):
        episode = copy.deepcopy(self.episode)
        event = copy.deepcopy(next(e for e in episode["events"] if e.get("tool_name") == "train_model"))
        event["tool_result"] = {"status": "error", "error_code": "schema_error"}
        episode["events"].insert(1, event)
        score = score_episode(self.folder, self.spec, episode, self.reference)
        self.assertFalse(score["execution_success"])
        self.assertTrue(score["checks"]["reference_matches"])

    def test_mean_field_is_a_valid_separately_confirmed_method(self):
        spec = replace(self.spec, model="mean_field")
        dialogue = DialogueSpec("darcy_cpu_001", "ideal", ("ResearchSpec_JSON:\n" + canonical(spec.to_dict()),), no_write_turns=())
        episode = run_episode(DarcyControlAgent(), DarcyEnvironment(self.folder), dialogue, research_spec=spec,
                              confirmation_turn=0, confirmation_source="operator_config")
        reference = independent_reference(self.folder, spec)
        self.assertTrue(score_episode(self.folder, spec, episode, reference)["execution_success"])

    def test_bundle_hash_and_saved_artifact_verification(self):
        output = Path(self.temp.name) / "saved_run"
        with contextlib.redirect_stdout(io.StringIO()):
            run_workflow(self.folder, self.spec, output)
        self.assertEqual(verify_run(self.folder, output)["status"], "passed")
        path = output / "scientific_reports.json"
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_run(self.folder, output)
        # An independent temporary bundle copy may not silently change.
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for source in self.folder.iterdir():
                (folder / source.name).write_bytes(source.read_bytes())
            with (folder / "test.npz").open("ab") as stream:
                stream.write(b"changed")
            with self.assertRaises(ValueError):
                load_bundle(folder)
