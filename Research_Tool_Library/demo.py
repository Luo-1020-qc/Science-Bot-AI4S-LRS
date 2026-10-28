"""Darcy/CViT version-review-freeze-evidence loops, synthetic observations only."""
import json
from pathlib import Path
from core import Library, ROOT, digest


def run_demo(domain, folder):
    library = Library(folder)
    trace = []
    def call(name, **arguments):
        result = library.call(name, arguments)["result"]
        trace.append({"tool": name, "arguments": arguments, "result": result})
        return result
    project = call("project_create", title=domain+" illustrative research", objective="Compare a prespecified method effect under a bounded dataset protocol")["project_ref"]
    family = "rcbd_two_arm" if domain == "darcy" else "factorial_2x2"
    first = call("plan_create", project_ref=project, family=family)["plan_ref"]
    template = library.store.get(first, "plan")
    factors = [{"name": "predictor", "levels": ["mean_field", "ridge_field"]}] if domain == "darcy" else [
        {"name": "architecture", "levels": ["baseline_small", "candidate_small"]}, {"name": "learning_rate", "levels": ["0.0001", "0.0003"]}]
    unit = ("One predictor application within an independently drawn data-realization block" if domain == "darcy" else
            "One independently seeded training run within a data-realization block")
    changes = [{"path": path, "value": value} for path, value in [
        ("/question", "Compare candidate minus baseline mean relative L2 under the declared dataset protocol"),
        ("/factors", factors), ("/experimental_unit/definition", unit), ("/response/name", "relative_l2"),
        ("/response/unit", "dimensionless"), ("/analysis/primary_term", factors[0]["name"]),
        ("/analysis/minimum_effect", .02), ("/analysis/sigma", .02), ("/analysis/model", "two_arm")]]
    bad = call("plan_patch", plan_ref=first, expected_contract_hash=digest(template["contract"]), changes=changes,
               reason="Illustrative requested scientific fields; intentionally omit block/interaction model terms to exercise review")["plan_ref"]
    claim = call("claim_define", project_ref=project, statement="Candidate has lower mean relative L2 than baseline within the declared protocol",
        response="relative_l2", primary_term=factors[0]["name"], direction="lower", practical_margin=.01,
        population_scope="declared_dataset_and_training_protocol", factor_levels=[{"factor": f["name"], "baseline": f["levels"][0], "candidate": f["levels"][1]} for f in factors],
        expected_unit_definition=unit)["claim_ref"]
    failed_review = call("plan_review", plan_ref=bad)
    if failed_review["ready_for_review"]:
        raise ValueError("Negative demo draft unexpectedly passed")
    corrected = call("plan_patch", plan_ref=bad, expected_contract_hash=digest(library.store.get(bad, "plan")["contract"]),
        changes=[{"path": "/analysis/model", "value": "additive_blocks" if domain == "darcy" else "blocked_full_factorial"}],
        reason="Resolve fixed verifier feedback; include declared blocks and all requested factorial interactions")["plan_ref"]
    call("plan_diff", old_plan_ref=bad, new_plan_ref=corrected)
    passed = call("plan_review", plan_ref=corrected)
    alignment = call("claim_check_plan", claim_ref=claim, plan_ref=corrected)
    resolution = call("review_resolve", old_review_ref=failed_review["review_ref"], new_review_ref=passed["review_ref"])
    frozen = call("plan_freeze", plan_ref=corrected, review_ref=passed["review_ref"], alignment_ref=alignment["alignment_ref"])["freeze_ref"]
    workflow = call("workflow_compile", freeze_ref=frozen)["workflow_ref"]
    call("workflow_verify", workflow_ref=workflow)
    call("job_reconcile_mock", freeze_ref=frozen)
    job = call("job_run_mock", freeze_ref=frozen, scenario="benefit")["job_ref"]
    reuse = call("job_run_mock", freeze_ref=frozen, scenario="benefit")
    call("job_poll_mock", job_ref=job)
    analysis = call("result_analyze", job_ref=job)
    assessment = call("claim_assess", claim_ref=claim, analysis_ref=analysis["analysis_ref"])
    call("loop_next_action", assessment_ref=assessment["assessment_ref"])
    report = call("report_build", assessment_ref=assessment["assessment_ref"], workflow_ref=workflow)
    value = {"domain": domain, "passed": passed["ready_for_review"] and resolution["all_clear"] and reuse["reused"],
        "plan_ref": corrected, "claim_ref": claim, "review_ref": passed["review_ref"], "freeze_ref": frozen,
        "workflow_ref": workflow, "job_ref": job, "analysis_ref": analysis["analysis_ref"], "assessment_ref": assessment["assessment_ref"],
        "report_ref": report["report_ref"], "initial_findings": failed_review["finding_codes"], "resolution": resolution,
        "final_assessment": assessment, "real_scientific_claim_verified": False, "real_tool_executions": 0,
        "note": "Synthetic unit responses used only to exercise evidence logic. No Darcy/CViT network was run.", "tool_calls": trace}
    (Path(folder)/"demo_summary.json").write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return value
