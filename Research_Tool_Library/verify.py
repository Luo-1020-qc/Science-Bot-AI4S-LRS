"""Export runnable examples and check the detailed tool-library delivery."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from catalog import CATALOG, validate
from core import Library, ROOT, digest, strict


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def save(relative, value):
    target = ROOT/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def main():
    demo_reports = {}
    for domain in ("darcy", "cvit"):
        summary = strict((ROOT/"runs"/domain/"demo_summary.json").read_text(encoding="utf-8"))
        library = Library(ROOT/"runs"/domain)
        workflow = library.store.get(summary["workflow_ref"], "workflow")
        library.workflow_verify(summary["workflow_ref"])
        save("workflows/"+domain+"_workflow.json", workflow)
        # Validate every recorded call against the same contract inventory.
        specs = {row["name"]: row for row in CATALOG}
        for call in summary["tool_calls"]:
            validate(call["arguments"], specs[call["tool"]]["input_schema"])
            validate(call["result"], specs[call["tool"]]["output_schema"])
        previous = None
        for line in (ROOT/"runs"/domain/"calls.jsonl").read_text(encoding="utf-8").splitlines():
            event = strict(line)
            checksum = event.pop("event_hash")
            if event["previous_hash"] != previous or digest(event) != checksum:
                raise ValueError("Broken tool call audit chain")
            previous = checksum
        demo_reports[domain] = {"passed": summary["passed"], "calls": len(summary["tool_calls"]),
            "initial_findings": summary["initial_findings"], "final_status": summary["final_assessment"]["status"],
            "report_ref": summary["report_ref"], "real_scientific_claim_verified": summary["real_scientific_claim_verified"]}
        if domain == "cvit":
            plan = library.store.get(summary["plan_ref"], "plan")
            save("inputs/review_example.json", {"plan_ref": summary["plan_ref"]})
            save("inputs/claim_check_example.json", {"claim_ref": summary["claim_ref"], "plan_ref": summary["plan_ref"]})
            save("inputs/patch_example.json", {"plan_ref": summary["plan_ref"], "expected_contract_hash": digest(plan["contract"]),
                "changes": [{"path": "/resources/budget", "value": 256}], "reason": "Illustrative requested budget amendment; requires a new review"})
    source_paths = list(ROOT.glob("*.py"))+list((ROOT/"tests").glob("*.py"))
    for path in source_paths:
        ast.parse(path.read_text(encoding="utf-8"))
    broken, links = [], 0
    for path in ROOT.glob("*.md"):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target:
                continue
            links += 1
            if not (path.parent/target).exists():
                broken.append(target)
    # Read-only comparison with the last accepted production integration.
    original = ROOT.parent/"RUT_Science/delivery/research_online_update"
    baseline = strict((original/"protected_before.json").read_text(encoding="utf-8"))["files"]
    edits = strict((original/"authorized_source_changes.json").read_text(encoding="utf-8"))["files"]
    changed = [p for p, checksum in baseline.items() if not (ROOT.parent/p).is_file() or sha(ROOT.parent/p) != edits.get(p, {}).get("sha256", checksum)]
    tests = strict((ROOT/"test_result.json").read_text(encoding="utf-8"))
    value = {"date": "2026-10-28", "passed": not broken and not changed and tests["passed"] and all(r["passed"] for r in demo_reports.values()),
        "tools": len(CATALOG), "by_implementation": dict(Counter(row["implementation"] for row in CATALOG)), "tests": tests,
        "demos": demo_reports, "python_files_parsed": len(source_paths), "local_links_checked": links, "broken_links": broken,
        "protected_existing_project_files_checked": len(baseline), "unexpected_existing_project_changes": changed,
        "live_agent_registry_changed": False, "real_model_requests": 0, "real_darcy_fits": 0, "real_cvit_jobs": 0,
        "scope": "Independent offline tool contracts and mock research loops; no automatic chat registration or real scientific claim verification"}
    save("verification.json", value)
    print(json.dumps(value, ensure_ascii=False))
    if not value["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
