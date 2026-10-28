from copy import deepcopy
import unittest
import numpy as np
from scipy.stats import nct, t
from doe.compiler import compile_plan, diagnose
from doe.io import digest, strict_json
from doe.schema import FAMILIES, request_errors
from doe.tasks import base_contract, make_case, request_for, SCENARIOS
from doe.validation import validate, blockers


class DesignTests(unittest.TestCase):
    def test_registered_designs_pass_conditionally_without_authorizing_execution(self):
        for family in FAMILIES:
            request, contract = base_contract(family)
            report = validate(contract, request)
            with self.subTest(family=family):
                self.assertTrue(report["ready_for_review"], blockers(report))
                self.assertFalse(report["execution_authorized"])
                self.assertIsNone(report["scientific_success"])
                self.assertFalse(report["expert_calibrated"])
                self.assertIn("unverified", [row["status"] for row in report["checks"]])

    def test_all_calibration_mutations_have_intended_blockers(self):
        for family in FAMILIES:
            for i, scenario in enumerate(SCENARIOS):
                task = make_case(family, scenario, "train", i)
                report = validate(task["candidate"], task["request"])
                with self.subTest(family=family, scenario=scenario):
                    self.assertEqual(report["ready_for_review"], task["expected"]["ready"])
                    if task["expected"]["blocker"]:
                        self.assertIn(task["expected"]["blocker"], blockers(report))

    def test_crd_contrast_variance_and_power_match_two_sample_formula(self):
        _, contract = base_contract()
        d = diagnose(contract)
        n, a = contract["replicates"], contract["analysis"]
        se = a["sigma"]*np.sqrt(2/n)
        df = 2*n-2
        critical = t.isf(a["alpha"]/2, df)
        power = nct.sf(critical, df, a["minimum_effect"]/se)+nct.cdf(-critical, df, a["minimum_effect"]/se)
        self.assertAlmostEqual(d["planned_standard_error"], se, places=12)
        self.assertEqual(d["residual_df"], df)
        self.assertAlmostEqual(d["nominal_power"], power, places=12)

    def test_rcbd_power_matches_paired_difference_formula_under_additivity(self):
        _, contract = base_contract("rcbd_two_arm")
        d, b, a = diagnose(contract), len(contract["blocks"]), contract["analysis"]
        se = a["sigma"]*np.sqrt(2/b)
        critical = t.isf(a["alpha"]/2, b-1)
        power = nct.sf(critical, b-1, a["minimum_effect"]/se)+nct.cdf(-critical, b-1, a["minimum_effect"]/se)
        self.assertAlmostEqual(d["nominal_power"], power, places=12)
        self.assertEqual(d["residual_df"], b-1)
        self.assertEqual(d["pure_error_df"], 0)

    def test_factorial_main_and_interaction_have_correct_effect_scales(self):
        _, contract = base_contract("factorial_2x2")
        n = len(contract["run_plan"])
        main = diagnose(contract)
        contract["analysis"]["primary_term"] = "A:B"
        interaction = diagnose(contract)
        self.assertAlmostEqual(main["variance_factor"], 4/n, places=12)
        self.assertAlmostEqual(interaction["variance_factor"], 16/n, places=12)
        self.assertEqual(interaction["contrast_definition"], "difference_in_differences")

    def test_unblocked_factorial_is_supported_with_its_own_model(self):
        _, c = base_contract("factorial_2x2")
        c["blocks"], c["replicates"] = [], 12
        c["analysis"]["model"] = "full_factorial"
        c["assumptions"].remove("no_treatment_block_interaction")
        c["run_plan"] = compile_plan(c)
        r = request_for(c); c["request_hash"] = digest(r)
        self.assertTrue(validate(c, r)["ready_for_review"])

    def test_prespecified_interaction_is_valid_when_power_and_evidence_match(self):
        _, c = base_contract("factorial_2x2")
        c["analysis"].update(primary_term="A:B", minimum_effect=2*c["analysis"]["sigma"])
        r = request_for(c); c["request_hash"] = digest(r)
        report = validate(c, r)
        self.assertTrue(report["ready_for_review"], blockers(report))
        self.assertEqual(report["diagnostics"]["contrast_definition"], "difference_in_differences")

    def test_power_and_type_one_error_match_independent_gaussian_simulation(self):
        _, c = base_contract()
        a, n = c["analysis"], c["replicates"]
        rng = np.random.default_rng(246)
        noise = rng.normal(0, a["sigma"], (6000, 2, n))
        se = np.sqrt(noise.var(axis=2, ddof=1).mean(axis=1)*2/n)
        null_diff = noise[:, 1].mean(axis=1)-noise[:, 0].mean(axis=1)
        critical = t.isf(a["alpha"]/2, 2*n-2)
        null_rate = np.mean(np.abs(null_diff/se) > critical)
        power = np.mean(np.abs((null_diff+a["minimum_effect"])/se) > critical)
        self.assertLess(abs(null_rate-a["alpha"]), .01)
        self.assertLess(abs(power-diagnose(c)["nominal_power"]), .02)

    def test_technical_repeated_measurements_do_not_inflate_sample_size_or_power(self):
        _, c = base_contract()
        before = diagnose(c)
        c["experimental_unit"]["measurement_repeats"] = 100
        after = diagnose(c)
        self.assertEqual(before, after)

    def test_sigma_sensitivity_exposes_optimistic_pilot_assumption(self):
        _, c = base_contract()
        result = diagnose(c)
        powers = [r["nominal_power"] for r in result["sigma_sensitivity"]]
        self.assertGreater(powers[0], powers[1]); self.assertGreater(powers[1], powers[2])
        self.assertFalse(result["pilot_variance_uncertainty_integrated"])

    def test_experiment_steps_are_ordered_review_only_and_do_not_claim_execution(self):
        r, c = base_contract()
        workflow = validate(c, r)["experiment_steps"]
        done = set()
        for step in workflow["steps"]:
            self.assertTrue(set(step["depends_on"]).issubset(done))
            self.assertFalse(step["executed"])
            done.add(step["id"])
        self.assertEqual(workflow["mode"], "design_review_only")
        self.assertFalse(workflow["execution_authorized"])
        self.assertIsNone(workflow["observed_outcomes"])

    def test_missing_treatment_cell_is_not_estimable(self):
        task = make_case("factorial_2x2", "missing_cell", "train", 0)
        d = diagnose(task["candidate"])
        self.assertFalse(d["full_rank"])
        self.assertFalse(d["primary_estimable"])

    def test_rank_saturated_design_cannot_claim_power(self):
        _, c = base_contract("factorial_2x2")
        c["blocks"], c["replicates"] = [], 1
        c["run_plan"] = compile_plan(c)
        self.assertEqual(diagnose(c)["residual_df"], 0)
        self.assertIsNone(diagnose(c)["nominal_power"])

    def test_randomization_is_reproducible_and_seed_changes_plan(self):
        _, c = base_contract("rcbd_two_arm", 9)
        self.assertEqual(c["run_plan"], compile_plan(c))
        c["randomization"]["seed"] += 1
        self.assertNotEqual(c["run_plan"], compile_plan(c))

    def test_blocks_balance_treatments_and_have_unique_units(self):
        _, c = base_contract("rcbd_two_arm")
        for block in c["blocks"]:
            inside = [r for r in c["run_plan"] if r["block"] == block]
            self.assertEqual(sorted(row["levels"][0] for row in inside), ["candidate", "control"])
        self.assertEqual(len({r["unit_id"] for r in c["run_plan"]}), len(c["run_plan"]))

    def test_changed_request_invalidates_old_confirmation_identity(self):
        r, c = base_contract()
        r["evidence"][0]["reference"] = "New user statement version"
        self.assertIn("request_binding", blockers(validate(c, r)))

    def test_forged_pilot_variance_is_not_accepted_even_when_power_increases(self):
        task = make_case("crd_two_arm", "forged_sigma", "train", 0)
        report = validate(task["candidate"], task["request"])
        self.assertGreater(report["diagnostics"]["nominal_power"], .99)
        self.assertFalse(report["ready_for_review"])

    def test_schema_rejects_bool_nonfinite_extra_and_duplicate_json_keys(self):
        r, c = base_contract()
        bad = deepcopy(c); bad["analysis"]["target_power"] = True
        self.assertFalse(validate(bad, r)["ready_for_review"])
        bad = deepcopy(c); bad["analysis"]["sigma"] = float("inf")
        self.assertFalse(validate(bad, r)["ready_for_review"])
        bad = deepcopy(c); bad["execution_authorized"] = True
        self.assertFalse(validate(bad, r)["ready_for_review"])
        with self.assertRaises(ValueError): strict_json('{"alpha":0.05,"alpha":0.2}')
        with self.assertRaises(ValueError): strict_json('{"sigma":NaN}')

    def test_unknown_real_world_independence_cannot_be_filled_from_structure(self):
        r, c = base_contract()
        next(row for row in r["evidence"] if row["path"] == "/experimental_unit").update(status="unavailable", value=None)
        c["request_hash"] = digest(r)
        self.assertIn("critical_facts_available", blockers(validate(c, r)))

    def test_power_does_not_accept_posthoc_alpha_or_primary_switch(self):
        r, c = base_contract()
        c["analysis"]["alpha"] = .15
        self.assertIn("evidence_grounding", blockers(validate(c, r)))

    def test_unsupported_hard_to_change_layout_does_not_fall_back_to_crd(self):
        task = make_case("crd_two_arm", "unsupported_scope", "train", 0)
        self.assertIn("supported_scope", blockers(validate(task["candidate"], task["request"])))

    def test_excessive_run_count_is_bounded_before_matrix_allocation(self):
        _, c = base_contract("factorial_2x2")
        c["replicates"] = 100
        with self.assertRaises(ValueError): compile_plan(c)

    def test_duplicate_or_inconsistent_public_evidence_fails_request_schema(self):
        r, _ = base_contract()
        r["evidence"][1]["id"] = r["evidence"][0]["id"]
        self.assertTrue(request_errors(r))

    def test_closed_schema_does_not_accept_arbitrary_analysis_code(self):
        r, c = base_contract()
        c["analysis"]["model"] = "__import__('os').system('never')"
        self.assertFalse(validate(c, r)["ready_for_review"])

    def test_no_mutation_of_host_request_or_candidate(self):
        r, c = base_contract()
        before = digest([r, c])
        validate(c, r)
        self.assertEqual(digest([r, c]), before)
