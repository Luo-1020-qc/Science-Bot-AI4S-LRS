"""Development diagnostics, public feedback replay and immutable release checks."""
from copy import deepcopy
import re
import sys
import numpy as np
import scipy
from .guard import LAB, PROJECT
from .io import digest, read, sha, write, write_rows
from .schema import CONTRACT_SCHEMA, REQUEST_SCHEMA
from .scoring import score, SCORER_VERSION
from .tasks import base_contract, build_bank, load_split, verify_bank
from .validation import validate, blockers, VERIFIER_VERSION


def diagnose_development():
    freeze = read(LAB/"evidence/protocol_freeze.json")
    check_freeze(freeze)
    tasks = load_split("development", purpose="development")
    results, stop_results = [], []
    for task in tasks:
        outcome = {"kind": "submit", "contract": task["candidate"]}
        reports = [score(task["request"], outcome, stage=stage) for stage in ("train", "development", "heldout")]
        if reports[0] != reports[1] or reports[1] != reports[2]:
            raise ValueError("Scoring semantics differ by stage")
        report = reports[0]["validation"]
        expected = task["expected"]
        matched = report["ready_for_review"] == expected["ready"] and (expected["blocker"] is None or expected["blocker"] in blockers(report))
        results.append({"task_id": task["task_id"], "scenario": task["scenario"], "family": task["family"],
            "matched_scripted_expectation": matched, "ready_for_review": report["ready_for_review"], "blocking_codes": blockers(report),
            "validation_hash": report["validation_hash"], "score_same_across_stages": True})
        unavailable = next((r for r in task["request"]["evidence"] if r["status"] == "unavailable"), None)
        unsupported = task["request"]["requested_family"] == "split_plot"
        scope = next(r for r in task["request"]["evidence"] if r["path"] == "/family")
        stopped = {"kind": "stop", "request_hash": digest(task["request"]),
            "reason": "unsupported_design" if unsupported else "critical_fact_unavailable",
            "evidence_ids": [scope["id"] if unsupported else unavailable["id"] if unavailable else "e00"]}
        graded = score(task["request"], stopped)
        if graded["success"] != expected["stop_required"]:
            raise ValueError("Public-evidence stop calibration mismatch")
        stop_results.append(graded)
    target = LAB/"evidence/development_diagnostics.json"
    value = {"version": "doe_calibration_diagnostics_v1", "cases": len(results), "matched": sum(row["matched_scripted_expectation"] for row in results),
        "results": results, "labels": "scripted regression expectations; not expert judgments or learned-agent performance",
        "positive_cases": sum(t["expected"]["ready"] for t in tasks), "negative_cases": sum(not t["expected"]["ready"] for t in tasks),
        "always_stop_diagnostic": {"cases": len(stop_results), "correct_stops": sum(r["success"] for r in stop_results),
            "unjustified_stops": sum(not r["success"] for r in stop_results), "note": "Publicly grounded reason chosen when present; blanket stopping still fails designable tasks"},
        "heldout_records_opened": False, "scorer_version": SCORER_VERSION, "verifier_version": VERIFIER_VERSION,
        "human_expert_labels": 0, "real_tool_executions": 0, "real_model_requests": 0, "real_gpu_jobs": 0}
    write(target, value)
    if value["matched"] != value["cases"]:
        raise ValueError("Development calibration mismatch: "+str([r for r in results if not r["matched_scripted_expectation"]]))
    return {"development_cases": value["cases"], "matched_scripted_expectations": value["matched"], "heldout_records_opened": False}


def demo():
    request, contract = base_contract("factorial_2x2", 73)
    broken = deepcopy(contract)
    broken["analysis"]["model"] = "two_arm"
    first = validate(broken, request)
    repaired = deepcopy(contract)
    repaired["revision"] += 1
    second = validate(repaired, request)
    result = {"version": "doe_feedback_demo_v1", "scripted_not_a_trained_policy": True,
        "trace": [{"action": "submit_candidate_without_interaction", "feedback": first},
                  {"action": "restore_grounded_full_factorial_analysis", "feedback": second}],
        "final_contract": repaired, "score": score(request, {"kind": "submit", "contract": repaired}, decisions=2),
        "observed_outcomes": None, "real_cvit_jobs": 0, "execution_authorized": False}
    write(LAB/"evidence/demo.json", result)
    write(LAB/"examples/factorial_request.json", request)
    write(LAB/"examples/factorial_contract.json", repaired)
    return {"initial_blockers": blockers(first), "repaired_ready_for_review": second["ready_for_review"],
            "nominal_power": second["diagnostics"]["nominal_power"], "real_cvit_jobs": 0, "scientific_success": None}


