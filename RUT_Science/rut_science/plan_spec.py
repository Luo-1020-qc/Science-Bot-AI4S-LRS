"""Strict public plan contracts, independent of evaluator gold or private state."""
import copy
from dataclasses import asdict, dataclass
import re

from .environment import ToolError, check_arguments
from .research_spec import ResearchSpec
from .util import digest

TOOLS = ("inspect_dataset", "validate_dataset", "split_dataset", "train_model", "evaluate_model", "write_report")
OUTPUTS = {name: [field] for name, field in zip(TOOLS,
          ("dataset_id", "dataset_id", "split_id", "model_id", "evaluation_id", "report_id"))}
ACCEPTANCE = {name: {"status": "ok"} for name in TOOLS}
ACCEPTANCE["validate_dataset"] = {"status": "ok", "valid": True}
ACCEPTANCE["evaluate_model"] = {"status": "ok", "sealed": True}
ACCEPTANCE["write_report"] = {"status": "ok", "evidence_complete": True}
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")
REFERENCE = re.compile(r"^\$([A-Za-z][A-Za-z0-9_]{0,40})\.([A-Za-z][A-Za-z0-9_]*)$")


class PlanValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PlanNode:
    node_id: str
    tool: str
    arguments: dict
    depends_on: list[str]
    outputs: list[str]
    acceptance: dict


