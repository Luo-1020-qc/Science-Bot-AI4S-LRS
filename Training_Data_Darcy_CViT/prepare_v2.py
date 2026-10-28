"""Preserve v1 exactly and copy the fixed offline tool runtime for v2 only."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    archive = ROOT/"v1"
    if archive.exists():
        raise ValueError("v1 snapshot already exists")
    archive.mkdir()
    names = ("tasks", "episodes", "labels", "evaluator_only", "review", "examples", "schemas", "reference_copy", "tests",
             "build_examples.py", "dataset_lib.py", "manifest.json", "schemas.py", "validate.py", "validation.json", "validation_tests.log",
             "project_integrity.json", "README_训练数据说明.md", "字段与训练流程.md")
    snapshot = {}
    # Copy first; directory removal/moving is a separate native PowerShell action.
    for name in names:
        source = ROOT/name
        destination = archive/name
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        for path in ([source] if source.is_file() else source.rglob("*")):
            if path.is_file():
                relative = path.relative_to(ROOT).as_posix()
                checksum = sha(path)
                if sha(archive/relative) != checksum:
                    raise ValueError("v1 copy differs")
                snapshot[relative] = checksum
    target = ROOT/"v2"
    target.mkdir(exist_ok=True)
    runtime = target/"tool_runtime"
    runtime.mkdir(exist_ok=True)
    records = []
    for name in ("core.py", "catalog.py", "doe_adapter.py"):
        source = PROJECT/"Research_Tool_Library"/name
        raw = source.read_text(encoding="utf-8")
        if name == "doe_adapter.py":
            raw = raw.replace('PROJECT = ROOT.parent', 'PROJECT = next(p for p in ROOT.parents if (p/"RUT_Science/research/strategy_learning").is_dir())')
        destination = runtime/name
        destination.write_text(raw, encoding="utf-8")
        records.append({"source": str(source), "source_sha256": sha(source), "copy": name, "copy_sha256": sha(destination),
                        "adaptation": "Ancestor project lookup for relocated read-only DOE adapter" if name == "doe_adapter.py" else None})
    (target/"v1_snapshot.json").write_text(json.dumps({"files": snapshot, "date": "2026-10-28"}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (runtime/"source_manifest.json").write_text(json.dumps(records, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (target/"original_root_names.json").write_text(json.dumps(names, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"v1_files_preserved": len(snapshot), "copied_runtime_sources": len(records)}))


if __name__ == "__main__":
    main()
