"""Two fitted candidates, validation-only branch selection, one sealed test."""
import copy
from dataclasses import dataclass
import re

from .environment import check_arguments, ToolError
from .plan_spec import PlanSpec, PlanNode, PlanValidationError, IDENTIFIER, REFERENCE, OUTPUTS, ACCEPTANCE

ROLES = ("inspect", "validate", "split", "fit_ridge", "fit_mean", "select", "evaluate", "report")
ROLE_TOOLS = dict(zip(ROLES, ("inspect_dataset", "validate_dataset", "split_dataset", "train_model", "train_model", "select_model", "evaluate_model", "write_report")))
ROLE_OUTPUTS = {role: OUTPUTS[tool] if tool != "select_model" else ["model_id"] for role, tool in ROLE_TOOLS.items()}
ROLE_ACCEPTANCE = {role: ACCEPTANCE[tool] if tool != "select_model" else {"status": "ok", "selected": True} for role, tool in ROLE_TOOLS.items()}
EDGES = (("inspect", "validate"), ("validate", "split"), ("split", "fit_ridge"), ("split", "fit_mean"),
         ("fit_ridge", "select"), ("fit_mean", "select"), ("select", "evaluate"), ("evaluate", "report"))


@dataclass(frozen=True)
class AdaptiveNode(PlanNode):
    role: str


