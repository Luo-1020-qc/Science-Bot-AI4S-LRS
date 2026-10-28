"""Policies consume only public observations. No access to environments."""
import json
from pathlib import Path
import numpy as np
from .contracts import K_MAX
from ..util import digest

KINDS = ("fit_mean", "fit_ridge", "diagnose_inputs", "diagnose_residuals", "retry", "submit_best", "abstain")
FEATURE_VERSION = "structured_shared_candidates_v1"
GLOBAL_DIM, CANDIDATE_DIM, HISTORY_DIM = 24, 20, 12


def _finite(value, default=0):
    return float(np.clip(value if value is not None else default, -1e6, 1e6))


def encode(obs, ablation=None):
    b, d = obs["budget"], obs["dataset_public"]
    successful = [e for e in obs["experiments"] if e["observed"]]
    best = min([e["validation_mean"] for e in successful], default=1)
    diag = obs["diagnostics"]
    history = np.zeros((13, HISTORY_DIM), np.float32)
    for i, e in enumerate(obs["experiments"]):
        p = e["parameters"]
        history[i] = [e["kind"] == "fit_mean", p.get("fidelity") == "full", p.get("feature_grid", 0)/5,
                      np.log10(p.get("alpha", 1))/2, e["status"] == "untried", e["observed"],
                      e["status"] == "failed", _finite(e["validation_mean"]), _finite(e["validation_std"]),
                      e["attempts"]/2, 0, 0]
    global_features = np.asarray([
        obs["goal"]["quality_threshold"], b["compute_units_remaining"]/14, b["compute_units_limit"]/14,
        b["tool_attempts_remaining"]/12, b["decision_steps_remaining"]/16,
        b["llm_tokens_remaining"]/160000, b["llm_requests_remaining"]/24,
        b["active_seconds_remaining"]/600, d["n_fit_pool"]/128, d["n_search_val"]/32,
        d["output_dim"]/225, best, len(successful)/13, bool(diag),
        np.log1p(diag.get("condition_number", 0))/10, diag.get("input_variance", 0),
        diag.get("spatial_roughness", 0), sum(e["status"] == "failed" for e in obs["experiments"])/13,
        len(obs["residuals"])/13, len(obs["history"])/16,
        sum(h["kind"] == "retry" for h in obs["history"])/2, 0, 0, 0], np.float32)
    candidate_features = np.zeros((K_MAX, CANDIDATE_DIM), np.float32)
    by_ref = {e["candidate_ref"]: e for e in obs["experiments"]}
    for i, c in enumerate(obs["candidates"]):
        p, e = c["parameters"], by_ref.get(c["id"], {})
        candidate_features[i] = [*[c["kind"] == k for k in KINDS],
            c["cost"]/4, p.get("fidelity") == "full", p.get("feature_grid", 0)/5,
            np.log10(p.get("alpha", 1))/2, e.get("status") == "untried", e.get("observed", False),
            e.get("status") == "failed", _finite(e.get("validation_mean")), _finite(e.get("validation_std")),
            e.get("attempts", 0)/2, c["legal"], p.get("model_id") == obs["incumbent"] and obs["incumbent"] is not None, 0]
    if ablation == "no_budget":
        global_features[1:8] = 0
    elif ablation == "no_history":
        history[:] = 0; global_features[11:21] = 0; candidate_features[:, 11:17] = 0
    elif ablation == "no_diagnostics":
        global_features[13:17] = 0
    return {"global": global_features, "history": history, "candidates": candidate_features,
            "mask": np.asarray(obs["mask"], bool)}


