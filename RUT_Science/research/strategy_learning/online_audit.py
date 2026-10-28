"""Current integration audit; original study protection proofs stay historical."""
import hashlib
import json
from pathlib import Path
import re

HUB = Path(__file__).resolve().parent
PROJECT = HUB.parents[2]
DELIVERY = PROJECT/"RUT_Science/delivery/research_online_update"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def audit_g24():
    folder = HUB/"studies/g2_4"
    baseline = read(folder/"evidence/protected_before.json")["files"]
    edits = read(DELIVERY/"authorized_source_changes.json")["files"]
    changed = [relative for relative, row in baseline.items() if not (PROJECT/relative).is_file() or
               sha(PROJECT/relative) != edits.get(relative, {}).get("sha256", row["sha256"])]
    freeze = read(folder/"evidence/protocol_freeze.json")
    for relative, expected in freeze["source_hashes"].items():
        if sha(folder/relative) != expected:
            raise ValueError("Frozen G2.4 protocol changed")
    if sha(folder/"bank/seal.json") != freeze["seal_sha256"] or sha(folder/"review/pending.jsonl") != freeze["pending_review_sha256"]:
        raise ValueError("G2.4 seal/pending record changed")
    seal = read(folder/"bank/seal.json")
    for record in seal["splits"].values():
        if sha(folder/record["path"]) != record["sha256"]:
            raise ValueError("Frozen DOE bank changed")
    log = (folder/"evidence/current_tests.log").read_text(encoding="utf-8")
    count = re.search(r"Ran (\d+) tests", log)
    diagnostic = read(folder/"evidence/development_diagnostics.json")
    checks = {"frozen_sources_tasks_reviews_retained": True, "protected_files_match_or_authorized_integration": not changed,
        "tests_passed": bool(count and "\nOK" in log and "FAILED" not in log),
        "development_reference_checks_pass": diagnostic["matched"] == diagnostic["cases"],
        "heldout_not_scored": diagnostic["heldout_records_opened"] is False}
    value = {"version": "g2_4_online_compatibility_v1", "date": "2026-10-27", "study": "g2_4", "passed": all(checks.values()),
        "checks": checks, "tests": int(count[1]) if count else 0, "changed_original_files": changed,
        "human_expert_labels": 0, "pending_expert_reviews": 42, "development_cases": diagnostic["cases"],
        "real_tool_executions": 0, "real_model_requests": 0, "real_gpu_jobs": 0, "policy_training": False, "live_policy_promotion": False,
        "scope": "Current app integration explicitly changes listed host sources; original no-change report is preserved in online delivery/historical_before"}
    (folder/"evidence/current_verification.json").write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    if not value["passed"]:
        raise ValueError(str(value))
    print(json.dumps({"study": "g2_4", "passed": True, "tests": value["tests"], "scope": value["scope"]}, ensure_ascii=False))


if __name__ == "__main__":
    audit_g24()
