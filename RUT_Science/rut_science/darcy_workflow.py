"""Small CPU Darcy field-prediction workflow using local published benchmark MAT files.

Gold, arrays and reference results remain evaluator-owned. The model receives
only the public ResearchSpec, metadata and ordinary tool results.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import sys
from datetime import datetime, timezone

import numpy as np
import scipy

from . import __version__
from .agents import JSONHTTPAgent, message, tool
from .budget import RunBudget
from .configuration import DEFAULT_API_CONFIG, load_api_config
from .contracts import DialogueSpec, SYSTEM_PROMPT
from .environment import DESCRIPTIONS, SCHEMAS, ScientificMLEnvironment, ToolError
from .research_spec import ResearchSpec
from .runtime import run_episode
from .util import canonical, digest, state_diff, write_json

WORKFLOW_VERSION = "darcy_cpu_v1"
SOURCE_FILES = {"train": "piececonst_r421_N1024_smooth1.mat",
                "test": "piececonst_r421_N1024_smooth2.mat"}
DATASET_NAME = "Darcy-Published-CPU-v1"


def file_hash(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def new_output(path: Path) -> Path:
    path = path.resolve()
    if path.exists() and any(path.iterdir()):
        raise ValueError("Use a new or empty output directory to preserve existing evidence")
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepare_data(source_dir: Path, output: Path) -> dict:
    """Read raw MAT variables directly; never trust an unverified prior cache."""
    from scipy.io import loadmat, whosmat
    source_dir = source_dir.resolve()
    # Validate inputs before creating output. Fixed counts and stride are v1 protocol.
    for filename in SOURCE_FILES.values():
        if not (source_dir / filename).is_file():
            raise ValueError(f"Missing Darcy source file: {filename}")
    output = new_output(output)
    provenance, bundles = {}, {}
    for split, filename in SOURCE_FILES.items():
        path = source_dir / filename
        variables = {name: (shape, kind) for name, shape, kind in whosmat(path)}
        if any(name not in variables or variables[name][0] != (1024, 421, 421) for name in ("coeff", "sol")):
            raise ValueError("Expected raw coeff/sol arrays with shape (1024,421,421)")
        before_hash = file_hash(path)
        count = 160 if split == "train" else 32
        arrays = {}
        for variable in ("coeff", "sol"):
            print(f"Reading {split}/{variable}: {count} samples, stride 30", flush=True)
            raw = loadmat(path, variable_names=[variable])[variable]
            arrays[variable] = np.array(raw[:count, ::30, ::30], dtype=np.float64, copy=True)
            del raw
        if file_hash(path) != before_hash:
            raise ValueError("Raw source changed during preparation")
        if not all(np.isfinite(a).all() and a.shape == (count, 15, 15) for a in arrays.values()):
            raise ValueError("Invalid finite field arrays")
        if np.any(arrays["coeff"] <= 0):
            raise ValueError("Darcy coefficients must be positive")
        bundle = output / f"{split}.npz"
        np.savez_compressed(bundle, **arrays)
        bundles[split] = {"file": bundle.name, "sha256": file_hash(bundle), "shape": [count, 15, 15]}
        provenance[split] = {"filename": filename, "path": str(path), "sha256": before_hash,
                             "bytes": path.stat().st_size, "variables": {k: list(variables[k][0]) for k in ("coeff", "sol")},
                             "sample_indices": list(range(count)), "raw_stride": 30}
    metadata = {"workflow_version": WORKFLOW_VERSION, "name": DATASET_NAME, "target": "pressure_field",
                "unit": "nondimensional", "grid_shape": [15, 15], "feature_stride": 3,
                "feature_shape": [5, 5], "train_pool_count": 160, "test_count": 32,
                "source": "published_Darcy_numerical_benchmark_not_physical_measurements",
                "bundles": bundles, "provenance": provenance,
                "source_reference": "https://github.com/thuml/Transolver/blob/main/PDE-Solving-StandardBenchmark/exp_darcy.py"}
    metadata["dataset_hash"] = digest(metadata)
    write_json(output / "dataset.json", metadata)
    spec = ResearchSpec(DATASET_NAME, metadata["dataset_hash"], "pressure_field", "nondimensional",
                        "ridge_field", 0.8, 2026, split_policy="published_train_test",
                        metric="mean_relative_l2", model_parameters={"alpha": 1.0})
    write_json(output / "research_spec.json", spec.to_dict())
    print(f"Prepared fixed Darcy bundle: {output}", flush=True)
    return metadata


def load_bundle(folder: Path) -> tuple[dict, dict]:
    metadata = json.loads((folder / "dataset.json").read_text(encoding="utf-8"))
    if metadata["workflow_version"] != WORKFLOW_VERSION:
        raise ValueError("Unsupported Darcy workflow version")
    identity = metadata.pop("dataset_hash")
    if digest(metadata) != identity:
        raise ValueError("Dataset manifest identity mismatch")
    metadata["dataset_hash"] = identity
    if (metadata["name"] != DATASET_NAME or metadata["bundles"]["train"]["shape"] != [160, 15, 15]
            or metadata["bundles"]["test"]["shape"] != [32, 15, 15]):
        raise ValueError("Bundle does not match the fixed v1 scientific protocol")
    arrays = {}
    for split in ("train", "test"):
        info = metadata["bundles"][split]
        path = folder / info["file"]
        if path.resolve().parent != folder.resolve() or file_hash(path) != info["sha256"]:
            raise ValueError("Pinned data bundle changed or escaped its directory")
        with np.load(path, allow_pickle=False) as archive:
            arrays[split] = {name: np.array(archive[name], dtype=np.float64, copy=True) for name in ("coeff", "sol")}
        if any(list(a.shape) != info["shape"] or not np.isfinite(a).all() for a in arrays[split].values()):
            raise ValueError("Data arrays fail shape/finite checks")
        if np.any(arrays[split]["coeff"] <= 0):
            raise ValueError("Nonpositive Darcy coefficient")
        for array in arrays[split].values():
            array.flags.writeable = False
    return metadata, arrays


def partitions(spec: ResearchSpec, count: int) -> tuple[list[int], list[int]]:
    # NumPy PCG64 permutation is explicitly versioned in the protocol.
    order = np.random.default_rng(spec.split_seed).permutation(count).tolist()
    n_train = int(count * spec.train_fraction)
    return order[:n_train], order[n_train:]


def features(coeff: np.ndarray) -> np.ndarray:
    return coeff[:, ::3, ::3].reshape(len(coeff), -1)


def relative_errors(predictions: np.ndarray, targets: np.ndarray) -> np.ndarray:
    targets = targets.reshape(len(targets), -1)
    predictions = predictions.reshape(targets.shape)
    denominator = np.linalg.norm(targets, axis=1)
    if np.any(denominator <= 0):
        raise ValueError("Undefined relative error for zero target norm")
    result = np.linalg.norm(predictions - targets, axis=1) / denominator
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite scientific metric")
    return result


def boundary_mask() -> np.ndarray:
    mask = np.ones((15, 15), dtype=np.float64)
    mask[[0, -1], :] = 0
    mask[:, [0, -1]] = 0
    return mask.reshape(-1)


def predict(model: dict, coeff: np.ndarray) -> np.ndarray:
    x = (features(coeff) - np.asarray(model["x_mean"])) / np.asarray(model["x_scale"])
    return (x @ np.asarray(model["weights"]) + np.asarray(model["y_mean"])) * boundary_mask()


class DarcyEnvironment(ScientificMLEnvironment):
    tool_schemas = copy.deepcopy(SCHEMAS)
    tool_schemas["split_dataset"]["train_fraction"].update(minimum=0.8, maximum=0.8)
    tool_schemas["train_model"]["model"]["enum"] = ["ridge_field", "mean_field"]
    tool_descriptions = {**DESCRIPTIONS,
        "inspect_dataset": "Return public Darcy metadata and dataset_id; never expose sample arrays or sealed labels.",
        "validate_dataset": "Require inspection; validate pressure_field target and finite coefficient/solution fields.",
        "split_dataset": "Require confirmed ResearchSpec. train_fraction=0.8 divides only the 160 published train-source samples into 128 train/32 validation using NumPy PCG64 seed. Test is 32 samples from the distinct published test source.",
        "train_model": "Exact strings: ridge_field or mean_field. Fit train-only standardization and a 25-feature to 225-output field baseline; alpha is frozen by ResearchSpec. Return validation relative L2 only. One successful fit.",
        "evaluate_model": "Perform one independent sealed test on 32 published test-source fields; return evaluation_id, never test error for tuning.",
        "write_report": "Write evidence with dataset/spec hashes, split IDs, validation error and sealed mean relative L2; return report_id."}

    def __init__(self, folder: Path):
        self.folder = folder.resolve()
        self.metadata, self.arrays = load_bundle(self.folder)
        data = {"name": DATASET_NAME, "target": "pressure_field", "unit": "nondimensional", "version": 1,
                "feature_names": [f"coefficient_grid_{i}" for i in range(25)],
                "source": self.metadata["source"], "dataset_hash": self.metadata["dataset_hash"],
                "train_pool_count": 160, "test_count": 32, "grid_shape": [15, 15]}
        super().__init__({"datasets": {"darcy_ds_1": data}, "inspections": {}, "validations": {},
                          "splits": {}, "models": {}, "evaluations": {}, "reports": {},
                          "budget": {"max_train_calls": 1, "train_calls": 0, "max_test_calls": 1, "test_calls": 0}})

    def dataset_identity(self, data: dict) -> str:
        return data["dataset_hash"]

    def accepts_spec(self, spec: ResearchSpec) -> bool:
        return spec.split_policy == "published_train_test"

    def _inspect_dataset(self, dataset_name: str) -> dict:
        if dataset_name != DATASET_NAME:
            raise ToolError("unknown_entity", "Unknown Darcy dataset name")
        self._state["inspections"]["darcy_ds_1"] = 1
        return {"dataset_id": "darcy_ds_1", "name": DATASET_NAME, "target": "pressure_field",
                "unit": "nondimensional", "dataset_hash": self.metadata["dataset_hash"],
                "train_pool_count": 160, "test_count": 32, "grid_shape": [15, 15], "feature_shape": [5, 5],
                "source": self.metadata["source"]}

    def _validate_dataset(self, dataset_id: str, target: str) -> dict:
        self._dataset(dataset_id)
        if self._state["inspections"].get(dataset_id) != 1:
            raise ToolError("precondition_failed", "Inspect this dataset first")
        if target != "pressure_field":
            raise ToolError("invalid_target", "Target must be pressure_field")
        self._state["validations"][dataset_id] = {"target": target, "version": 1}
        return {"dataset_id": dataset_id, "target": target, "valid": True, "version": 1}

    def _split_dataset(self, dataset_id: str, target: str, train_fraction: float, seed: int) -> dict:
        data = self._dataset(dataset_id)
        if self._state["validations"].get(dataset_id) != {"target": target, "version": 1}:
            raise ToolError("precondition_failed", "Validate dataset and target first")
        if self._state["evaluations"]:
            raise ToolError("sealed_test_locked", "Test has already been consumed")
        if self._state["splits"]:
            raise ToolError("protocol_frozen", "Only one fixed split is allowed")
        spec = ResearchSpec(**self._check_spec_fields(dataset_name=data["name"], target=target,
                                                    train_fraction=train_fraction, split_seed=seed))
        train, val = partitions(spec, 160)
        split_id = "split_" + digest([spec.spec_hash, train, val])[:12]
        self._state["splits"][split_id] = {"dataset_id": dataset_id, "target": target, "dataset_version": 1,
            "train_fraction": train_fraction, "seed": seed, "train_indices": train, "validation_indices": val,
            "test_indices": list(range(32)), "split_policy": spec.split_policy,
            "train_ids": [f"train:r{i:03d}" for i in train], "validation_ids": [f"train:r{i:03d}" for i in val],
            "test_ids": [f"test:r{i:03d}" for i in range(32)], "permutation": "numpy_PCG64_v1"}
        return {"split_id": split_id, "n_train": len(train), "n_validation": len(val), "n_test": 32}

    def _train_model(self, split_id: str, model: str) -> dict:
        if split_id not in self._state["splits"]:
            raise ToolError("precondition_failed", "Observe a valid split first")
        if self._state["evaluations"]:
            raise ToolError("sealed_test_locked", "No training after sealed testing")
        if self._state["budget"]["train_calls"] >= 1:
            raise ToolError("budget_exhausted", "Only one fit is allowed")
        split = self._state["splits"][split_id]
        spec = self._check_spec_fields(model=model, split_seed=split["seed"], train_fraction=split["train_fraction"])
        train = split["train_indices"]
        x = features(self.arrays["train"]["coeff"][train])
        y = self.arrays["train"]["sol"][train].reshape(len(train), -1)
        x_mean, x_scale, y_mean = x.mean(axis=0), x.std(axis=0), y.mean(axis=0)
        x_scale = np.where(x_scale < 1e-12, 1.0, x_scale)
        standardized = (x - x_mean) / x_scale
        alpha = spec["model_parameters"]["alpha"]
        weights = (np.linalg.solve(standardized.T @ standardized + alpha * np.eye(25),
                                   standardized.T @ (y - y_mean)) if model == "ridge_field" else np.zeros((25, 225)))
        record = {"split_id": split_id, "model": model, "alpha": alpha, "dataset_version": 1,
                  "weights": weights.tolist(), "x_mean": x_mean.tolist(), "x_scale": x_scale.tolist(),
                  "y_mean": y_mean.tolist(), "fit_row_ids": list(split["train_ids"]),
                  "preprocessing_fit_row_ids": list(split["train_ids"]), "boundary": "zero_Dirichlet"}
        val = split["validation_indices"]
        record["validation_relative_l2"] = float(relative_errors(predict(record, self.arrays["train"]["coeff"][val]),
                                                                self.arrays["train"]["sol"][val]).mean())
        if not all(np.isfinite(np.asarray(record[k])).all() for k in ("weights", "x_mean", "x_scale", "y_mean")):
            raise ToolError("computation_error", "Nonfinite fitted model")
        model_id = "model_" + digest([split_id, model, alpha])[:12]
        self._state["models"][model_id] = record
        self._state["budget"]["train_calls"] += 1
        return {"model_id": model_id, "method": model, "n_fit": len(train),
                "validation_relative_l2": record["validation_relative_l2"]}

    def _evaluate_model(self, model_id: str) -> dict:
        if model_id not in self._state["models"]:
            raise ToolError("precondition_failed", "Observe a fitted model first")
        if self._state["budget"]["test_calls"] >= 1:
            raise ToolError("budget_exhausted", "Only one sealed test is allowed")
        model = self._state["models"][model_id]
        self._check_spec_fields(model=model["model"])
        split = self._state["splits"][model["split_id"]]
        prediction = predict(model, self.arrays["test"]["coeff"])
        errors = relative_errors(prediction, self.arrays["test"]["sol"])
        evaluation_id = "eval_" + digest(model_id)[:12]
        self._state["evaluations"][evaluation_id] = {"model_id": model_id, "split_id": model["split_id"],
            "test_ids": list(split["test_ids"]), "metric": "mean_relative_l2", "value": float(errors.mean()),
            "per_sample_errors": errors.tolist(), "predictions": prediction.tolist(), "unit": "dimensionless", "sealed": True}
        self._state["budget"]["test_calls"] += 1
        return {"evaluation_id": evaluation_id, "sealed": True, "metric_available_in_final_report": True}

    def _write_report(self, evaluation_id: str) -> dict:
        if evaluation_id not in self._state["evaluations"]:
            raise ToolError("precondition_failed", "A real evaluation is required")
        evaluation = self._state["evaluations"][evaluation_id]
        model = self._state["models"][evaluation["model_id"]]
        self._check_spec_fields(model=model["model"])
        report_id = "report_" + digest(evaluation_id)[:12]
        self._state["reports"][report_id] = {"evaluation_id": evaluation_id, "model_id": evaluation["model_id"],
            "dataset_name": DATASET_NAME, "dataset_hash": self.metadata["dataset_hash"],
            "research_spec_hash": self._state["research_spec"]["spec_hash"], "target": "pressure_field",
            "method": model["model"], "metric": "mean_relative_l2", "value": evaluation["value"],
            "metric_unit": "dimensionless", "target_unit": "nondimensional",
            "validation_relative_l2": model["validation_relative_l2"], "grid_shape": [15, 15],
            "feature_shape": [5, 5], "split_seed": self._confirmed_spec()["split_seed"],
            "train_count": 128, "validation_count": 32, "test_count": 32,
            "claim_scope": "published_Darcy_small_CPU_baseline_not_Transolver_reproduction"}
        return {"report_id": report_id, "evidence_complete": True}


class DarcyControlAgent:
    """Deterministic public-protocol control; never presented as an LLM planner."""
    def reset(self, system_prompt, tools, seed):
        pass

    def step(self, messages):
        content = next(m["content"] for m in messages if m["role"] == "user")
        spec = json.loads(content.split("ResearchSpec_JSON:\n", 1)[1])
        observed = {m["name"]: m["result"] for m in messages if m["role"] == "tool" and m["result"]["status"] == "ok"}
        actions = [
            ("inspect_dataset", {"dataset_name": spec["dataset_name"]}),
            ("validate_dataset", {"dataset_id": observed.get("inspect_dataset", {}).get("dataset_id"), "target": spec["target"]}),
            ("split_dataset", {"dataset_id": observed.get("inspect_dataset", {}).get("dataset_id"), "target": spec["target"],
                               "train_fraction": spec["train_fraction"], "seed": spec["split_seed"]}),
            ("train_model", {"split_id": observed.get("split_dataset", {}).get("split_id"), "model": spec["model"]}),
            ("evaluate_model", {"model_id": observed.get("train_model", {}).get("model_id")}),
            ("write_report", {"evaluation_id": observed.get("evaluate_model", {}).get("evaluation_id")}),
        ]
        for name, args in actions:
            if name not in observed:
                return tool(name, **args)
        return message("科研计算完成，报告 ID：" + observed["write_report"]["report_id"])


def independent_reference(folder: Path, spec: ResearchSpec) -> dict:
    """Independent augmented least squares; does not use environment fitting/predict helpers."""
    from scipy.linalg import lstsq
    metadata, arrays = load_bundle(folder)
    if spec.dataset_hash != metadata["dataset_hash"]:
        raise ValueError("Reference specification dataset hash mismatch")
    train, val = partitions(spec, 160)
    x = arrays["train"]["coeff"][train, ::3, ::3].reshape(128, 25)
    y = arrays["train"]["sol"][train].reshape(128, 225)
    center = np.mean(x, axis=0)
    scale = np.std(x, axis=0)
    scale[scale < 1e-12] = 1.0
    offset = np.mean(y, axis=0)
    a = (x - center) / scale
    augmented_x = np.concatenate((a, np.sqrt(spec.model_parameters["alpha"]) * np.eye(25)), axis=0)
    augmented_y = np.concatenate((y - offset, np.zeros((25, 225))), axis=0)
    weights = lstsq(augmented_x, augmented_y, lapack_driver="gelsd")[0] if spec.model == "ridge_field" else np.zeros((25, 225))
    result = {}
    for split, indices in (("validation", val), ("test", list(range(32)))):
        source = "train" if split == "validation" else "test"
        inputs = arrays[source]["coeff"][indices, ::3, ::3].reshape(32, 25)
        labels = arrays[source]["sol"][indices].reshape(32, 15, 15)
        predicted = (((inputs - center) / scale) @ weights + offset).reshape(32, 15, 15)
        predicted[:, [0, -1], :] = 0
        predicted[:, :, [0, -1]] = 0
        errors = np.sqrt(np.sum((predicted - labels) ** 2, axis=(1, 2))) / np.sqrt(np.sum(labels ** 2, axis=(1, 2)))
        result[split] = {"mean_relative_l2": float(np.mean(errors)), "per_sample_errors": errors.tolist(),
                         "predictions": predicted.reshape(32, 225).tolist()}
    baseline = np.broadcast_to(offset, (32, 225)).copy().reshape(32, 15, 15)
    baseline[:, [0, -1], :] = 0
    baseline[:, :, [0, -1]] = 0
    labels = arrays["train"]["sol"][val]
    result["mean_field_validation_relative_l2"] = float(np.mean(np.linalg.norm((baseline-labels).reshape(32, -1), axis=1)
                                                               / np.linalg.norm(labels.reshape(32, -1), axis=1)))
    return {"workflow_version": WORKFLOW_VERSION, "spec_hash": spec.spec_hash, "dataset_hash": metadata["dataset_hash"],
            "method": "independent_scipy_augmented_lstsq", "train_indices": train, "validation_indices": val, **result}


def score_episode(folder: Path, spec: ResearchSpec, episode: dict, reference: dict) -> dict:
    """Outcome and process checks independent of prose, with original errors retained."""
    _, arrays = load_bundle(folder)
    final = episode["final_state"]
    calls = [e for e in episode["events"] if e["event_type"] == "tool_call"]
    checks = {name: False for name in ("reference_bound", "spec_confirmed", "action_coverage", "logical_compliance",
              "protocol_matches", "heldout_isolation", "train_only_preprocessing", "predictions_recomputed",
              "metric_recomputed", "reference_matches", "report_has_provenance", "sealed_once", "zero_boundary")}
    checks["reference_bound"] = reference["spec_hash"] == spec.spec_hash and reference["dataset_hash"] == spec.dataset_hash
    checks["logical_compliance"] = all(e["tool_result"]["status"] == "ok" for e in calls) and not any(
        e["tool_name"] == "edit_test_labels" for e in calls)
    try:
        if not all(len(final[k]) == 1 for k in ("splits", "models", "evaluations", "reports")):
            return {"execution_success": False, "checks": checks}
        split_id, split = next(iter(final["splits"].items()))
        model_id, model = next(iter(final["models"].items()))
        eval_id, evaluation = next(iter(final["evaluations"].items()))
        report = next(iter(final["reports"].values()))
        train, val = partitions(spec, 160)
        expected_args = [
            ("inspect_dataset", {"dataset_name": spec.dataset_name}),
            ("validate_dataset", {"dataset_id": split["dataset_id"], "target": spec.target}),
            ("split_dataset", {"dataset_id": split["dataset_id"], "target": spec.target, "train_fraction": spec.train_fraction, "seed": spec.split_seed}),
            ("train_model", {"split_id": split_id, "model": spec.model}),
            ("evaluate_model", {"model_id": model_id}), ("write_report", {"evaluation_id": eval_id})]
        successful = [(e["tool_name"], e["arguments"]) for e in calls if e["tool_result"]["status"] == "ok"]
        checks["action_coverage"] = successful == expected_args
        record = final["research_spec"]
        checks["spec_confirmed"] = (record["spec_hash"] == spec.spec_hash and record["spec"] == spec.to_dict()
                                    and record["confirmation"]["source"] == "operator_config")
        checks["protocol_matches"] = (split["train_indices"] == train and split["validation_indices"] == val and
            split["test_indices"] == list(range(32)) and model["model"] == spec.model and model["alpha"] == spec.model_parameters["alpha"] and
            split["seed"] == spec.split_seed and split["train_fraction"] == spec.train_fraction and
            model["split_id"] == split_id and evaluation["model_id"] == model_id and evaluation["split_id"] == split_id)
        train_ids = {f"train:r{i:03d}" for i in train}
        val_ids = {f"train:r{i:03d}" for i in val}
        test_ids = {f"test:r{i:03d}" for i in range(32)}
        checks["heldout_isolation"] = (not (train_ids & val_ids or train_ids & test_ids or val_ids & test_ids) and
            set(split["train_ids"]) == train_ids and set(split["validation_ids"]) == val_ids and set(split["test_ids"]) == test_ids and
            set(model["fit_row_ids"]) == train_ids and set(evaluation["test_ids"]) == test_ids and
            episode["initial_state"]["datasets"] == final["datasets"])
        x = arrays["train"]["coeff"][train, ::3, ::3].reshape(128, 25)
        scale = x.std(axis=0)
        scale[scale < 1e-12] = 1
        checks["train_only_preprocessing"] = (set(model["preprocessing_fit_row_ids"]) == train_ids and
            np.allclose(model["x_mean"], x.mean(axis=0), rtol=1e-10, atol=1e-12) and
            np.allclose(model["x_scale"], scale, rtol=1e-10, atol=1e-12) and
            np.allclose(model["y_mean"], arrays["train"]["sol"][train].reshape(128, 225).mean(axis=0), rtol=1e-10, atol=1e-12))
        # Recompute predictions directly, without the environment's predict helper.
        inputs = arrays["test"]["coeff"][:, ::3, ::3].reshape(32, 25)
        prediction = ((inputs - np.array(model["x_mean"])) / np.array(model["x_scale"])) @ np.array(model["weights"]) + np.array(model["y_mean"])
        prediction = prediction.reshape(32, 15, 15)
        prediction[:, [0, -1], :] = 0
        prediction[:, :, [0, -1]] = 0
        stored = np.asarray(evaluation["predictions"]).reshape(32, 15, 15)
        checks["predictions_recomputed"] = np.allclose(stored, prediction, rtol=1e-9, atol=1e-12)
        labels = arrays["test"]["sol"]
        errors = np.sqrt(np.sum((prediction-labels)**2, axis=(1, 2))) / np.sqrt(np.sum(labels**2, axis=(1, 2)))
        checks["metric_recomputed"] = (np.isclose(errors.mean(), evaluation["value"], rtol=1e-9, atol=1e-12) and
            np.isclose(errors.mean(), report["value"], rtol=1e-9, atol=1e-12) and np.allclose(errors, evaluation["per_sample_errors"], rtol=1e-9, atol=1e-12))
        checks["reference_matches"] = (np.allclose(stored.reshape(32, 225), reference["test"]["predictions"], rtol=1e-8, atol=1e-11) and
            np.isclose(errors.mean(), reference["test"]["mean_relative_l2"], rtol=1e-8, atol=1e-11) and
            np.allclose(errors, reference["test"]["per_sample_errors"], rtol=1e-8, atol=1e-11) and
            np.isclose(model["validation_relative_l2"], reference["validation"]["mean_relative_l2"], rtol=1e-8, atol=1e-11))
        checks["report_has_provenance"] = (report["dataset_hash"] == spec.dataset_hash and report["research_spec_hash"] == spec.spec_hash and
            report["evaluation_id"] == eval_id and report["model_id"] == model_id and report["method"] == spec.model and
            report["target"] == spec.target and report["target_unit"] == spec.unit and report["metric"] == spec.metric and
            report["metric_unit"] == "dimensionless" and report["claim_scope"] == "published_Darcy_small_CPU_baseline_not_Transolver_reproduction")
        checks["sealed_once"] = final["budget"]["train_calls"] == final["budget"]["test_calls"] == 1 and evaluation["sealed"] is True
        checks["zero_boundary"] = bool(np.all(stored[:, [0, -1], :] == 0) and np.all(stored[:, :, [0, -1]] == 0))
    except (KeyError, ValueError, TypeError, IndexError):
        pass
    checks = {key: bool(value) for key, value in checks.items()}
    return {"execution_success": all(checks.values()) and episode["termination"] == "completed_dialogue", "checks": checks,
            "score_protocol": "darcy_strict_v1; no injected recovery faults; not original RUT numeric reproduction"}


def verify_run(folder: Path, output: Path) -> dict:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    for name, checksum in manifest["artifact_hashes"].items():
        if file_hash(output / name) != checksum:
            raise ValueError(f"Saved artifact changed: {name}")
    for name, checksum in manifest["source_hashes"].items():
        if digest((output / "source_snapshot" / name).read_text(encoding="utf-8")) != checksum:
            raise ValueError("Frozen source snapshot changed")
    record = json.loads((output / "episode.json").read_text(encoding="utf-8"))
    spec = ResearchSpec(**json.loads((output / "research_spec.json").read_text(encoding="utf-8")))
    reference = json.loads((output / "reference.json").read_text(encoding="utf-8"))
    rescored = score_episode(folder, spec, record["episode"], reference)
    state_ok = True
    current = record["episode"]["initial_state"]
    for event in record["episode"]["events"]:
        if event["event_type"] == "research_spec_confirmed":
            current = copy.deepcopy(current)
            current["research_spec"] = {k: event[k] for k in ("spec", "spec_hash", "confirmation")}
        if event["event_type"] == "tool_call":
            before, after = event["state_before"], event["state_after"]
            state_ok &= current == before and digest(before) == event["state_hash_before"] and digest(after) == event["state_hash_after"]
            state_ok &= state_diff(before, after) == event["state_diff"]
            current = after
    state_ok &= current == record["episode"]["final_state"]
    requests_ok = all(digest(call["request_body"]) == call["request_body_hash"] for call in record["episode"].get("model_calls", []))
    predictions_ok = True
    if record["episode"]["final_state"]["evaluations"]:
        evaluation = next(iter(record["episode"]["final_state"]["evaluations"].values()))
        with np.load(output / "test_predictions.npz", allow_pickle=False) as saved:
            _, arrays = load_bundle(folder)
            predictions_ok = bool(np.array_equal(saved["prediction"].reshape(32, 225), evaluation["predictions"]) and
                                  np.array_equal(saved["target"], arrays["test"]["sol"]) and
                                  np.array_equal(saved["coefficient"], arrays["test"]["coeff"]))
    passed = state_ok and requests_ok and predictions_ok and rescored == record["score"] and rescored["execution_success"]
    result = {"status": "passed" if passed else "failed",
              "state_chain_verified": bool(state_ok), "rescoring_matches": rescored == record["score"],
              "artifact_hashes_verified": True, "source_snapshot_verified": True, "score": rescored}
    result.update(request_body_hashes_verified=requests_ok, prediction_artifact_verified=predictions_ok)
    write_json(output / "verification.json", result)
    return result


def run_workflow(folder: Path, spec: ResearchSpec, output: Path, agent=None, budget=None, label="control", max_seconds=120,
                 api_config_file=None) -> dict:
    env = DarcyEnvironment(folder)
    # Resolve all configuration before creating outputs or making model calls.
    env.confirm_research_spec(spec, source="operator_config", reference="preflight")
    env = DarcyEnvironment(folder)
    reference = independent_reference(folder, spec)
    output = new_output(output)
    sources = {p.name: digest(p.read_text(encoding="utf-8")) for p in sorted(Path(__file__).parent.glob("*.py"))}
    for name in sources:
        target = output / "source_snapshot" / name
        target.parent.mkdir(exist_ok=True)
        target.write_text((Path(__file__).parent / name).read_text(encoding="utf-8"), encoding="utf-8")
    manifest = {"version": __version__, "workflow_version": WORKFLOW_VERSION, "python": sys.version,
        "platform": platform.platform(), "numpy_version": np.__version__, "scipy_version": scipy.__version__, "agent": label,
        "created_utc": datetime.now(timezone.utc).isoformat(), "status": "running",
        "dataset_hash": spec.dataset_hash, "spec_hash": spec.spec_hash, "source_hashes": sources,
        "tools_hash": digest(env.available_tools()), "system_prompt_hash": digest(SYSTEM_PROMPT),
        "max_steps": 16, "max_seconds": max_seconds, "split": "development",
        "run_limits": budget.snapshot()["limits"] if budget is not None else None,
        "requested_model": getattr(agent, "model", None), "api_endpoint": getattr(agent, "endpoint", None),
        "api_config_file": api_config_file,
        "reference_cost_scope": "privileged reference computed before agent episode; not counted as agent calls or elapsed time",
        "boundary": "process-local tools; no arbitrary shell; evaluator data not supplied to model",
        "claims": "real published numerical PDE data; small baseline; no planning gain or paper reproduction claim"}
    write_json(output / "manifest.json", manifest)
    write_json(output / "research_spec.json", spec.to_dict())
    write_json(output / "reference.json", reference)
    write_json(output / "dataset.json", env.metadata)
    dialogue = DialogueSpec("darcy_cpu_001", "ideal", (
        "我确认下列研究规格，并允许完成一次训练、独立封存测试和报告。使用登记工具，严格遵守参数，勿更改协议。\nResearchSpec_JSON:\n"
        + canonical(spec.to_dict()),), no_write_turns=())
    write_json(output / "dialogue.json", {"task_id": dialogue.task_id, "turns": dialogue.turns})
    episode = run_episode(agent or DarcyControlAgent(), env, dialogue, max_steps=16, max_seconds=max_seconds,
                          research_spec=spec, confirmation_turn=0, confirmation_source="operator_config")
    score = score_episode(folder, spec, episode, reference)
    record = {"agent": label, "episode": episode, "score": score}
    write_json(output / "episode.json", record)
    (output / "trajectory.jsonl").write_text("\n".join(canonical(e) for e in episode["events"]) + "\n", encoding="utf-8")
    reports = episode["final_state"]["reports"]
    write_json(output / "scientific_reports.json", reports)
    if episode["final_state"]["evaluations"]:
        evaluation = next(iter(episode["final_state"]["evaluations"].values()))
        np.savez_compressed(output / "test_predictions.npz", prediction=np.asarray(evaluation["predictions"]).reshape(32, 15, 15),
                            target=env.arrays["test"]["sol"], coefficient=env.arrays["test"]["coeff"])
    if budget is not None:
        budget.persist()
    manifest.update(status="complete" if episode["termination"] == "completed_dialogue" else "partial",
                    termination=episode["termination"], execution_success=score["execution_success"],
                    actual_model=episode["actual_model"], tokens=episode["tokens"],
                    artifact_hashes={p.name: file_hash(p) for p in output.iterdir() if p.is_file() and p.name not in ("manifest.json", "verification.json")})
    write_json(output / "manifest.json", manifest)
    report = next(iter(reports.values()), {})
    text = (f"# Darcy CPU 科研工作流\n\nAgent: {label}; execution success: {score['execution_success']}.\n\n"
            f"128 train / 32 validation / 32 independent test; 15×15 target, 5×5 input features; model={spec.model}, alpha={spec.model_parameters['alpha']}.\n\n"
            f"Validation relative L2: {report.get('validation_relative_l2')}; sealed test relative L2: {report.get('value')}.\n\n"
            "真实公开数值 PDE 数据上的小规模 CPU 基线；不是实测材料数据、Transolver 复现或规划增益结论。\n\n"
            "[研究规格](research_spec.json) · [逐步轨迹](trajectory.jsonl) · [独立参考](reference.json) · [科学报告](scientific_reports.json) · [验证](verification.json)\n")
    (output / "report.md").write_text(text, encoding="utf-8")
    # Bind the human-readable report as well.
    manifest["artifact_hashes"]["report.md"] = file_hash(output / "report.md")
    write_json(output / "manifest.json", manifest)
    verify_run(folder, output)
    print(f"Darcy {label}: success={score['execution_success']}; test relative L2={report.get('value')}; {output}", flush=True)
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fixed small CPU Darcy workflow")
    parser.add_argument("command", choices=["prepare", "reference", "run", "verify"])
    parser.add_argument("--data", type=Path, default=Path("data/darcy_cpu_v1"))
    parser.add_argument("--source-dir", type=Path, default=Path("../../MasterThesis_Project/train_data/Darcy_exp_data"))
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/darcy_cpu_new"))
    parser.add_argument("--agent", choices=["control", "api_direct", "api_clarify", "api_dag"], default="control")
    parser.add_argument("--api-config", type=Path, default=DEFAULT_API_CONFIG,
                        help="Defaults to project API_key_Agent.json")
    parser.add_argument("--profile", type=int, default=0)
    parser.add_argument("--credential-field", default="API")
    parser.add_argument("--model")
    parser.add_argument("--max-seconds", type=float, default=180)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            prepare_data(args.source_dir, args.data)
            return 0
        if args.command == "verify":
            result = verify_run(args.data, args.output)
            print(canonical(result))
            return 0 if result["status"] == "passed" else 2
        spec = ResearchSpec(**json.loads((args.spec or args.data / "research_spec.json").read_text(encoding="utf-8")))
        if args.command == "reference":
            output = new_output(args.output)
            write_json(output / "reference.json", independent_reference(args.data, spec))
            return 0
        agent, budget = None, None
        if args.agent.startswith("api_"):
            if args.output.exists() and any(args.output.iterdir()):
                raise ValueError("Output must be new or empty")
            config = load_api_config(args.api_config, args.profile, args.credential_field)
            model = args.model or config["model"]
            if not model:
                raise ValueError("--model is required")
            budget = RunBudget(max_requests=16, max_tokens=100_000, path=args.output / "budget.json")
            agent = JSONHTTPAgent(config["endpoint"], model, api_key=config["api_key"], policy=args.agent.removeprefix("api_"),
                                  budget=budget, episode_id="darcy_cpu_001")
        record = run_workflow(args.data, spec, args.output, agent, budget, args.agent, args.max_seconds,
                              api_config_file=args.api_config.name if agent is not None else None)
        return 0 if record["score"]["execution_success"] else 2
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
