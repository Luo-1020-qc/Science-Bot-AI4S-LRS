"""Versioned G2 scientific specifications and host-built execution plans.

The scope is deliberately finite: two-group means, paired means and a frozen
mean/OLS prediction comparison. Scientific declarations are user supplied;
checking column structure cannot establish independence or randomization.
"""
from dataclasses import asdict, dataclass, field

from ...util import digest


@dataclass(frozen=True)
class ExperimentSpec:
    data_path: str
    research_question: str
    design: str
    response: str
    unit: str
    provenance: str
    sampling_note: str
    factor: str | None = None
    levels: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    randomization_note: str = "not_applicable"
    missing_policy: str = "reject"
    alpha: float = .05
    seed: int = 42
    schema_version: str = "experiment_spec_v1"

    def __post_init__(self):
        for name in ("data_path", "research_question", "response", "unit", "sampling_note", "randomization_note"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 2048:
                raise ValueError(f"实验设计缺少有效字段：{name}")
        if self.schema_version != "experiment_spec_v1" or self.design not in {"independent", "paired", "prediction"}:
            raise ValueError("G2 支持 independent、paired、prediction 三种设计")
        if self.provenance not in {"observational", "randomized", "synthetic"}:
            raise ValueError("请明确数据来源 observational / randomized / synthetic")
        if self.provenance == "randomized" and self.randomization_note == "not_applicable":
            raise ValueError("随机分配数据必须说明实际随机化方式，不能由模型补造")
        if self.provenance != "randomized" and self.randomization_note != "not_applicable":
            raise ValueError("非随机分配数据的 randomization_note 应为 not_applicable")
        if self.missing_policy not in {"reject", "drop_complete_case"}:
            raise ValueError("缺失值策略仅支持 reject / drop_complete_case")
        if type(self.alpha) not in {int, float} or not .001 <= self.alpha <= .2:
            raise ValueError("alpha 必须在0.001至0.2之间")
        if type(self.seed) is not int or not 0 <= self.seed <= 2**32-1:
            raise ValueError("seed 必须为0至2^32-1之间的整数")
        for name in ("features", "levels"):
            value = getattr(self, name)
            if (not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value)
                    or len(set(value)) != len(value)):
                raise ValueError(f"{name} 必须为不重复的字符串列表")
        if self.design == "prediction":
            if not 1 <= len(self.features) <= 20 or self.factor is not None or self.levels:
                raise ValueError("预测设计需要1至20个数值特征，且不使用 factor / levels")
            if self.response in self.features or self.unit in self.features or self.response == self.unit:
                raise ValueError("响应和实验单位列不能作为预测特征")
        elif (not isinstance(self.factor, str) or not self.factor.strip() or len(self.levels) != 2
              or self.features or len({self.factor, self.response, self.unit}) != 3):
            raise ValueError("均值比较需要不同的 factor / response / unit 列和两个明确水平，不接受特征列表")

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict:
            raise ValueError("ExperimentSpec 必须为 JSON 对象")
        try:
            return cls(**value)
        except TypeError as exc:
            raise ValueError("实验设计字段缺失或包含未注册参数："+str(exc)) from None

    def to_dict(self):
        return asdict(self)

    def protocol(self):
        prediction = self.design == "prediction"
        return {
            "goal": "out_of_sample_prediction" if prediction else "two_sided_mean_comparison",
            "hypothesis": "Validation MSE selects mean or OLS; evaluate winner once on frozen test" if prediction
                          else f"H0: E[{self.response}|{self.levels[0]}] - E[{self.response}|{self.levels[1]}] = 0",
            "methods": ["mean", "ols"] if prediction else ["welch_t" if self.design == "independent" else "paired_t"],
            "metric": "MSE" if prediction else "mean_difference, two-sided p, confidence interval",
            "preprocessing": "standardization fitted on train only; no imputation" if prediction else "no transformation",
            "split": {"train": .6, "validation": .2, "test": .2, "seed": self.seed} if prediction else None,
            "replication": "distinct declared units; random seed is not an independent replicate",
            "assumptions": (["independent, exchangeable units; no temporal or clustered splitting",
                             "linear model; finite numeric features; full-rank train matrix"] if prediction else
                            ["independent units; inspect outliers and distributional assumptions",
                             "normal approximation for group means" if self.design == "independent"
                             else "complete matched units; approximately normal within-unit differences"]),
            "sample_basis": self.sampling_note,
            "causal_claim": "not_established; provenance and randomization are user declarations",
            "stopping": "fixed plan, no hyperparameter search or test feedback",
            "failure": "pause at tool boundary; repair inputs with a new draft; no silent substitutions",
        }


@dataclass(frozen=True)
class ExecutionPlan:
    nodes: list[dict]
    spec_hash: str
    data_sha256: str
    schema_version: str = "execution_plan_v1"

    def __post_init__(self):
        if self.schema_version != "execution_plan_v1" or not 1 <= len(self.nodes) <= 8:
            raise ValueError("Invalid G2 execution plan version or length")
        known = set()
        tools = {"tabular_compare", "tabular_partition", "tabular_fit", "tabular_select", "tabular_evaluate", "tabular_report"}
        for node in self.nodes:
            if (type(node) is not dict or set(node) != {"id", "tool", "depends_on"}
                    or node["id"] in known or node["tool"] not in tools
                    or type(node["depends_on"]) is not list or not set(node["depends_on"]) <= known):
                raise ValueError("Plan has duplicate nodes, unregistered tools or invalid dependencies")
            known.add(node["id"])
        for value in (self.spec_hash, self.data_sha256):
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("Plan must bind spec and data SHA-256")

    @classmethod
    def build(cls, spec, data_sha256):
        names = ["partition", "fit", "select", "evaluate", "report"] if spec.design == "prediction" else ["compare", "report"]
        return cls([{"id": name, "tool": "tabular_"+name,
                     "depends_on": [names[i-1]] if i else []} for i, name in enumerate(names)],
                   digest(spec.to_dict()), data_sha256)

    def to_dict(self):
        return asdict(self)


SPEC_SCHEMA = {"type": "object", "properties": {
    **{key: {"type": "string", "minLength": 1, "maxLength": 2048} for key in
       ("data_path", "research_question", "response", "unit", "sampling_note", "randomization_note", "factor")},
    "design": {"type": "string", "enum": ["independent", "paired", "prediction"]},
    "provenance": {"type": "string", "enum": ["observational", "randomized", "synthetic"]},
    "missing_policy": {"type": "string", "enum": ["reject", "drop_complete_case"]},
    "alpha": {"type": "number", "minimum": .001, "maximum": .2},
    "seed": {"type": "integer", "minimum": 0, "maximum": 2**32-1},
    "levels": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
    "features": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
}, "required": ["data_path", "research_question", "design", "response", "unit", "provenance", "sampling_note"],
    "additionalProperties": False}
SPEC_SCHEMA["properties"]["randomization_note"]["description"] = "For observational/synthetic omit this field or use exactly not_applicable. For randomized data copy the user's actual randomization statement; never infer one."
SPEC_SCHEMA["properties"]["sampling_note"]["description"] = "Copy the sample-size/data-availability basis verbatim from the user; do not invent a power calculation."
