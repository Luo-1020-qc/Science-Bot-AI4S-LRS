"""Copy G2.2 fixtures/source into this new folder only; never import live code."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parent/"g2_2"


def copy(source, target):
    target = target.resolve()
    if not target.is_relative_to(ROOT) or source.resolve() != source:
        raise ValueError("Copy scope violation")
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = source.read_bytes()
    if target.exists() and target.read_bytes() != raw:
        raise ValueError("Refusing to replace an existing different copy")
    if not target.exists():
        target.write_bytes(raw)
    return {"source": str(source), "copy": str(target.relative_to(ROOT)),
            "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    if (ROOT/"relocation.json").exists():
        print(json.dumps({"already_consolidated": True, "historical_copies_preserved": True,
                          "current_previous_study": str(PREVIOUS)}))
        return
    selected = ("__init__", "guard", "contracts", "environment", "verifier", "mock_tools", "policies", "tasks")
    records = [copy(PREVIOUS/"lab"/(name+".py"), ROOT/"lab"/(name+".py")) for name in selected]
    for folder, pattern in ((PREVIOUS/"lab", "*.py"), (PREVIOUS/"tests", "*.py"),
                            (PREVIOUS/"reference_copy/examples/g2", "*.csv"),
                            (PREVIOUS/"reference_copy/examples/g2", "*.json")):
        for source in sorted(folder.glob(pattern)):
            records.append(copy(source, ROOT/"reference_copy/G2_2"/source.relative_to(PREVIOUS)))
    for source in (PREVIOUS/"bank/seal.json", PREVIOUS/"evidence/benchmark.json", PREVIOUS/"README_本轮交付.md"):
        records.append(copy(source, ROOT/"reference_copy/G2_2"/source.relative_to(PREVIOUS)))
    (ROOT/"evidence").mkdir(exist_ok=True)
    (ROOT/"evidence/copied_files.json").write_text(json.dumps({"records": records, "copied_tests_are_reference_only": True}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"copied": len(records), "writes_only_inside": str(ROOT)}))


if __name__ == "__main__":
    main()