def freeze_protocol():
    path = LAB/"evidence/protocol_freeze.json"
    if path.exists():
        check_freeze(read(path))
        return {"frozen_protocol_reused": True}
    build_bank()
    from .review import export_queue
    export_queue()
    write(LAB/"schemas/experiment_contract.schema.json", CONTRACT_SCHEMA, fresh=True)
    write(LAB/"schemas/request.schema.json", REQUEST_SCHEMA, fresh=True)
    sources = [LAB/"run.py", *sorted((LAB/"doe").glob("*.py"))]
    frozen = {p.relative_to(LAB).as_posix(): sha(p) for p in sources}
    value = {"version": "doe_protocol_freeze_v1", "date": "2026-10-27", "source_hashes": frozen,
        "seal_sha256": sha(LAB/"bank/seal.json"), "pending_review_sha256": sha(LAB/"review/pending.jsonl"),
        "schema_hashes": {p.name: sha(p) for p in sorted((LAB/"schemas").glob("*.json"))},
        "scorer_version": SCORER_VERSION, "verifier_version": VERIFIER_VERSION,
        "before_development_diagnostics": True, "heldout_records_evaluated": False, "policy_training": False,
        "python": sys.version.split()[0], "numpy": np.__version__, "scipy": scipy.__version__}
    write(path, value, fresh=True)
    return {"frozen_source_files": len(frozen), "policy_training": False}


def check_freeze(freeze):
    for relative, checksum in freeze["source_hashes"].items():
        if sha(LAB/relative) != checksum:
            raise ValueError("Frozen protocol source changed: "+relative)
    if sha(LAB/"bank/seal.json") != freeze["seal_sha256"] or sha(LAB/"review/pending.jsonl") != freeze["pending_review_sha256"]:
        raise ValueError("Frozen seal or pending reviews changed")
    for name, checksum in freeze["schema_hashes"].items():
        if sha(LAB/"schemas"/name) != checksum:
            raise ValueError("Frozen JSON schema changed")
    verify_bank()


def verify():
    check_freeze(read(LAB/"evidence/protocol_freeze.json"))
    before = read(LAB/"evidence/protected_before.json")
    changed = [relative for relative, row in before["files"].items() if not (PROJECT/relative).is_file() or sha(PROJECT/relative) != row["sha256"]]
    copied = read(LAB/"evidence/copied_files.json")
    for row in copied["files"]:
        if sha(LAB/row["copy"]) != row["sha256"]:
            raise ValueError("Reference copy changed")
    log = (LAB/"evidence/current_tests.log").read_text(encoding="utf-8")
    count = re.search(r"Ran (\d+) tests", log)
    development = read(LAB/"evidence/development_diagnostics.json")
    from .io import rows
    pending = rows(LAB/"review/pending.jsonl")
    checks = {"protected_original_files_unchanged": not changed, "tests_passed": bool(count and "\nOK" in log and "FAILED" not in log),
        "development_diagnostics_match": development["cases"] == development["matched"], "heldout_records_not_evaluated": not development["heldout_records_opened"],
        "pending_reviews_not_fabricated": all(r["review"]["status"] == "pending" and r["review"]["verdict"] is None for r in pending),
        "no_real_tools": development["real_tool_executions"] == development["real_model_requests"] == development["real_gpu_jobs"] == 0}
    value = {"version": "g2_4_delivery_v1", "date": "2026-10-27", "study": "g2_4", "passed": all(checks.values()), "checks": checks,
        "tests": int(count[1]) if count else 0, "protected_files": len(before["files"]), "changed_original_files": changed,
        "pending_expert_reviews": len(pending), "human_expert_labels": 0, "development_cases": development["cases"],
        "heldout_records_evaluated": False, "real_model_requests": 0, "real_tool_executions": 0, "real_gpu_jobs": 0,
        "policy_training": False, "live_policy_promotion": False, "scope": "Synthetic protocol diagnostics, not expert-calibrated DOE correctness or learned-agent gains"}
    write(LAB/"evidence/current_verification.json", value)
    if not value["passed"]:
        raise ValueError(str(value))
    return {"study": "g2_4", "passed": True, "tests": value["tests"], "development_cases": value["development_cases"], "human_expert_labels": 0}