class RulePolicy:
    def __init__(self, mode="adaptive", seed=0):
        self.mode, self.rng = mode, np.random.default_rng(seed)
        self.identity = digest({"rule": mode, "version": 1})

    def choose(self, observation):
        obs = observation
        legal = {c["id"]: c for c in obs["candidates"] if c["legal"]}
        if self.mode == "random":
            return self.rng.choice(list(legal)).item()
        completed = [e for e in obs["experiments"] if e["observed"]]
        best = min([e["validation_mean"] for e in completed], default=1e9)
        if "submit_best" in legal and best <= obs["goal"]["quality_threshold"]*0.90:
            return "submit_best"
        if "retry" in legal:
            return "retry"
        if self.mode == "search":
            fits = [c for c in legal.values() if c["kind"] in {"fit_mean", "fit_ridge"}]
            return self.rng.choice([c["id"] for c in fits]).item() if fits else ("submit_best" if completed else "abstain")
        if self.mode == "dense":
            order = ["ridge_full_5_1", "ridge_full_5_10", "mean", "ridge_half_3_1"]
        elif self.mode == "adaptive" and completed and not obs["diagnostics"] and "diagnose_inputs" in legal:
            return "diagnose_inputs"
        elif self.mode == "adaptive" and obs["diagnostics"]:
            diag = obs["diagnostics"]
            if diag["condition_number"] > 15:
                order = ["ridge_full_5_10", "ridge_half_3_1", "ridge_full_5_1"]
            elif diag["spatial_roughness"] > 0.8:
                order = ["ridge_half_5_1", "ridge_full_5_1", "ridge_half_3_1"]
            else:
                order = ["ridge_half_3_1", "ridge_full_5_1", "ridge_full_5_10"]
        else:
            order = ["mean", "ridge_half_3_1", "ridge_full_5_1", "ridge_half_5_1", "ridge_full_5_10"]
        for name in order:
            if name in legal:
                return name
        return "submit_best" if completed else "abstain"


def make_network():
    import torch
    from torch import nn

    class ActorCritic(nn.Module):
        def __init__(self):
            super().__init__()
            self.history_encoder = nn.Sequential(nn.Linear(HISTORY_DIM, 32), nn.Tanh())
            self.context = nn.Sequential(nn.Linear(GLOBAL_DIM+64, 128), nn.Tanh(), nn.Linear(128, 128), nn.Tanh())
            self.actor = nn.Sequential(nn.Linear(128+CANDIDATE_DIM, 128), nn.Tanh(), nn.Linear(128, 1))
            self.critic = nn.Sequential(nn.Linear(128, 128), nn.Tanh(), nn.Linear(128, 1))

        def forward(self, batch):
            history = self.history_encoder(batch["history"])
            context = self.context(torch.cat([batch["global"], history.mean(1), history.max(1).values], -1))
            candidates = batch["candidates"]
            logits = self.actor(torch.cat([context[:, None, :].expand(-1, K_MAX, -1), candidates], -1)).squeeze(-1)
            logits = logits.masked_fill(~batch["mask"], -1e9)
            return torch.distributions.Categorical(logits=logits), self.critic(context).squeeze(-1)

    return ActorCritic()


def tensor_batch(rows):
    import torch
    return {k: torch.from_numpy(np.stack([r[k] for r in rows])) for k in rows[0]}


class LearnedPolicy:
    def __init__(self, folder, ablation=None):
        import torch
        from ..darcy_workflow import file_hash
        self.folder = Path(folder)
        meta = json.loads((self.folder/"manifest.json").read_text(encoding="utf-8"))
        if meta["feature_version"] != FEATURE_VERSION or meta["k_max"] != K_MAX:
            raise ValueError("Incompatible policy schema")
        from .contracts import catalog
        from .numerics import TOOL_VERSION
        if meta["catalog_hash"] != digest(catalog()) or meta["tool_version"] != TOOL_VERSION:
            raise ValueError("Policy catalog or numerical protocol mismatch")
        if file_hash(self.folder/"weights.pt") != meta["weights_hash"]:
            raise ValueError("Policy weight hash mismatch")
        self.network = make_network()
        self.network.load_state_dict(torch.load(self.folder/"weights.pt", map_location="cpu", weights_only=True))
        self.network.eval()
        self.identity, self.ablation = meta["weights_hash"], ablation or meta.get("ablation")
        self.manifest = meta

    def choose(self, observation):
        import torch
        if self.ablation == "no_diagnostics":
            import copy
            observation = copy.deepcopy(observation)
            for i, candidate in enumerate(observation["candidates"]):
                if candidate["kind"] in {"diagnose_inputs", "diagnose_residuals"}:
                    observation["mask"][i] = False
                    candidate["legal"] = False
        with torch.no_grad():
            distribution, _ = self.network(tensor_batch([encode(observation, self.ablation)]))
            index = int(distribution.logits.argmax(-1).item())
        return observation["candidates"][index]["id"]
