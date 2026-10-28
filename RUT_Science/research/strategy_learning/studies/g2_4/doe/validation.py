"""One fixed verifier for feedback, model selection and final evaluation."""
from .compiler import compile_plan, compile_workflow, diagnose, layout
from .io import digest
from .schema import CLAIM_PATHS, CONTRACT_SCHEMA, FAMILIES, errors, request_errors

VERIFIER_VERSION = "doe_verifier_v1"


def validate(contract, request):
    checks = []
    diagnostics = None
    def add(code, passed, detail):
        checks.append({"code": code, "status": "passed" if passed else "blocked", "detail": detail})
    try:
        contract_hash, request_hash = digest(contract), digest(request)
    except (TypeError, ValueError):
        contract_hash, request_hash = None, None
        add("finite_json", False, "Contract and request must be finite JSON")
    request_issues = request_errors(request)
    add("request_schema", not request_issues, request_issues)
    issues = errors(contract, CONTRACT_SCHEMA)
    add("contract_schema", not issues, issues)
    if not request_issues and not issues and request_hash is not None:
        add("request_binding", contract["request_hash"] == request_hash, "Host-owned request identity must match")
        add("supported_scope", request["requested_family"] in FAMILIES and contract["family"] == request["requested_family"],
            "v1 accepts only the explicitly requested registered family")
        evidence = {row["id"]: row for row in request["evidence"]}
        claims = {row["path"]: row for row in contract["provenance"]}
        grounded = set(claims) == set(CLAIM_PATHS) and len(claims) == len(contract["provenance"])
        problems = []
        for path in CLAIM_PATHS:
            row = evidence.get(claims.get(path, {}).get("evidence_id"))
            if not row or row["path"] != path or row["status"] != "provided" or row["value"] != contract[path[1:]]:
                problems.append(path)
        add("evidence_grounding", grounded and not problems, {"ungrounded_claims": problems})
        unresolved = [row["path"] for row in request["evidence"] if row["status"] != "provided"]
        add("critical_facts_available", not unresolved, unresolved)
        required = {"normal_iid_errors", "constant_error_variance"}
        if contract["blocks"]:
            required.add("no_treatment_block_interaction")
        add("assumptions_declared", set(contract["assumptions"]) == required, "Nominal power requires these declared model assumptions")
        expected_model = {"crd_two_arm": "two_arm", "rcbd_two_arm": "additive_blocks",
            "factorial_2x2": "blocked_full_factorial" if contract["blocks"] else "full_factorial"}[contract["family"]]
        add("analysis_model", contract["analysis"]["model"] == expected_model, "Analysis must include all factors/interactions and declared blocks")
        try:
            layout(contract)
            add("design_layout", True, "Bounded balanced design family")
            expected = compile_plan(contract)
            add("randomization_schedule", contract["run_plan"] == expected, "Recomputed allocation and within-block order must match the locked seed")
            ids = [row["unit_id"] for row in contract["run_plan"]]
            add("experimental_units", len(set(ids)) == len(ids), "Each planned treatment application needs a distinct unit id; measurements do not add units")
            add("run_budget", len(expected)*contract["resources"]["per_run"] <= contract["resources"]["budget"],
                {"planned_cost": len(expected)*contract["resources"]["per_run"], "declared_budget": contract["resources"]["budget"]})
            diagnostics = diagnose(contract)
            add("estimability", diagnostics["full_rank"] and diagnostics["primary_estimable"], diagnostics)
            add("residual_degrees_of_freedom", diagnostics["residual_df"] > 0, "Residual variance must be estimable under the declared model")
            power = diagnostics["nominal_power"]
            add("nominal_power", power is not None and power+1e-12 >= contract["analysis"]["target_power"],
                {"achieved": power, "target": contract["analysis"]["target_power"], "conditional_on_declared_sigma_and_model": True})
        except (ValueError, KeyError, IndexError) as exc:
            add("design_layout", False, str(exc))
    checks.append({"code": "real_world_assumptions", "status": "unverified",
        "detail": "Unit independence, variance, additivity, measurement quality and actual randomization require external evidence; no observed outcomes were analyzed"})
    value = {"schema_version": "doe_validation_v1", "verifier_version": VERIFIER_VERSION,
        "contract_hash": contract_hash, "request_hash": request_hash, "checks": checks, "diagnostics": diagnostics,
        "experiment_steps": compile_workflow(contract) if not issues else None,
        "ready_for_review": not any(check["status"] == "blocked" for check in checks),
        "execution_authorized": False, "scientific_success": None, "expert_calibrated": False}
    value["validation_hash"] = digest(value)
    return value


def blockers(report):
    return [row["code"] for row in report["checks"] if row["status"] == "blocked"]
