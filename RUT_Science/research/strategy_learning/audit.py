"""Current integrity checks for relocated studies; historic proofs stay immutable."""
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def read(path):
    if path.resolve() != path:
        raise ValueError("Redirected research artifact")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_study(folder):
    folder = Path(folder).resolve()
    relocation = read(folder/"relocation.json")
    project = Path(relocation["project_root"]).resolve()
    manifest = read(project/relocation["manifest_ref"])
    entry = manifest["studies"][relocation["study"]]
    if folder != Path(entry["new_root"]).resolve():
        raise ValueError("Study identity or current root mismatch")
    adapted = read(folder/"evidence/relocation_adaptations.json")
    allowed = {"run.py", "bootstrap.py", "lab/guard.py", "README_本轮交付.md", "tests/test_isolation.py", "tests/test_ppo.py", "tests/test_review.py"}
    if set(adapted["files"])-allowed:
        raise ValueError("Adaptation exceeds relocation-only scope")
    if sha(folder/adapted["new_runtime_helper"]) != adapted["new_runtime_helper_sha256"]:
        raise ValueError("Relocation runtime helper changed")
    for relative in adapted["files"]:
        if sha(folder/"evidence/pre_consolidation"/relative) != entry["files"][relative]["sha256"]:
            raise ValueError("Original adapted file backup changed: "+relative)
    changed = []
    for relative, expected in entry["files"].items():
        path = folder/relative
        current_hash = adapted["files"].get(relative, {}).get("sha256", expected["sha256"])
        if not path.is_file() or sha(path) != current_hash:
            changed.append(relative)
    frozen_sources, policy_count = 0, 0
    if relocation["study"] == "g2_2":
        freeze = read(folder/"evidence/freeze.json")
        if sha(folder/"bank/seal.json") != freeze["bank_seal_hash"]:
            raise ValueError("G2.2 task seal changed")
        for relative, checksum in freeze["control_files"].items():
            if sha(folder/relative) != checksum:
                raise ValueError("Frozen G2.2 control changed: "+relative)
            frozen_sources += 1
        for seed, checksum in freeze["policy_hashes"].items():
            if digest(read(folder/"models"/f"bc_seed_{seed}"/"policy.json")) != checksum:
                raise ValueError("G2.2 selected policy changed")
            policy_count += 1
        for record in read(folder/"bank/seal.json")["splits"].values():
            if sha(folder/record["path"]) != record["sha256"]:
                raise ValueError("G2.2 frozen task file changed")
        summary = read(folder/"evidence/benchmark.json")
        pending = [json.loads(line) for line in (folder/"review/pending.jsonl").read_text(encoding="utf-8").splitlines() if line]
        if not all(row["review"]["status"] == "pending" and row["review"]["correct_action"] is None for row in pending):
            raise ValueError("Historical pending review queue changed")
    else:
        freeze = read(folder/"evidence/selection_freeze.json")
        if sha(folder/"bank_v3/seal.json") != freeze["bank_seal_hash"]:
            raise ValueError("G2.3 task seal changed")
        for relative, checksum in freeze["source_hashes"].items():
            if sha(folder/relative) != checksum:
                raise ValueError("Frozen G2.3 source changed: "+relative)
            frozen_sources += 1
        for key, checksum in freeze["policies"].items():
            if digest(read(folder/"models"/key/"policy.json")) != checksum:
                raise ValueError("G2.3 selected policy changed")
            policy_count += 1
        for record in read(folder/"bank_v3/seal.json")["splits"].values():
            if sha(folder/record["path"]) != record["sha256"]:
                raise ValueError("G2.3 frozen task file changed")
        trial = folder/"experiments/feedback_v2"
        selection = read(trial/"selection.json")
        if sha(folder/"lab/feedback_trial.py") != selection["source_hash"] or sha(trial/"heldout.jsonl") != selection["bank_hash"]:
            raise ValueError("Corrective trial source or bank changed")
        frozen_sources += 1
        for name, checksum in selection["policies"].items():
            if digest(read(trial/"models"/(name+".json"))) != checksum:
                raise ValueError("Corrective trial policy changed")
            policy_count += 1
        summary = read(folder/"evidence/final_evaluation.json")
        scoring = read(folder/"evidence/scoring_audit.json")
        if scoring["policy_retrained_or_reselected"] or not scoring["original_frozen_report_preserved"]:
            raise ValueError("Scoring correction changed the frozen experiment")
    log = folder/"evidence/current_tests.log"
    log_text = log.read_text(encoding="utf-8") if log.exists() else ""
    count = re.search(r"Ran (\d+) tests", log_text)
    checks = {"all_original_files_preserved_or_explicitly_adapted": not changed,
              "frozen_control_sources_match": frozen_sources > 0, "selected_policies_match": policy_count > 0,
              "current_tests_pass": bool(count and "\nOK" in log_text and "FAILED" not in log_text),
              "historical_verification_retained": read(folder/"evidence/verification.json")["passed"],
              "no_live_policy_promotion": not summary.get("live_policy_promoted", False),
              "no_real_model_calls_or_execution": summary.get("real_model_calls", 0) == summary.get("real_executions", summary.get("real_tool_executions", 0)) == 0}
    value = {"version": "relocated_research_verification_v1", "date": "2026-10-27", "study": relocation["study"],
             "passed": all(checks.values()), "checks": checks, "changed_artifacts": changed,
             "tests": int(count[1]) if count else 0, "frozen_source_files": frozen_sources, "frozen_selected_policies": policy_count,
             "historical_root": entry["old_root"], "current_root": str(folder),
             "scope": "Current relocation validity; historical no-change inventories remain evidence of the original run, not today's project layout",
             "real_model_calls": 0, "real_tool_executions": 0, "real_gpu_jobs": 0, "policies_retrained": False}
    target = folder/"evidence/current_verification.json"
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    if not value["passed"]:
        raise ValueError("Relocation verification failed: "+str(value))
    return {"study": value["study"], "passed": True, "tests": value["tests"], "frozen_selected_policies": policy_count,
            "real_tool_executions": 0, "policies_retrained": False}
