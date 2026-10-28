"""Non-destructive copy and hash audit for the authorized research consolidation.

Removal is a separate, explicit PowerShell operation after all checks pass.
This script never loads model services, policies, checkpoints or real tools.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
RECORDS = Path(__file__).resolve().parent
STUDIES = ROOT/"RUT_Science/research/strategy_learning/studies"
PAIRS = {"g2_2": "G2_2_Test_Workspace", "g2_3": "G2_3_Test_Workspace"}


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def inventory(folder):
    result = {}
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError("Refuse redirected migration target: "+str(path))
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = {"sha256": sha(path), "bytes": path.stat().st_size}
    return result


def protected_files():
    prefixes = [ROOT/"RUT_Science"/name for name in ("rut_science", "data", "models", "prompts")]+[ROOT/"Reference_Paper"]
    files = [path for folder in prefixes for path in folder.rglob("*") if path.is_file() and "__pycache__" not in path.parts]
    files += [ROOT/name for name in ("API_key_Agent.json", "science-bot.cmd", "Start-ScienceBot.ps1")]
    return {p.relative_to(ROOT).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size} for p in files}


def copy_studies():
    manifest_path = RECORDS/"migration.json"
    if manifest_path.exists():
        raise ValueError("Migration baseline already exists; audit it instead of replacing")
    entries = {}
    for study, old_name in PAIRS.items():
        source, destination = (ROOT/old_name).resolve(), (STUDIES/study).resolve()
        if source.parent != ROOT or source.name != old_name or not destination.is_relative_to(ROOT/"RUT_Science/research"):
            raise ValueError("Migration escaped authorized project paths")
        if not source.is_dir() or destination.exists():
            raise ValueError("Expected old source and an unused destination")
        files = inventory(source)
        shutil.copytree(source, destination, copy_function=shutil.copy2)
        if inventory(destination) != files:
            raise ValueError("Copy differs from source")
        for relative in ("run.py", "bootstrap.py", "lab/guard.py", "README_本轮交付.md"):
            path = source/relative
            if path.is_file():
                backup = destination/"evidence/pre_consolidation"/relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
        entries[study] = {"old_root": str(source), "new_root": str(destination), "files": files,
                          "file_count": len(files), "bytes": sum(record["bytes"] for record in files.values()), "initial_copy_exact": True}
    protected = protected_files()
    for name in ("README.md", "science_Bot_交接.md", "science_Bot_交付.md", "RUT_Science/README.md"):
        source = ROOT/name
        target = RECORDS/"documents_before"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    write(manifest_path, {"version": "research_consolidation_v1", "date": "2026-10-27", "studies": entries,
                         "protected_live_files": protected,
                         "authorization": "User requested checking and consolidating G2.2/G2.3 and removing the two former folders",
                         "policy": "No live policy promotion, real tools or model calls. Frozen sources/models/results remain byte-identical."})
    for study, entry in entries.items():
        write(Path(entry["new_root"])/"relocation.json", {"version": "study_relocation_v1", "date": "2026-10-27", "study": study,
              "old_root": entry["old_root"], "new_root": entry["new_root"], "project_root": str(ROOT),
              "manifest_ref": "maintenance/consolidation_2026-10-27/migration.json",
              "historical_evidence": "Old verification/protected inventories refer to original isolated-run conditions; retained without rewriting",
              "live_verification": "evidence/current_verification.json"})
    return {key: {"files": value["file_count"], "bytes": value["bytes"]} for key, value in entries.items()}


def audit():
    manifest = json.loads((RECORDS/"migration.json").read_text(encoding="utf-8"))
    changed_live = [relative for relative, expected in manifest["protected_live_files"].items()
                    if not (ROOT/relative).is_file() or sha(ROOT/relative) != expected["sha256"]]
    live_now = protected_files()
    added_live = sorted(set(live_now)-set(manifest["protected_live_files"]))
    reports = {}
    allowed_changes = {"run.py", "bootstrap.py", "lab/guard.py", "README_本轮交付.md", "tests/test_isolation.py", "tests/test_ppo.py", "tests/test_review.py"}
    for study, entry in manifest["studies"].items():
        destination = Path(entry["new_root"])
        missing, unexpected_changes = [], []
        for relative, expected in entry["files"].items():
            path = destination/relative
            if not path.is_file():
                missing.append(relative)
            elif sha(path) != expected["sha256"] and relative not in allowed_changes:
                unexpected_changes.append(relative)
        reports[study] = {"missing": missing, "unexpected_changes": unexpected_changes,
                          "old_folder_exists": Path(entry["old_root"]).exists(), "original_files": entry["file_count"]}
        source = Path(entry["old_root"])
        reports[study]["old_source_matches_baseline"] = inventory(source) == entry["files"] if source.exists() else None
    result = {"date": "2026-10-27", "protected_live_files_unchanged": not changed_live and not added_live,
              "changed_live": changed_live, "added_live": added_live, "protected_live_file_count": len(live_now),
              "studies": reports, "passed": not changed_live and not added_live and all(
                  not r["missing"] and not r["unexpected_changes"] and r["old_source_matches_baseline"] is not False for r in reports.values())}
    write(RECORDS/"migration_audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["copy", "audit"])
    args = parser.parse_args()
    print(json.dumps(copy_studies() if args.action == "copy" else audit(), ensure_ascii=False))
