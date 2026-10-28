"""Versioned contracts. Logical CU are not seconds or currency."""
from dataclasses import asdict, dataclass
import math
from . import VERSION
from ..util import digest

K_MAX = 24
CATALOG_VERSION = "mean_ridge_grid_v1"


@dataclass(frozen=True)
class BudgetedResearchSpec:
    dataset: str = "generated"
    task_seed: int = 11
    group: int = 0
    split: str = "train"
    quality_threshold: float = 0.20
    compute_units: int = 10
    tool_attempts: int = 12
    decision_steps: int = 16
    llm_requests: int = 24
    llm_tokens: int = 160000
    active_seconds: int = 600
    fault_rate: float = 0.0
    schema_version: str = "budgeted_research_v1"

    def __post_init__(self):
        if self.dataset not in {"generated", "darcy"} or self.split not in {"train", "dev", "test", "demo"}:
            raise ValueError("Unknown dataset or split")
        for key in ("task_seed", "group", "compute_units", "tool_attempts", "decision_steps", "llm_requests", "llm_tokens", "active_seconds"):
            v = getattr(self, key)
            if type(v) is not int or v < (0 if key in {"task_seed", "group"} else 1):
                raise ValueError(f"Invalid {key}")
        if not math.isfinite(self.quality_threshold) or not 0 < self.quality_threshold <= 10:
            raise ValueError("Invalid engineering quality threshold")
        if not math.isfinite(self.fault_rate) or not 0 <= self.fault_rate <= 0.5:
            raise ValueError("Invalid fixture fault rate")
        if self.schema_version != "budgeted_research_v1":
            raise ValueError("Unsupported schema")

    def to_dict(self):
        return asdict(self)


def catalog():
    result = [{"id": "mean", "kind": "fit_mean", "parameters": {}, "cost": 1}]
    for fidelity in ("half", "full"):
        for grid in (3, 5):
            for alpha in (0.1, 1.0, 10.0):
                result.append({"id": f"ridge_{fidelity}_{grid}_{alpha:g}", "kind": "fit_ridge",
                               "parameters": {"fidelity": fidelity, "feature_grid": grid, "alpha": alpha},
                               "cost": 2 if fidelity == "half" else 4})
    return result


def confirmation_hash(spec, data_identity, policy_identity):
    return digest({"spec": spec.to_dict(), "data": data_identity, "catalog": catalog(),
                   "policy": policy_identity, "resource_policy": "reserve_finalize_2cu_2tools_1llm_v1",
                   "version": VERSION})


def validate_proposals(proposals):
    """Normalize LLM proposals using only the frozen registered domain."""
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= 13:
        raise ValueError("Candidate supply must contain 1..13 fits")
    allowed, selected = catalog(), []
    for proposal in proposals:
        if not isinstance(proposal, dict) or not isinstance(proposal.get("parameters"), dict):
            raise ValueError("Each candidate needs registered parameters")
        if any(isinstance(v, bool) for v in proposal["parameters"].values()):
            raise ValueError("Boolean parameters cannot alias numeric parameters")
        matches = [c for c in allowed if c["kind"] == proposal.get("template_id")
                   and c["parameters"] == proposal.get("parameters")]
        if len(matches) != 1 or matches[0]["id"] in selected:
            raise ValueError("Unknown, duplicate or out-of-domain candidate")
        selected.append(matches[0]["id"])
    return selected
