import copy
import unittest

from rut_science.benchmark import build_tasks
from rut_science.environment import ScientificMLEnvironment
from rut_science.plan_spec import PlanSpec, PlanValidationError, accept_result, public_control_plan, resolve_node
from rut_science.research_spec import ResearchSpec


class PlanSpecTests(unittest.TestCase):
    def setUp(self):
        self.env = ScientificMLEnvironment()
        self.spec = ResearchSpec.from_task(build_tasks()[0], self.env.snapshot())
        self.plan = public_control_plan(self.spec)

    def test_valid_plan_and_permuted_storage_order(self):
        self.assertEqual(self.plan.validate(self.spec, self.env.available_tools())["status"], "passed")
        value = self.plan.to_dict()
        value["nodes"].reverse()
        self.assertEqual(PlanSpec.from_dict(value).validate(self.spec, self.env.available_tools())["status"], "passed")

    def test_invalid_plans_rejected_before_any_effects(self):
        cases = []
        for kind in ("cycle", "missing_dependency", "literal_id", "unknown_output", "wrong_model", "bad_enum", "forbidden_tool",
                     "duplicate_id", "duplicate_tool", "wrong_spec", "budget", "extra_argument", "bad_type", "acceptance", "outputs_object", "extra_field"):
            value = self.plan.to_dict()
            nodes = value["nodes"]
            if kind == "cycle":
                nodes[0]["depends_on"] = ["report"]
            elif kind == "missing_dependency":
                nodes[2]["depends_on"] = ["inspect"]
            elif kind == "literal_id":
                nodes[1]["arguments"]["dataset_id"] = "ds_1"
            elif kind == "unknown_output":
                nodes[1]["arguments"]["dataset_id"] = "$inspect.private_label"
            elif kind == "wrong_model":
                nodes[3]["arguments"]["model"] = "mean"
            elif kind == "bad_enum":
                nodes[3]["arguments"]["model"] = "ridge"
            elif kind == "forbidden_tool":
                nodes[5]["tool"] = "edit_test_labels"
            elif kind == "duplicate_id":
                nodes[1]["node_id"] = "inspect"
            elif kind == "duplicate_tool":
                nodes[1]["tool"] = "inspect_dataset"
            elif kind == "wrong_spec":
                value["research_spec_hash"] = "0"*64
            elif kind == "budget":
                value["max_tool_calls"] = 100
            elif kind == "extra_argument":
                nodes[2]["arguments"]["shell"] = "arbitrary_code"
            elif kind == "bad_type":
                nodes[2]["arguments"]["seed"] = True
            elif kind == "acceptance":
                nodes[1]["acceptance"]["valid"] = 1
            elif kind == "outputs_object":
                nodes[0]["outputs"] = {"dataset_id": "$inspect.dataset_id"}
            else:
                value["hidden_state"] = {}
            cases.append((kind, value))
        initial = self.env.snapshot()
        for kind, value in cases:
            with self.subTest(kind=kind), self.assertRaises(PlanValidationError):
                PlanSpec.from_dict(value).validate(self.spec, self.env.available_tools())
            self.assertEqual(initial, self.env.snapshot())

    def test_binding_requires_successful_observed_output(self):
        node = self.plan.nodes[1]
        with self.assertRaises(PlanValidationError):
            resolve_node(node, {})
        with self.assertRaises(PlanValidationError):
            resolve_node(node, {"inspect": {"status": "error", "dataset_id": "x"}})
        self.assertEqual(resolve_node(node, {"inspect": {"status": "ok", "dataset_id": "seen"}})["dataset_id"], "seen")

    def test_split_can_reference_validated_dataset_identity(self):
        value = self.plan.to_dict()
        value["nodes"][2]["arguments"]["dataset_id"] = "$validate.dataset_id"
        self.assertEqual(PlanSpec.from_dict(value).validate(self.spec, self.env.available_tools())["status"], "passed")

    def test_acceptance_boolean_is_not_integer_and_output_is_required(self):
        node = self.plan.nodes[1]
        self.assertFalse(accept_result(node, {"status": "ok", "valid": 1, "dataset_id": "d"}))
        self.assertFalse(accept_result(node, {"status": "ok", "valid": True}))
        self.assertTrue(accept_result(node, {"status": "ok", "valid": True, "dataset_id": "d"}))

    def test_revision_metadata_and_safe_identifiers(self):
        for fields in ({"plan_id": "../escape"}, {"version": True}, {"parent_plan_hash": "x"}):
            value = self.plan.to_dict() | fields
            with self.assertRaises(PlanValidationError):
                PlanSpec.from_dict(value).validate(self.spec, self.env.available_tools())