@dataclass(frozen=True)
class PlanSpec:
    schema_version: str
    plan_id: str
    version: int
    research_spec_hash: str
    parent_plan_hash: str | None
    max_tool_calls: int
    nodes: list[PlanNode]

    @classmethod
    def from_dict(cls, value: dict):
        if isinstance(value, dict) and value.get("schema_version") == "planspec_v2":
            from .adaptive_plan_spec import AdaptivePlanSpec
            return AdaptivePlanSpec.from_dict(value)
        keys = {"schema_version", "plan_id", "version", "research_spec_hash", "parent_plan_hash", "max_tool_calls", "nodes"}
        node_keys = {"node_id", "tool", "arguments", "depends_on", "outputs", "acceptance"}
        if not isinstance(value, dict) or set(value) != keys or not isinstance(value["nodes"], list):
            raise PlanValidationError("Plan must match the exact planspec_v1 fields")
        if len(value["nodes"]) != 6:
            raise PlanValidationError("This six-stage scientific protocol requires exactly six nodes")
        nodes = []
        for item in value["nodes"]:
            if not isinstance(item, dict) or set(item) != node_keys:
                raise PlanValidationError("Node fields must match the documented schema")
            nodes.append(PlanNode(**copy.deepcopy(item)))
        return cls(**{k: copy.deepcopy(v) for k, v in value.items() if k != "nodes"}, nodes=nodes)

    def to_dict(self):
        return asdict(self)

    @property
    def plan_hash(self):
        return digest(self.to_dict())

    def validate(self, spec: ResearchSpec, registry: list[dict], host_tool_limit=12):
        if self.schema_version != "planspec_v1" or not isinstance(self.plan_id, str) or not IDENTIFIER.fullmatch(self.plan_id):
            raise PlanValidationError("Invalid plan version or identifier")
        if type(self.version) is not int or self.version < 1 or self.research_spec_hash != spec.spec_hash:
            raise PlanValidationError("Plan must bind the confirmed ResearchSpec and a positive version")
        if (self.version == 1 and self.parent_plan_hash is not None) or (self.version > 1 and (
                not isinstance(self.parent_plan_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", self.parent_plan_hash))):
            raise PlanValidationError("A revision must reference its parent plan hash")
        if type(self.max_tool_calls) is not int or not 6 <= self.max_tool_calls <= host_tool_limit:
            raise PlanValidationError("Plan tool budget must fit the trusted host limit")
        schemas = {t["name"]: t["parameters"]["properties"] for t in registry}
        index = {}
        by_tool = {}
        for node in self.nodes:
            if not isinstance(node.node_id, str) or not IDENTIFIER.fullmatch(node.node_id) or node.node_id in index:
                raise PlanValidationError("Node identifiers must be unique safe identifiers")
            if not isinstance(node.tool, str) or node.tool not in TOOLS or node.tool not in schemas or node.tool in by_tool:
                raise PlanValidationError("Only one node for each registered scientific stage is allowed")
            if not isinstance(node.depends_on, list) or any(not isinstance(d, str) for d in node.depends_on) or len(set(node.depends_on)) != len(node.depends_on):
                raise PlanValidationError("Node dependencies must be a unique list of node identifiers")
            expected_acceptance = ACCEPTANCE[node.tool]
            if type(node.outputs) is not list or node.outputs != OUTPUTS[node.tool]:
                raise PlanValidationError(f"{node.tool}.outputs must be a JSON string array exactly {OUTPUTS[node.tool]}, not a mapping")
            if (type(node.acceptance) is not dict or node.acceptance.keys() != expected_acceptance.keys() or
                    any(type(node.acceptance[k]) is not type(v) or node.acceptance[k] != v for k, v in expected_acceptance.items())):
                raise PlanValidationError(f"{node.tool}.acceptance must match exactly {expected_acceptance}, including value types")
            index[node.node_id], by_tool[node.tool] = node, node
        if set(by_tool) != set(TOOLS):
            raise PlanValidationError("Missing mandatory scientific stage")
        ancestors = {}
        visiting = set()
        def visit(node_id):
            if node_id in ancestors:
                return ancestors[node_id]
            if node_id in visiting:
                raise PlanValidationError("Plan contains a dependency cycle")
            if node_id not in index:
                raise PlanValidationError("Plan references an unknown dependency")
            visiting.add(node_id)
            found = set()
            for dependency in index[node_id].depends_on:
                found.add(dependency)
                found.update(visit(dependency))
            visiting.remove(node_id)
            ancestors[node_id] = found
            return found
        for node_id in index:
            visit(node_id)
        for predecessor, successor in zip(TOOLS, TOOLS[1:]):
            if by_tool[predecessor].node_id not in ancestors[by_tool[successor].node_id]:
                raise PlanValidationError(f"Required scientific precedence missing: {predecessor} -> {successor}")
        static = {"inspect_dataset": {"dataset_name": spec.dataset_name},
                  "validate_dataset": {"target": spec.target},
                  "split_dataset": {"target": spec.target, "train_fraction": spec.train_fraction, "seed": spec.split_seed},
                  "train_model": {"model": spec.model}, "evaluate_model": {}, "write_report": {}}
        required_refs = {"validate_dataset": {"dataset_id": (("inspect_dataset",), "dataset_id")},
                         "split_dataset": {"dataset_id": (("inspect_dataset", "validate_dataset"), "dataset_id")},
                         "train_model": {"split_id": (("split_dataset",), "split_id")},
                         "evaluate_model": {"model_id": (("train_model",), "model_id")},
                         "write_report": {"evaluation_id": (("evaluate_model",), "evaluation_id")}}
        for node in self.nodes:
            if not isinstance(node.arguments, dict) or set(node.arguments) != set(schemas[node.tool]):
                raise PlanValidationError("Tool arguments must match the exact registered schema")
            for key, expected in static[node.tool].items():
                if node.arguments[key] != expected or type(node.arguments[key]) is bool:
                    raise PlanValidationError(f"Plan parameter {node.tool}.{key} differs from confirmed ResearchSpec")
            literal = {}
            for key, value in node.arguments.items():
                if key in required_refs.get(node.tool, {}):
                    match = REFERENCE.fullmatch(value) if isinstance(value, str) else None
                    if not match:
                        raise PlanValidationError("Entity IDs must be references to observed producer outputs, not literals")
                    producer, output = match.groups()
                    producer_tools, producer_output = required_refs[node.tool][key]
                    if (producer not in ancestors[node.node_id] or index[producer].tool not in producer_tools or
                            output != producer_output or output not in index[producer].outputs):
                        raise PlanValidationError(f"{node.tool}.{key} must reference an ancestor {producer_output} from {producer_tools}")
                    literal[key] = "observed_id"
                else:
                    literal[key] = value
            try:
                check_arguments(schemas[node.tool], literal)
            except ToolError:
                raise PlanValidationError("Plan violates tool argument types, enum or bounds") from None
        return {"status": "passed", "plan_hash": self.plan_hash, "nodes": len(index),
                "checks": ["spec_binding", "acyclic", "scientific_precedence", "typed_output_references", "exact_parameters", "budget", "acceptance"]}


def resolve_node(node: PlanNode, results: dict) -> dict:
    arguments = {}
    for key, value in node.arguments.items():
        match = REFERENCE.fullmatch(value) if isinstance(value, str) else None
        if match:
            producer, output = match.groups()
            if producer not in results or results[producer].get("status") != "ok" or output not in results[producer]:
                raise PlanValidationError("Input producer has not supplied a successful observed output")
            arguments[key] = results[producer][output]
        else:
            arguments[key] = value
    return arguments


def accept_result(node: PlanNode, result: dict) -> bool:
    return (isinstance(result, dict) and all(type(result.get(k)) is type(v) and result.get(k) == v for k, v in node.acceptance.items())
            and all(isinstance(result.get(k), str) and bool(result[k]) for k in node.outputs))


def public_control_plan(spec: ResearchSpec, version=1, parent_plan_hash=None, plan_id="science_plan") -> PlanSpec:
    """Offline harness control, constructed solely from public specification."""
    if spec.model == "validation_select":
        from .adaptive_plan_spec import selection_control_plan
        return selection_control_plan(spec, version, parent_plan_hash, plan_id)
    names = ("inspect", "validate", "split", "train", "evaluate", "report")
    arguments = [{"dataset_name": spec.dataset_name}, {"dataset_id": "$inspect.dataset_id", "target": spec.target},
                 {"dataset_id": "$inspect.dataset_id", "target": spec.target, "train_fraction": spec.train_fraction, "seed": spec.split_seed},
                 {"split_id": "$split.split_id", "model": spec.model}, {"model_id": "$train.model_id"},
                 {"evaluation_id": "$evaluate.evaluation_id"}]
    nodes = [PlanNode(node_id, tool, args, [] if i == 0 else [names[i-1]], copy.deepcopy(OUTPUTS[tool]), copy.deepcopy(ACCEPTANCE[tool]))
             for i, (node_id, tool, args) in enumerate(zip(names, TOOLS, arguments))]
    return PlanSpec("planspec_v1", plan_id, version, spec.spec_hash, parent_plan_hash, 6, nodes)
