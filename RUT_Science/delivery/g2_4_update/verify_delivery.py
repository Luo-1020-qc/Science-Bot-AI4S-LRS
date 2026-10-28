"""Read-only delivery QA plus one JSON report; no tool/model imports or training."""
import ast
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
HUB = PROJECT/"RUT_Science/research/strategy_learning"
STUDY = HUB/"studies/g2_4"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def main():
    reports = {study: read(HUB/"studies"/study/"evidence/current_verification.json") for study in ("g2_2", "g2_3", "g2_4")}
    protected = read(STUDY/"evidence/protected_before.json")["files"]
    changed = [relative for relative, row in protected.items() if not (PROJECT/relative).is_file() or sha(PROJECT/relative) != row["sha256"]]
    prefixes = [PROJECT/"RUT_Science"/name for name in ("rut_science", "data", "models", "prompts")]+[PROJECT/"Reference_Paper"]
    added = [p.relative_to(PROJECT).as_posix() for folder in prefixes for p in folder.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.relative_to(PROJECT).as_posix() not in protected]
    freeze = read(STUDY/"evidence/protocol_freeze.json")
    frozen_changes = [relative for relative, checksum in freeze["source_hashes"].items() if sha(STUDY/relative) != checksum]
    documents = [PROJECT/p for p in ("README.md", "science_Bot_交接.md", "science_Bot_交付.md", "阶段性总结2_2026-10-27.md",
        "RUT_Science/README.md", "RUT_Science/docs/Science_Bot_G2_4_DOE协议与统一验收_zh.md",
        "RUT_Science/research/strategy_learning/README.md", "RUT_Science/research/strategy_learning/studies/g2_4/README_本轮交付.md",
        "RUT_Science/delivery/g2_4_update/README_本轮交付.md")]
    broken, links = [], 0
    for document in documents:
        for ref in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if "://" in ref or ref.startswith("#"):
                continue
            links += 1
            target = (document.parent/ref.split("#")[0]).resolve()
            if not target.is_relative_to(PROJECT) or (not target.exists() and target != HERE/"verification.json"):
                broken.append({"document": document.relative_to(PROJECT).as_posix(), "ref": ref})
    sources = [HUB/"run.py", *STUDY.glob("*.py"), *(STUDY/"doe").glob("*.py"), *(STUDY/"tests").glob("*.py"), *HERE.glob("*.py")]
    errors = []
    for source in sources:
        try:
            ast.parse(source.read_text(encoding="utf-8-sig"))
        except SyntaxError as exc:
            errors.append({"path": str(source), "error": str(exc)})
    diagnostics = read(STUDY/"evidence/development_diagnostics.json")
    checks = {"all_research_studies_pass": all(row["passed"] for row in reports.values()),
        "protected_existing_files_unchanged": not changed and not added,
        "frozen_doe_sources_unchanged": not frozen_changes, "current_document_links_valid": not broken,
        "source_syntax_valid": not errors, "development_expected_results_match": diagnostics["cases"] == diagnostics["matched"],
        "heldout_records_not_scored": diagnostics["heldout_records_opened"] is False,
        "no_expert_labels_fabricated": reports["g2_4"]["human_expert_labels"] == 0,
        "no_training_or_live_promotion": reports["g2_4"]["policy_training"] is reports["g2_4"]["live_policy_promotion"] is False}
    result = {"schema_version": "g2_4_release_v1", "date": "2026-10-27", "passed": all(checks.values()), "checks": checks,
        "tests_by_study": {name: row["tests"] for name, row in reports.items()}, "total_research_tests": sum(row["tests"] for row in reports.values()),
        "protected_files": len(protected), "changed_existing_files": changed, "added_core_files": added,
        "frozen_doe_source_files": len(freeze["source_hashes"]), "frozen_doe_source_changes": frozen_changes,
        "python_files_parsed": len(sources), "syntax_errors": errors, "current_documents_checked": len(documents),
        "local_links_checked": links, "broken_links": broken, "development_cases": diagnostics["cases"], "matched_scripted_expectations": diagnostics["matched"],
        "always_stop_diagnostic": diagnostics["always_stop_diagnostic"], "pending_expert_reviews": reports["g2_4"]["pending_expert_reviews"],
        "human_expert_labels": 0, "heldout_records_scored": False, "real_tool_executions": 0, "real_model_requests": 0,
        "real_cvit_jobs": 0, "formal_training_transitions": 0, "application_entry_unchanged": not any(
            p in changed for p in ("science-bot.cmd", "Start-ScienceBot.ps1")),
        "scope": "Synthetic DOE protocol release. Original application full tool tests were not rerun; no expert calibration or learned-policy gains claimed."}
    (HERE/"verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
