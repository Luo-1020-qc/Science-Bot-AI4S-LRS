"""Small public contracts for general routing and registered host tools."""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import re


@dataclass(frozen=True)
class TaskRequest:
    raw_text: str
    intent: str
    dataset: str | None = None
    input_paths: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    reason: str = ""
    schema_version: str = "general_task_v1"

    def __post_init__(self):
        if self.intent not in {"chat", "project_qa", "numeric", "clarify", "unsupported", "design"}:
            raise ValueError("Unknown general task intent")
        if self.dataset not in {None, "generated", "darcy"}:
            raise ValueError("Unknown numeric dataset")
        if self.intent == "numeric" and self.dataset is None:
            raise ValueError("Numeric tasks require an explicit dataset")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    output_schema: dict = field(default_factory=lambda: {"type": "object"})
    domain: str = "project"
    read_only: bool = True
    idempotent: bool = True
    preconditions: tuple[str, ...] = ()
    resource_estimate: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", self.name):
            raise ValueError("Invalid registered tool name")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Registered tools need a description")
        if (not isinstance(self.input_schema, dict) or self.input_schema.get("type") != "object"
                or self.input_schema.get("additionalProperties") is not False):
            raise ValueError("Tool input must be a closed object schema")
        if not isinstance(self.output_schema, dict):
            raise ValueError("Tool output schema must be an object")

    def to_dict(self):
        return deepcopy(asdict(self))

    def provider_schema(self):
        return {"type": "function", "function": {"name": self.name,
                "description": self.description, "parameters": deepcopy(self.input_schema)}}

