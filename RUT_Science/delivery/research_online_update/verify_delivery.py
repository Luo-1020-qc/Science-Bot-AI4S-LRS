"""Verify integration changes, immutable studies, entry evidence and navigation."""
import ast
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
HUB = PROJECT/"RUT_Science/research/strategy_learning"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    baseline = read(HERE/"protected_before.json")["files"]
    edits = read(HERE/"authorized_source_changes.json")["files"]
    unexpected = [relative for relative, checksum in baseline.items() if not (PROJECT/relative).is_file() or sha(PROJECT/relative) != edits.get(relative, {}).get("sha256", checksum)]
    prefixes = [PROJECT/"RUT_Science"/name for name in ("rut_science", "data", "models", "prompts")]+[PROJECT/"Reference_Paper"]
    added = [p.relative_to(PROJECT).as_posix() for folder in prefixes for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.relative_to(PROJECT).as_posix() not in baseline]
    allowed_new = {"RUT_Science/rut_science/science_bot/general/research.py"}
    originals = [relative for relative, checksum in baseline.items() if "/research/strategy_learning/studies/" in relative]
    changed_studies = [relative for relative in originals if not (PROJECT/relative).is_file() or sha(PROJECT/relative) != baseline[relative]]
    manifests = read(HUB/"online_artifacts.json")["studies"]
    changed_runtime_artifacts = [study+"/"+relative for study, entries in manifests.items() for relative, checksum in entries.items()
                                 if sha(HUB/"studies"/study/relative) != checksum]
    tests = read(HERE/"tests.json")
    studies = {study: read(HUB/"studies"/study/"evidence/current_verification.json") for study in ("g2_2", "g2_3", "g2_4")}
    entry = read(HERE/"entry_acceptance.json")
    documents = [PROJECT/name for name in ("README.md", "science_Bot_交接.md", "science_Bot_交付.md", "阶段性总结2_2026-10-27.md",
        "RUT_Science/README.md", "RUT_Science/research/strategy_learning/README.md", "RUT_Science/docs/Science_Bot_研究接口上线_zh.md",
        "RUT_Science/delivery/research_online_update/README_本轮交付.md")]
    broken, links = [], 0
    for path in documents:
        for ref in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in ref or ref.startswith("#"):
                continue
            links += 1
            target = (path.parent/ref.split("#")[0]).resolve()
            if not target.is_relative_to(PROJECT) or (not target.exists() and target != HERE/"verification.json"):
                broken.append({"document": path.relative_to(PROJECT).as_posix(), "ref": ref})
    source_paths = [PROJECT/relative for relative in edits]+[PROJECT/"RUT_Science/rut_science/science_bot/general/research.py",
        HUB/"online_worker.py", HUB/"online_audit.py", HUB/"run.py", *HERE.glob("*.py"), *(HERE/"tests").glob("*.py")]
    syntax = []
    for path in source_paths:
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"))
        except SyntaxError as exc:
            syntax.append({"path": str(path), "error": str(exc)})
    copied = {"test_compat_general_tools.py": "test_general_tools.py", "test_compat_general_provider.py": "test_general_provider.py", "http_helpers.py": "test_general_http.py"}
    copied_match = all(sha(HERE/"tests"/target) == sha(PROJECT/"RUT_Science/tests"/source) for target, source in copied.items())
    entry_files = ("science-bot.cmd", "Start-ScienceBot.ps1", "API_key_Agent.json")
    checks = {"protected_files_match_or_explicitly_authorized": not unexpected, "frozen_studies_unchanged": not changed_studies,
        "only_expected_core_additions": set(added) == allowed_new,
        "pinned_runtime_artifacts_match": not changed_runtime_artifacts, "integration_tests_pass": tests["passed"],
        "research_tests_pass": all(v["passed"] for v in studies.values()), "copied_compatibility_tests_match": copied_match,
        "entry_and_credentials_unchanged": all(sha(PROJECT/p) == baseline[p] for p in entry_files),
        "saved_entry_acceptance_pass": entry["passed"], "no_live_model_calls_or_training": entry["model_requests_used"] == entry["real_tool_executions"] == entry["formal_training_transitions"] == 0,
        "current_links_valid": not broken, "source_syntax_valid": not syntax}
    value = {"schema_version": "research_online_delivery_v1", "date": "2026-10-27", "passed": all(checks.values()), "checks": checks,
        "integration_tests": tests["tests"], "integration_passed": tests["tests"]-tests["skipped"]-tests["errors"]-tests["failures"],
        "integration_skipped": tests["skipped"], "research_tests": {study: row["tests"] for study, row in studies.items()},
        "total_research_tests": sum(v["tests"] for v in studies.values()), "protected_files": len(baseline),
        "authorized_modified_host_sources": len(edits), "unexpected_changes": unexpected, "retained_study_files": len(originals),
        "new_core_files": added,
        "changed_study_files": changed_studies, "pinned_online_artifacts": sum(len(v) for v in manifests.values()),
        "current_documents_checked": len(documents), "local_links_checked": links, "broken_links": broken,
        "parsed_python_files": len(source_paths), "syntax_errors": syntax,
        "real_model_requests": 0, "real_scientific_tool_executions": 0, "real_gpu_jobs": 0, "formal_training_transitions": 0,
        "default_interview_policy": "rule", "learned_policy_mode": "explicit_development_simulation_only", "expert_identity_verified_labels": 0,
        "scope": "Local terminal and existing HTTP messages integration; no external deployment, real scientific execution or default policy promotion"}
    (HERE/"verification.json").write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(value, ensure_ascii=False))
    if not value["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
