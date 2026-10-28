"""Darcy validation-based branch with two pre-authorized fits and one test."""
import copy
from dataclasses import replace
from pathlib import Path
import numpy as np

from .darcy_workflow import (DarcyEnvironment, features, predict, relative_errors, partitions, load_bundle,
                             independent_reference, DATASET_NAME)
from .environment import ToolError
from .util import digest


def select_method(scores):
    return min(scores, key=lambda method: (scores[method], method != "mean_field"))


class SelectionDarcyEnvironment(DarcyEnvironment):
    tool_schemas = copy.deepcopy(DarcyEnvironment.tool_schemas)
    tool_schemas["select_model"] = {"ridge_model_id": {"type": "string"}, "mean_model_id": {"type": "string"}}
    tool_descriptions = {**DarcyEnvironment.tool_descriptions,
        "train_model": "Fit each pre-authorized candidate once: ridge_field or mean_field. Two successful fits total; train-only normalization. Return validation error, never test error.",
        "select_model": "Require both candidate model IDs on the same split. Choose minimum validation_relative_l2; exact ties choose mean_field. Return selected model_id and method. No selection after a sealed test."}

    def __init__(self, folder):
        super().__init__(folder)
        self._state["selections"] = {}

    def accepts_spec(self, spec):
        return super().accepts_spec(spec) and spec.model == "validation_select" and spec.max_train_calls == 2

    def _check_spec_fields(self, **fields):
        if "model" in fields:
            if fields.pop("model") not in {"ridge_field", "mean_field"}:
                raise ToolError("research_spec_mismatch", "Only the two pre-authorized candidates are permitted")
        return super()._check_spec_fields(**fields)

    def _train_model(self, split_id, model):
        if split_id not in self._state["splits"]:
            raise ToolError("precondition_failed", "A validated split is required")
        if self._state["evaluations"] or self._state["selections"]:
            raise ToolError("sealed_test_locked", "Candidate fitting is frozen after selection")
        if self._state["budget"]["train_calls"] >= 2 or any(m["model"] == model for m in self._state["models"].values()):
            raise ToolError("budget_exhausted", "Each candidate can be fitted once")
        split = self._state["splits"][split_id]
        spec = self._check_spec_fields(model=model, split_seed=split["seed"], train_fraction=split["train_fraction"])
        train = split["train_indices"]
        x, y = features(self.arrays["train"]["coeff"][train]), self.arrays["train"]["sol"][train].reshape(len(train), -1)
        center, scale, offset = x.mean(0), x.std(0), y.mean(0)
        scale = np.where(scale < 1e-12, 1, scale)
        z = (x-center)/scale
        alpha = spec["model_parameters"]["alpha"]
        weights = np.linalg.solve(z.T@z + alpha*np.eye(25), z.T@(y-offset)) if model == "ridge_field" else np.zeros((25, 225))
        record = {"split_id": split_id, "model": model, "alpha": alpha, "dataset_version": 1,
            "weights": weights.tolist(), "x_mean": center.tolist(), "x_scale": scale.tolist(), "y_mean": offset.tolist(),
            "fit_row_ids": list(split["train_ids"]), "preprocessing_fit_row_ids": list(split["train_ids"]), "boundary": "zero_Dirichlet"}
        val = split["validation_indices"]
        error = float(relative_errors(predict(record, self.arrays["train"]["coeff"][val]), self.arrays["train"]["sol"][val]).mean())
        if not np.isfinite(weights).all() or not np.isfinite(error):
            raise ToolError("computation_error", "Nonfinite candidate fit")
        record["validation_relative_l2"] = error
        model_id = "model_" + digest([split_id, model, alpha])[:12]
        self._state["models"][model_id] = record
        self._state["budget"]["train_calls"] += 1
        return {"model_id": model_id, "method": model, "n_fit": len(train), "validation_relative_l2": error}

    def _select_model(self, ridge_model_id, mean_model_id):
        self._confirmed_spec()
        models = self._state["models"]
        if ridge_model_id not in models or mean_model_id not in models:
            raise ToolError("precondition_failed", "Observe both fitted candidates first")
        ridge, mean = models[ridge_model_id], models[mean_model_id]
        if ridge["model"] != "ridge_field" or mean["model"] != "mean_field" or ridge["split_id"] != mean["split_id"]:
            raise ToolError("research_spec_mismatch", "Candidate identities or splits do not match")
        if self._state["evaluations"] or self._state["selections"]:
            raise ToolError("protocol_frozen", "Selection is allowed exactly once before the test")
        scores = {"ridge_field": ridge["validation_relative_l2"], "mean_field": mean["validation_relative_l2"]}
        method = select_method(scores)
        model_id = ridge_model_id if method == "ridge_field" else mean_model_id
        selection_id = "selection_" + digest([ridge_model_id, mean_model_id])[:12]
        record = {"model_id": model_id, "selected_method": method, "validation_scores": scores,
            "candidate_model_ids": {"ridge_field": ridge_model_id, "mean_field": mean_model_id},
            "policy": "min_validation_relative_l2_then_mean"}
        self._state["selections"][selection_id] = record
        return {"selection_id": selection_id, "selected": True, **record}

    def _evaluate_model(self, model_id):
        if len(self._state["selections"]) != 1 or next(iter(self._state["selections"].values()))["model_id"] != model_id:
            raise ToolError("precondition_failed", "Test only the validation-selected candidate")
        return super()._evaluate_model(model_id)

    def _write_report(self, evaluation_id):
        result = super()._write_report(evaluation_id)
        selection_id, selection = next(iter(self._state["selections"].items()))
        self._state["reports"][result["report_id"]].update(selection_id=selection_id,
            selection_policy=selection["policy"], candidate_model_ids=selection["candidate_model_ids"],
            candidate_validation_scores=selection["validation_scores"], research_method="validation_select")
        return result


