"""Record explicit relocation edits and validate the current project navigation."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def prepare():
    manifest = json.loads((HERE/"migration.json").read_text(encoding="utf-8"))
    reasons = {"run.py": "Route current integrity checks separately and retain original test logs; refuse baseline overwrite",
               "bootstrap.py": "Resolve prior study inside unified research; prevent relocated baseline overwrite",
               "lab/guard.py": "Find actual project root after relocation; retain per-study write/import boundaries",
               "README_本轮交付.md": "Current navigation and commands; complete original report retained as historical evidence",
               "tests/test_isolation.py": "Use relocated prior-study path for the outside-write negative test",
               "tests/test_ppo.py": "Write repeatable current checkpoint tests separately from historical test artifacts",
               "tests/test_review.py": "Write current review fixtures separately from historical test artifacts"}
    for study, entry in manifest["studies"].items():
        folder, source = Path(entry["new_root"]), Path(entry["old_root"])
        changes = {}
        for relative, expected in entry["files"].items():
            target = folder/relative
            checksum = sha(target)
            if checksum == expected["sha256"]:
                continue
            if relative not in reasons:
                raise ValueError("Unapproved relocated content change: "+study+"/"+relative)
            original = source/relative
            if sha(original) != expected["sha256"]:
                raise ValueError("Original source changed since migration")
            backup = folder/"evidence/pre_consolidation"/relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copy2(original, backup)
            if sha(backup) != expected["sha256"]:
                raise ValueError("Adaptation backup mismatch")
            changes[relative] = {"sha256": checksum, "original_sha256": expected["sha256"], "reason": reasons[relative]}
        save(folder/"evidence/relocation_adaptations.json", {"date": "2026-10-27", "files": changes,
             "frozen_sources_modified": False, "new_runtime_helper": "lab/relocation.py",
             "new_runtime_helper_sha256": sha(folder/"lab/relocation.py")})
    return {"adaptation_manifests_saved": True}


def check():
    documents = [ROOT/p for p in ("README.md", "science_Bot_交接.md", "science_Bot_交付.md", "RUT_Science/README.md",
        "阶段性总结2_2026-10-27.md", "RUT_Science/research/strategy_learning/README.md",
        "RUT_Science/research/strategy_learning/studies/g2_2/README_本轮交付.md",
        "RUT_Science/research/strategy_learning/studies/g2_3/README_本轮交付.md",
        "maintenance/consolidation_2026-10-27/README.md")]
    broken = []
    links = 0
    for path in documents:
        for ref in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in ref or ref.startswith("#"):
                continue
            links += 1
            target = (path.parent/ref.split("#")[0]).resolve()
            if not target.is_relative_to(ROOT) or (not target.exists() and target != HERE/"verification.json"):
                broken.append({"document": path.relative_to(ROOT).as_posix(), "ref": ref})
    sources = [ROOT/"RUT_Science/scripts/science_bot_research.py"]
    sources += list((ROOT/"RUT_Science/research/strategy_learning").rglob("*.py"))
    sources += list(HERE.glob("*.py"))
    parse_errors = []
    for path in sources:
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except SyntaxError as exc:
            parse_errors.append({"path": str(path), "error": str(exc)})
    reports = [json.loads((ROOT/"RUT_Science/research/strategy_learning/studies"/study/"evidence/current_verification.json").read_text(encoding="utf-8")) for study in ("g2_2", "g2_3")]
    migration = json.loads((HERE/"migration_audit.json").read_text(encoding="utf-8"))
    value = {"date": "2026-10-27", "passed": not broken and not parse_errors and migration["passed"] and all(r["passed"] for r in reports),
             "current_documents_checked": len(documents), "local_links_checked": links, "broken_links": broken,
             "python_files_parsed": len(sources), "parse_errors": parse_errors,
             "research_tests": sum(r["tests"] for r in reports), "frozen_selected_policies_verified": sum(r["frozen_selected_policies"] for r in reports),
             "frozen_source_files_verified": sum(r["frozen_source_files"] for r in reports),
             "old_folders_removed": all(not r["old_folder_exists"] for r in migration["studies"].values()),
             "protected_live_files_unchanged": migration["protected_live_files_unchanged"],
             "protected_live_file_count": migration["protected_live_file_count"],
             "original_study_files": sum(r["original_files"] for r in migration["studies"].values()),
             "real_model_requests": 0, "real_tool_executions": 0, "real_gpu_jobs": 0, "retraining": False, "live_policy_promotion": False,
             "scope": "Research tests, relocation integrity, static syntax and current navigation; historic full application tests were not rerun"}
    save(HERE/"verification.json", value)
    if not value["passed"]:
        raise ValueError(str(value))
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "check"])
    args = parser.parse_args()
    print(json.dumps(prepare() if args.action == "prepare" else check(), ensure_ascii=False))
