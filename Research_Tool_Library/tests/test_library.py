from copy import deepcopy
import inspect
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from catalog import CATALOG
from core import Library, ROOT, digest
from demo import run_demo


class ToolLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = ROOT/"test_fixture"
        cls.summary = run_demo("cvit", cls.fixture)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        shutil.copytree(self.fixture/"objects", self.folder/"objects")
        self.library = Library(self.folder)
        self.s = deepcopy(self.summary)

    def call(self, name, **kwargs):
        return self.library.call(name, kwargs)["result"]

    def test_catalog_identifies_implemented_and_disabled_tools_with_closed_inputs(self):
        self.assertEqual(len(CATALOG), 45)
        self.assertEqual(sum(t["implementation"] == "offline_implemented" for t in CATALOG), 20)
        self.assertEqual(len({t["name"] for t in CATALOG}), len(CATALOG))
        for tool in CATALOG:
            self.assertFalse(tool["input_schema"]["additionalProperties"])
            if tool["implementation"] == "offline_implemented":
                parameters = set(inspect.signature(getattr(self.library, tool["name"])).parameters)
                self.assertEqual(parameters, set(tool["input_schema"]["required"]))

    def test_actual_demo_performs_review_repair_and_preserves_mock_scope(self):
        self.assertTrue(self.s["passed"])
        self.assertIn("analysis_model", self.s["initial_findings"])
        self.assertFalse(self.s["real_scientific_claim_verified"])
        tools = [t["tool"] for t in self.s["tool_calls"]]
        self.assertLess(tools.index("plan_review"), tools.index("review_resolve"))
        self.assertLess(tools.index("plan_freeze"), tools.index("result_analyze"))

    def test_stale_modification_hash_is_rejected(self):
        with self.assertRaises(ValueError):
            self.call("plan_patch", plan_ref=self.s["plan_ref"], expected_contract_hash="0"*64,
                changes=[{"path": "/analysis/sigma", "value": .03}], reason="stale editor")

    def test_authorization_and_review_status_cannot_be_patched(self):
        plan = self.library.store.get(self.s["plan_ref"], "plan")
        for path in ("/execution_authorized", "/request_hash", "/revision", "/run_plan"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.call("plan_patch", plan_ref=self.s["plan_ref"], expected_contract_hash=digest(plan["contract"]),
                    changes=[{"path": path, "value": True}], reason="forbidden")

    def test_plan_change_cannot_reuse_old_review_or_freeze(self):
        p = self.library.store.get(self.s["plan_ref"], "plan")
        new = self.call("plan_patch", plan_ref=self.s["plan_ref"], expected_contract_hash=digest(p["contract"]),
            changes=[{"path": "/resources/budget", "value": 101}], reason="new budget")
        freeze = self.library.store.get(self.s["freeze_ref"], "freeze")
        with self.assertRaises(ValueError):
            self.call("plan_freeze", plan_ref=new["plan_ref"], review_ref=self.s["review_ref"], alignment_ref=freeze["alignment_ref"])
        self.assertEqual(self.library.store.get(self.s["plan_ref"], "plan"), p)

    def changed_claim(self, **changes):
        value = self.library.store.get(self.s["claim_ref"], "claim")
        args = {k: v for k, v in value.items() if k not in {"type", "decision_rule", "real_world_verified"}}
        args.update(changes)
        return self.call("claim_define", **args)["claim_ref"]

    def test_plan_check_detects_wrong_response_scope_unit_and_treatment_mapping(self):
        for fields in ({"response": "training_loss"}, {"population_scope": "all_pdes_and_all_populations"},
                       {"expected_unit_definition": "every_grid_point_is_an_independent_experiment"},
                       {"factor_levels": [{"factor": "architecture", "baseline": "wrong", "candidate": "other"}]}):
            claim = self.changed_claim(**fields)
            result = self.call("claim_check_plan", claim_ref=claim, plan_ref=self.s["plan_ref"])
            self.assertFalse(result["can_test_conditionally"])
            self.assertIsNone(result["claim_supported"])

    def test_posthoc_claim_or_practical_threshold_change_cannot_assess_locked_results(self):
        claim = self.changed_claim(practical_margin=0)
        with self.assertRaises(ValueError): self.call("claim_assess", claim_ref=claim, analysis_ref=self.s["analysis_ref"])

    def test_passing_plan_alignment_is_not_result_support(self):
        result = self.call("claim_check_plan", claim_ref=self.s["claim_ref"], plan_ref=self.s["plan_ref"])
        self.assertTrue(result["can_test_conditionally"])
        self.assertIsNone(result["claim_supported"])
        self.assertFalse(result["real_world_assumptions_verified"])

    def test_findings_cannot_be_self_marked_resolved(self):
        with self.assertRaises(ValueError): self.call("review_resolve", old_review_ref=self.s["review_ref"], new_review_ref=self.s["review_ref"])

    def test_workflow_is_ordered_with_tool_parameter_bindings(self):
        result = self.call("workflow_verify", workflow_ref=self.s["workflow_ref"])
        self.assertTrue(result["passed"])
        workflow = self.library.store.get(self.s["workflow_ref"], "workflow")
        self.assertTrue(all(node["arguments"] and node["acceptance"] and node["on_failure"] for node in workflow["nodes"]))

    def test_workflow_cycle_or_bad_output_reference_is_rejected(self):
        for kind in ("cycle", "output"):
            value = self.library.store.get(self.s["workflow_ref"], "workflow")
            if kind == "cycle":
                value["nodes"][0]["depends_on"] = ["write_report"]
            else:
                value["nodes"][3]["arguments"]["job_ref"] = {"$from": "run_or_reuse.missing_output"}
            reference = self.library.store.put("workflow", value)
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.call("workflow_verify", workflow_ref=reference)

    def test_mock_job_is_idempotent_and_cannot_shop_for_outcome(self):
        first = self.call("job_run_mock", freeze_ref=self.s["freeze_ref"], scenario="benefit")
        second = self.call("job_run_mock", freeze_ref=self.s["freeze_ref"], scenario="benefit")
        self.assertEqual(first["job_ref"], second["job_ref"])
        self.assertTrue(second["reused"])
        with self.assertRaises(ValueError): self.call("job_run_mock", freeze_ref=self.s["freeze_ref"], scenario="harm")

    def test_incomplete_unit_outcomes_are_not_analyzed(self):
        job = self.library.store.get(self.s["job_ref"], "job")
        job["rows"].pop()
        reference = self.library.store.put("job", job)
        with self.assertRaises(ValueError): self.call("result_analyze", job_ref=reference)

    def test_inconclusive_evidence_is_not_equivalence_or_automatic_retest(self):
        analysis = self.library.store.get(self.s["analysis_ref"], "analysis")
        analysis["interval"] = [-.02, .01]
        reference = self.library.store.put("analysis", analysis)
        result = self.call("claim_assess", claim_ref=self.s["claim_ref"], analysis_ref=reference)
        self.assertEqual(result["status"], "inconclusive")
        self.assertFalse(result["real_scientific_claim_verified"])
        next_step = self.call("loop_next_action", assessment_ref=result["assessment_ref"])
        self.assertFalse(next_step["automatic_retest"])
        self.assertFalse(next_step["change_success_threshold"])

    def test_effect_direction_and_practical_margin_are_separate(self):
        analysis = self.library.store.get(self.s["analysis_ref"], "analysis")
        analysis["interval"] = [-.009, -.002]
        reference = self.library.store.put("analysis", analysis)
        result = self.call("claim_assess", claim_ref=self.s["claim_ref"], analysis_ref=reference)
        self.assertEqual(result["status"], "supports_direction_under_assumptions")
        self.assertFalse(result["practical_benefit_supported"])

    def test_interval_in_opposite_direction_is_reported(self):
        analysis = self.library.store.get(self.s["analysis_ref"], "analysis")
        analysis["interval"] = [.01, .03]
        reference = self.library.store.put("analysis", analysis)
        result = self.call("claim_assess", claim_ref=self.s["claim_ref"], analysis_ref=reference)
        self.assertEqual(result["status"], "opposite_direction_under_assumptions")

    def test_unimplemented_and_real_tools_cannot_execute(self):
        for name in ("sample_size_compute", "cvit_train_real", "darcy_fit_real", "human_approval_record"):
            with self.subTest(name=name), self.assertRaises(ValueError): self.call(name)

    def test_strict_schema_rejects_extra_keys_bool_as_number_and_nonfinite(self):
        with self.assertRaises(ValueError): self.call("project_create", title="t", objective="x", shell="never")
        with self.assertRaises(ValueError): self.changed_claim(practical_margin=True)
        with self.assertRaises(ValueError): self.changed_claim(practical_margin=float("nan"))

    def test_artifact_type_and_hash_tampering_detected(self):
        with self.assertRaises(ValueError): self.library.store.get(self.s["claim_ref"], "plan")
        path = self.folder/"objects"/(self.s["plan_ref"][:24]+".json")
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises((ValueError, KeyError)): self.library.store.get(self.s["plan_ref"])

    def test_no_arbitrary_workspace_or_path_read(self):
        with self.assertRaises(ValueError): Library(ROOT.parent)
        with self.assertRaises(ValueError): self.call("artifact_read", artifact_ref="../API_key_Agent.json")
