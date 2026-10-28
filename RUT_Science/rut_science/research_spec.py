"""Public research contracts, confirmed by the host/user rather than the model."""
from dataclasses import asdict, dataclass, field
import math
import re

from .util import digest


@dataclass(frozen=True)
class ResearchSpec:
    dataset_name: str
    dataset_hash: str
    target: str
    unit: str
    model: str
    train_fraction: float
    split_seed: int
    validation_fraction: float = 0.2
    split_policy: str = "random_three_way"
    metric: str = "MAE"
    max_train_calls: int = 1
    max_test_calls: int = 1
    model_parameters: dict = field(default_factory=dict)
    schema_version: str = "research_spec_v1"

    def __post_init__(self):
        if self.schema_version != "research_spec_v1":
            raise ValueError("Unsupported ResearchSpec version")
        if any(not isinstance(v, str) or not v.strip() for v in
               (self.dataset_name, self.target, self.unit, self.model)):
            raise ValueError("Research fields must be nonempty strings")
        if not isinstance(self.dataset_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", self.dataset_hash):
            raise ValueError("A pinned SHA-256 dataset identity is required")
        for value in (self.train_fraction, self.validation_fraction):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Fractions must be finite numbers")
        if type(self.split_seed) is not int or self.split_seed < 0:
            raise ValueError("split_seed must be a nonnegative integer")
        if type(self.max_train_calls) is not int or type(self.max_test_calls) is not int or (
                self.max_train_calls != (2 if self.model == "validation_select" else 1) or self.max_test_calls != 1):
            raise ValueError("Fit budget must match the method: two for validation_select, otherwise one; one sealed test")
        if self.validation_fraction != 0.2:
            raise ValueError("Validation fraction is fixed at 0.2")
        if self.split_policy == "random_three_way":
            if not 0.4 <= self.train_fraction <= 0.7 or self.model not in {"linear", "mean"} or self.metric != "MAE":
                raise ValueError("Invalid synthetic baseline protocol")
            if self.model_parameters:
                raise ValueError("Synthetic baselines have no configurable model parameters")
        elif self.split_policy == "published_train_test":
            if self.train_fraction != 0.8 or self.model not in {"ridge_field", "mean_field", "validation_select"} or self.metric != "mean_relative_l2":
                raise ValueError("Invalid Darcy baseline protocol")
            if set(self.model_parameters) != {"alpha"} or type(self.model_parameters["alpha"]) not in (int, float) or (
                    not math.isfinite(self.model_parameters["alpha"]) or self.model_parameters["alpha"] <= 0):
                raise ValueError("Darcy requires a fixed positive alpha")
        else:
            raise ValueError("Unknown split policy")

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def spec_hash(self) -> str:
        return digest(self.to_dict())

    @classmethod
    def from_task(cls, task, initial: dict):
        """For authored public user fixtures only; does not read oracle or gold."""
        data = next(d for d in initial["datasets"].values() if d["name"] == task.dataset_name)
        return cls(task.dataset_name, digest(data), task.target, task.unit, task.model,
                   task.train_fraction, task.split_seed)
