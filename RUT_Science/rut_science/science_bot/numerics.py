"""Real regression tools. Sealed arrays never enter the public observation."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import numpy as np
from ..util import digest

TOOL_VERSION = "budgeted_numpy_ridge_v1"


def array_hash(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


@dataclass
class ResearchData:
    fit_x: np.ndarray
    fit_y: np.ndarray
    val_x: np.ndarray
    val_y: np.ndarray
    sealed_x: np.ndarray
    sealed_y: np.ndarray
    identity: str
    provenance: dict

    def public(self):
        return {"source": self.provenance["source"], "n_fit_pool": len(self.fit_x),
                "n_search_val": len(self.val_x), "input_grid": list(self.fit_x.shape[1:]),
                "output_dim": self.fit_y.reshape(len(self.fit_y), -1).shape[1]}


def generated(spec):
    # Entire mechanism groups are disjoint across meta splits. Public fields
    # exclude group, generator parameters, seeds and data hashes.
    split_offset = {"train": 0, "dev": 10000, "test": 20000, "demo": 30000}[spec.split]
    root = split_offset + spec.group
    mechanism = np.random.default_rng(root + 709)
    rng = np.random.default_rng(np.random.SeedSequence([root, spec.task_seed, 9401]))
    n = 192
    latent = rng.normal(size=(n, 9))
    coarse = latent.reshape(n, 3, 3)
    from scipy.ndimage import zoom
    smooth = zoom(coarse, (1, 5/3, 5/3), order=1)[:, :5, :5]
    correlation = mechanism.choice([0.0, 0.65, 0.98])
    x = correlation * smooth + (1-correlation) * rng.normal(size=(n, 5, 5))
    # Some tasks are solved cheaply; others need fine observations or more data.
    strength = mechanism.choice([0.015, 0.25, 0.7])
    fine = bool(mechanism.integers(2))
    weights = mechanism.normal(size=(25, 4))
    if not fine:
        mask = np.zeros((5, 5)); mask[::2, ::2] = 1
        weights *= mask.reshape(-1, 1)
    weights *= strength / max(np.linalg.norm(weights), 1e-9)
    noise = float(mechanism.choice([0.01, 0.05, 0.20]))
    y = 1.0 + x.reshape(n, -1) @ weights + rng.normal(scale=noise, size=(n, 4))
    parts = (x[:96], y[:96], x[96:128], y[96:128], x[128:], y[128:])
    identity = digest({"tool": TOOL_VERSION, "root": root, "instance": spec.task_seed,
                       "hashes": [array_hash(a) for a in parts]})
    return ResearchData(*parts, identity, {"source": "controlled_generated_regression", "root_group": root,
                                         "split": spec.split, "instance": spec.task_seed})


def darcy(spec, folder):
    from ..darcy_workflow import load_bundle
    meta, arrays = load_bundle(Path(folder))
    # Already-exposed bundle is a product/transfer pilot, never a fresh blind test.
    if spec.split != "demo":
        raise ValueError("Existing Darcy bundle is historically exposed; use split=demo")
    order = np.random.default_rng(spec.task_seed).permutation(160)
    fit, val = order[:128], order[128:]
    tr, te = arrays["train"], arrays["test"]
    return ResearchData(tr["coeff"][fit], tr["sol"][fit].reshape(128, -1),
                        tr["coeff"][val], tr["sol"][val].reshape(32, -1),
                        te["coeff"], te["sol"].reshape(32, -1),
                        digest({"dataset": meta["dataset_hash"], "order": order.tolist(), "tool": TOOL_VERSION}),
                        {"source": meta["source"], "dataset_hash": meta["dataset_hash"],
                         "historically_exposed": True, "scope": "transfer_pilot_not_blind_test"})


def load_data(spec, folder=None):
    return generated(spec) if spec.dataset == "generated" else darcy(spec, folder)


def features(x, grid):
    rows = np.linspace(0, x.shape[1]-1, grid, dtype=int)
    cols = np.linspace(0, x.shape[2]-1, grid, dtype=int)
    return x[:, rows[:, None], cols].reshape(len(x), -1)


def fit(data, candidate):
    p = candidate["parameters"]
    n = len(data.fit_x) if p.get("fidelity", "full") == "full" else len(data.fit_x)//2
    y = data.fit_y[:n]
    if candidate["kind"] == "fit_mean":
        return {"kind": "mean", "y_mean": y.mean(0).tolist(), "n_fit": n}
    x = features(data.fit_x[:n], p["feature_grid"])
    mu, scale = x.mean(0), x.std(0)
    scale = np.where(scale < 1e-12, 1.0, scale)
    z, ym = (x-mu)/scale, y.mean(0)
    weights = np.linalg.solve(z.T @ z + p["alpha"]*np.eye(z.shape[1]), z.T @ (y-ym))
    return {"kind": "ridge", "grid": p["feature_grid"], "x_mean": mu.tolist(), "x_scale": scale.tolist(),
            "y_mean": ym.tolist(), "weights": weights.tolist(), "n_fit": n}


def predict(model, x):
    mean = np.asarray(model["y_mean"])
    if model["kind"] == "mean":
        return np.broadcast_to(mean, (len(x), len(mean))).copy()
    z = (features(x, model["grid"])-np.asarray(model["x_mean"]))/np.asarray(model["x_scale"])
    return z @ np.asarray(model["weights"]) + mean


def errors(pred, target):
    denominator = np.linalg.norm(target, axis=1)
    if np.any(denominator <= 1e-12):
        raise ValueError("Undefined relative L2 for zero target")
    e = np.linalg.norm(pred-target, axis=1)/denominator
    if not np.isfinite(e).all():
        raise ValueError("Nonfinite scientific metric")
    return e


def execute(data, candidate):
    model = fit(data, candidate)
    predictions = predict(model, data.val_x)
    e = errors(predictions, data.val_y)
    return {"model": model, "validation_mean": float(e.mean()), "validation_std": float(e.std()),
            "prediction_hash": array_hash(predictions), "tool_version": TOOL_VERSION}


def diagnose_inputs(data):
    x = features(data.fit_x, 5)
    z = (x-x.mean(0))/np.maximum(x.std(0), 1e-12)
    singular = np.linalg.svd(z, compute_uv=False)
    return {"input_variance": float(x.var()), "condition_number": float(singular[0]/max(singular[-1], 1e-12)),
            "spatial_roughness": float(np.mean(np.diff(data.fit_x, axis=1)**2)), "n": len(x)}


def diagnose_residuals(data, model):
    e = errors(predict(model, data.val_x), data.val_y)
    return {"group_errors": [float(a.mean()) for a in np.array_split(e, 4)], "std": float(e.std()),
            "n": len(e)}
