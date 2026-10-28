"""Stage-independent task semantics. No rewards for hidden future stop reasons."""
from .io import digest
from .schema import CLAIM_PATHS, FAMILIES, request_errors
from .validation import validate, VERIFIER_VERSION

SCORER_VERSION = "doe_score_v1"


def stop_certificate(request, outcome):
    if set(outcome) != {"kind", "request_hash", "reason", "evidence_ids"} or outcome["request_hash"] != digest(request):
        return False
    ids = outcome["evidence_ids"]
    if type(ids) is not list or not ids or any(type(i) is not str for i in ids) or len(set(ids)) != len(ids):
        return False
    evidence = {row["id"]: row for row in request["evidence"]}
    if any(i not in evidence for i in ids):
        return False
    if outcome["reason"] == "critical_fact_unavailable":
        return all(evidence[i]["status"] == "unavailable" and evidence[i]["path"] in CLAIM_PATHS for i in ids)
    if outcome["reason"] == "unsupported_design":
        return request["requested_family"] not in FAMILIES and all(
            evidence[i]["path"] == "/family" and evidence[i]["value"] == request["requested_family"] for i in ids)
    # No blanket permission/budget excuse: this delivery evaluates design-only tasks.
    return False


def score(request, outcome, *, stage="development", decisions=1):
    if request_errors(request):
        raise ValueError("Invalid host-owned request")
    if stage not in {"train", "development", "heldout"} or type(decisions) is not int or not 1 <= decisions <= 40:
        raise ValueError("Invalid evaluation stage or episode decision count")
    digest(outcome)
    if type(outcome) is not dict:
        raise ValueError("Outcome must be a closed JSON object")
    kind, report = outcome.get("kind"), None
    success, classification = False, "invalid_submission"
    if kind == "submit" and set(outcome) == {"kind", "contract"}:
        report = validate(outcome["contract"], request)
        success = report["ready_for_review"]
        classification = "valid_design" if success else "invalid_design"
    elif kind == "stop":
        success = stop_certificate(request, outcome)
        classification = "correct_stop" if success else "unjustified_stop"
    # Positive terminal outcomes dominate the bounded decision cost (<=0.4).
    reward = (10.0 if success else -10.0)-.01*decisions
    return {"scorer_version": SCORER_VERSION, "verifier_version": VERIFIER_VERSION, "success": success,
        "classification": classification, "reward": reward, "decision_cost": .01*decisions,
        "validation": report, "request_hash": digest(request), "outcome_hash": digest(outcome),
        "execution_authorized": False, "scientific_success": None}


def selection_key(reports):
    """Use identical strict outcomes for dev ranking; keep components visible."""
    if not reports:
        raise ValueError("No development episodes")
    failures = sum(not row["success"] for row in reports)
    unjustified = sum(row["classification"] == "unjustified_stop" for row in reports)
    return (-failures, -unjustified, -sum(row["decision_cost"] for row in reports))