@dataclass(frozen=True)
class AdaptivePlanSpec(PlanSpec):
    @classmethod
    def from_dict(cls, value):
        keys = {"schema_version", "plan_id", "version", "research_spec_hash", "parent_plan_hash", "max_tool_calls", "nodes"}
        node_keys = {"node_id", "tool", "arguments", "depends_on", "outputs", "acceptance", "role"}
        if not isinstance(value, dict) or set(value) != keys or not isinstance(value["nodes"], list) or len(value["nodes"]) != 8:
            raise PlanValidationError("planspec_v2 requires exact top-level fields and eight role-labelled nodes")
        if any(not isinstance(n, dict) or set(n) != node_keys for n in value["nodes"]):
            raise PlanValidationError("Every v2 node requires role and the standard node fields")
        return cls(**{k: copy.deepcopy(v) for k, v in value.items() if k != "nodes"}, nodes=[AdaptiveNode(**copy.deepcopy(n)) for n in value["nodes"]])

    def validate(self, spec, registry, host_tool_limit=12):
        if spec.model != "validation_select" or self.schema_version != "planspec_v2" or self.research_spec_hash != spec.spec_hash:
            raise PlanValidationError("v2 plan must bind a confirmed validation_select specification")
        if not isinstance(self.plan_id, str) or not IDENTIFIER.fullmatch(self.plan_id) or type(self.version) is not int or self.version < 1:
            raise PlanValidationError("Invalid plan ID or version")
        if (self.version == 1 and self.parent_plan_hash is not None) or (self.version > 1 and (not isinstance(self.parent_plan_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", self.parent_plan_hash))):
            raise PlanValidationError("Invalid parent plan hash")
        if type(self.max_tool_calls) is not int or not 8 <= self.max_tool_calls <= host_tool_limit:
            raise PlanValidationError("v2 tool budget must fit the host limit and eight required operations")
        schemas = {t["name"]: t["parameters"]["properties"] for t in registry}
        nodes, roles = {}, {}
        for n in self.nodes:
            if not isinstance(n.node_id, str) or not IDENTIFIER.fullmatch(n.node_id) or n.node_id in nodes:
                raise PlanValidationError("Invalid/duplicate node ID")
            if not isinstance(n.role, str) or n.role not in ROLES or n.role in roles or n.tool != ROLE_TOOLS[n.role] or n.tool not in schemas:
                raise PlanValidationError("Each v2 scientific role must occur exactly once with its registered tool")
            if type(n.depends_on) is not list or any(type(d) is not str for d in n.depends_on) or len(set(n.depends_on)) != len(n.depends_on):
                raise PlanValidationError("Invalid dependencies")
            expected = ROLE_ACCEPTANCE[n.role]
            if n.outputs != ROLE_OUTPUTS[n.role] or type(n.outputs) is not list or type(n.acceptance) is not dict or n.acceptance.keys() != expected.keys() or any(type(n.acceptance[k]) is not type(v) or n.acceptance[k] != v for k, v in expected.items()):
                raise PlanValidationError(f"Invalid outputs/acceptance for role {n.role}")
            nodes[n.node_id], roles[n.role] = n, n
        if set(roles) != set(ROLES):
            raise PlanValidationError("Missing v2 role")
        ancestry, visiting = {}, set()
        def visit(key):
            if key in ancestry:
                return ancestry[key]
            if key not in nodes or key in visiting:
                raise PlanValidationError("Unknown dependency or cycle")
            visiting.add(key)
            found = set()
            for parent in nodes[key].depends_on:
                found.add(parent)
                found.update(visit(parent))
            visiting.remove(key)
            ancestry[key] = found
            return found
        for key in nodes:
            visit(key)
        if any(roles[a].node_id not in ancestry[roles[b].node_id] for a, b in EDGES):
            raise PlanValidationError("Missing candidate-selection scientific precedence")
        static = {"inspect": {"dataset_name": spec.dataset_name}, "validate": {"target": spec.target},
            "split": {"target": spec.target, "train_fraction": spec.train_fraction, "seed": spec.split_seed},
            "fit_ridge": {"model": "ridge_field"}, "fit_mean": {"model": "mean_field"}, "select": {}, "evaluate": {}, "report": {}}
        refs = {"validate": {"dataset_id": (("inspect",), "dataset_id")}, "split": {"dataset_id": (("inspect", "validate"), "dataset_id")},
            "fit_ridge": {"split_id": (("split",), "split_id")}, "fit_mean": {"split_id": (("split",), "split_id")},
            "select": {"ridge_model_id": (("fit_ridge",), "model_id"), "mean_model_id": (("fit_mean",), "model_id")},
            "evaluate": {"model_id": (("select",), "model_id")}, "report": {"evaluation_id": (("evaluate",), "evaluation_id")}}
        for n in self.nodes:
            if type(n.arguments) is not dict or set(n.arguments) != set(schemas[n.tool]):
                raise PlanValidationError("Invalid v2 tool arguments")
            if any(type(n.arguments[k]) is bool or n.arguments[k] != value for k, value in static[n.role].items()):
                raise PlanValidationError("v2 action contradicts confirmed research specification")
            literal = dict(n.arguments)
            for key, (producer_roles, field) in refs.get(n.role, {}).items():
                match = REFERENCE.fullmatch(n.arguments[key]) if isinstance(n.arguments[key], str) else None
                if not match:
                    raise PlanValidationError("v2 IDs must use observed output references")
                producer, output = match.groups()
                if producer not in ancestry[n.node_id] or nodes[producer].role not in producer_roles or output != field:
                    raise PlanValidationError(f"Invalid v2 input binding for {n.role}.{key}")
                literal[key] = "observed_id"
            try:
                check_arguments(schemas[n.tool], literal)
            except ToolError:
                raise PlanValidationError("v2 tool schema violation") from None
        return {"status": "passed", "plan_hash": self.plan_hash, "nodes": 8,
                "checks": ["spec_binding", "acyclic", "both_candidate_fits", "validation_only_selection", "single_selected_test", "budget", "typed_bindings"]}


def selection_control_plan(spec, version=1, parent_plan_hash=None, plan_id="science_plan"):
    args = {"inspect": {"dataset_name": spec.dataset_name}, "validate": {"dataset_id": "$inspect.dataset_id", "target": spec.target},
        "split": {"dataset_id": "$validate.dataset_id", "target": spec.target, "train_fraction": spec.train_fraction, "seed": spec.split_seed},
        "fit_ridge": {"split_id": "$split.split_id", "model": "ridge_field"}, "fit_mean": {"split_id": "$split.split_id", "model": "mean_field"},
        "select": {"ridge_model_id": "$fit_ridge.model_id", "mean_model_id": "$fit_mean.model_id"},
        "evaluate": {"model_id": "$select.model_id"}, "report": {"evaluation_id": "$evaluate.evaluation_id"}}
    nodes = [AdaptiveNode(role, ROLE_TOOLS[role], args[role], [a for a, b in EDGES if b == role],
             copy.deepcopy(ROLE_OUTPUTS[role]), copy.deepcopy(ROLE_ACCEPTANCE[role]), role) for role in ROLES]
    return AdaptivePlanSpec("planspec_v2", plan_id, version, spec.spec_hash, parent_plan_hash, 8, nodes)