def selection_reference(folder, spec):
    candidates = {method: independent_reference(folder, replace(spec, model=method, max_train_calls=1)) for method in ("ridge_field", "mean_field")}
    scores = {method: ref["validation"]["mean_relative_l2"] for method, ref in candidates.items()}
    return {"spec_hash": spec.spec_hash, "dataset_hash": spec.dataset_hash, "selected_method": select_method(scores),
            "validation_scores": scores, "candidates": candidates, "policy": "min_validation_relative_l2_then_mean"}


def score_selection_episode(folder, spec, episode, reference):
    metadata, arrays = load_bundle(folder)
    final = episode["final_state"]
    checks = {key: False for key in ("spec_confirmed", "protocol_matches", "heldout_isolation", "train_only_preprocessing",
        "validation_only_selection", "candidate_references_match", "predictions_recomputed", "metric_recomputed",
        "report_has_provenance", "sealed_once", "action_coverage", "logical_compliance", "zero_boundary")}
    calls = [e for e in episode["events"] if e["event_type"] == "tool_call"]
    checks["logical_compliance"] = all(e["tool_result"].get("status") == "ok" for e in calls)
    try:
        if not (len(final["models"]) == 2 and all(len(final[k]) == 1 for k in ("splits", "selections", "evaluations", "reports"))):
            return {"execution_success": False, "checks": checks, "score_protocol": "validation_selection_strict_v1"}
        split_id, split = next(iter(final["splits"].items()))
        selection_id, selection = next(iter(final["selections"].items()))
        eval_id, evaluation = next(iter(final["evaluations"].items()))
        report = next(iter(final["reports"].values()))
        models = {m["model"]: (key, m) for key, m in final["models"].items()}
        if set(models) != {"ridge_field", "mean_field"}:
            raise ValueError("Invalid candidate set")
        train, val = partitions(spec, 160)
        train_ids, val_ids, test_ids = ({f"train:r{i:03d}" for i in train}, {f"train:r{i:03d}" for i in val}, {f"test:r{i:03d}" for i in range(32)})
        checks["spec_confirmed"] = (final["research_spec"]["spec"] == spec.to_dict() and final["research_spec"]["spec_hash"] == spec.spec_hash
            and final["research_spec"]["confirmation"]["source"] == "operator_config")
        checks["protocol_matches"] = (metadata["dataset_hash"] == spec.dataset_hash and split["train_indices"] == train and split["validation_indices"] == val
            and split["test_indices"] == list(range(32)) and all(m["split_id"] == split_id and m["alpha"] == spec.model_parameters["alpha"] for _, m in models.values()))
        checks["heldout_isolation"] = (not (train_ids & val_ids or train_ids & test_ids or val_ids & test_ids)
            and set(split["train_ids"]) == train_ids and set(split["validation_ids"]) == val_ids and set(split["test_ids"]) == test_ids
            and all(set(m["fit_row_ids"]) == train_ids for _, m in models.values()) and set(evaluation["test_ids"]) == test_ids
            and episode["initial_state"]["datasets"] == final["datasets"])
        x = arrays["train"]["coeff"][train, ::3, ::3].reshape(128, 25)
        scale = x.std(0)
        scale[scale < 1e-12] = 1
        y_mean = arrays["train"]["sol"][train].reshape(128, 225).mean(0)
        checks["train_only_preprocessing"] = all(set(m["preprocessing_fit_row_ids"]) == train_ids and np.allclose(m["x_mean"], x.mean(0), rtol=1e-10, atol=1e-12)
            and np.allclose(m["x_scale"], scale, rtol=1e-10, atol=1e-12) and np.allclose(m["y_mean"], y_mean, rtol=1e-10, atol=1e-12) for _, m in models.values())
        validation_scores = {}
        candidates_ok = True
        for method, (_, model) in models.items():
            inputs = arrays["train"]["coeff"][val, ::3, ::3].reshape(32, 25)
            prediction = (((inputs-np.array(model["x_mean"]))/np.array(model["x_scale"]))@np.array(model["weights"])+np.array(model["y_mean"])).reshape(32, 15, 15)
            prediction[:, [0, -1], :] = 0
            prediction[:, :, [0, -1]] = 0
            target = arrays["train"]["sol"][val]
            errors = np.linalg.norm((prediction-target).reshape(32, -1), axis=1)/np.linalg.norm(target.reshape(32, -1), axis=1)
            validation_scores[method] = float(errors.mean())
            candidates_ok &= bool(np.allclose(prediction.reshape(32, 225), reference["candidates"][method]["validation"]["predictions"], rtol=1e-8, atol=1e-11)
                                  and np.isclose(model["validation_relative_l2"], errors.mean(), rtol=1e-9, atol=1e-12))
        selected = select_method(validation_scores)
        model_id, model = models[selected]
        checks["candidate_references_match"] = bool(candidates_ok and reference["spec_hash"] == spec.spec_hash and reference["dataset_hash"] == spec.dataset_hash)
        checks["validation_only_selection"] = (selected == reference["selected_method"] == selection["selected_method"] and selection["model_id"] == model_id
            and selection["policy"] == "min_validation_relative_l2_then_mean" and selection["candidate_model_ids"] == {method: key for method, (key, _) in models.items()}
            and all(np.isclose(selection["validation_scores"][method], score, rtol=1e-9, atol=1e-12) for method, score in validation_scores.items()))
        inputs = arrays["test"]["coeff"][:, ::3, ::3].reshape(32, 25)
        predicted = (((inputs-np.array(model["x_mean"]))/np.array(model["x_scale"]))@np.array(model["weights"])+np.array(model["y_mean"])).reshape(32, 15, 15)
        predicted[:, [0, -1], :] = 0
        predicted[:, :, [0, -1]] = 0
        stored = np.array(evaluation["predictions"]).reshape(32, 15, 15)
        target = arrays["test"]["sol"]
        errors = np.linalg.norm((predicted-target).reshape(32, -1), axis=1)/np.linalg.norm(target.reshape(32, -1), axis=1)
        checks["predictions_recomputed"] = bool(np.allclose(stored, predicted, rtol=1e-9, atol=1e-12) and np.allclose(predicted.reshape(32, 225), reference["candidates"][selected]["test"]["predictions"], rtol=1e-8, atol=1e-11))
        checks["metric_recomputed"] = bool(np.isclose(errors.mean(), evaluation["value"], rtol=1e-9, atol=1e-12) and np.isclose(errors.mean(), report["value"], rtol=1e-9, atol=1e-12)
            and np.allclose(errors, evaluation["per_sample_errors"], rtol=1e-9, atol=1e-12) and evaluation["model_id"] == model_id and evaluation["split_id"] == split_id)
        checks["report_has_provenance"] = (report["research_spec_hash"] == spec.spec_hash and report["dataset_hash"] == spec.dataset_hash and report["method"] == selected
            and report["evaluation_id"] == eval_id and report["model_id"] == model_id and report["selection_id"] == selection_id and report["research_method"] == spec.model
            and report["metric"] == spec.metric and report["target_unit"] == spec.unit and report["metric_unit"] == "dimensionless")
        checks["sealed_once"] = final["budget"]["train_calls"] == 2 and final["budget"]["test_calls"] == 1 and evaluation["sealed"] is True
        checks["zero_boundary"] = bool(np.all(stored[:, [0, -1], :] == 0) and np.all(stored[:, :, [0, -1]] == 0))
        successful = [e for e in calls if e["tool_result"].get("status") == "ok"]
        checks["action_coverage"] = (len(successful) == 8 and [e["tool_name"] for e in successful[:3]] == ["inspect_dataset", "validate_dataset", "split_dataset"]
            and {e["arguments"].get("model") for e in successful[3:5]} == {"ridge_field", "mean_field"}
            and [e["tool_name"] for e in successful[3:]] == ["train_model", "train_model", "select_model", "evaluate_model", "write_report"])
    except (ValueError, TypeError, KeyError, IndexError):
        pass
    checks = {k: bool(v) for k, v in checks.items()}
    return {"execution_success": all(checks.values()) and episode["termination"] == "completed_dialogue", "checks": checks, "score_protocol": "validation_selection_strict_v1"}
