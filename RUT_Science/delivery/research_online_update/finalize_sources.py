"""Record explicit source integration changes and preserve available originals."""
from pathlib import Path
import hashlib
import json
import shutil

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
ALLOWED = {"RUT_Science/rut_science/science_bot/terminal.py",
    *("RUT_Science/rut_science/science_bot/general/"+name+".py" for name in ("contracts", "conversation", "graph", "registry", "router"))}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    baseline = json.loads((HERE/"protected_before.json").read_text(encoding="utf-8"))["files"]
    changes = {}
    for relative, original in baseline.items():
        path = PROJECT/relative
        if sha(path) == original:
            continue
        if relative not in ALLOWED:
            raise ValueError("Unexpected protected source/artifact edit: "+relative)
        changes[relative] = {"sha256": sha(path), "before_sha256": original,
            "reason": "User authorized exposing all research interfaces through the existing local Agent; simulation and DOE only"}
        candidates = [PROJECT/"RUT_Science/delivery/g2_1_update/source_snapshot"/relative,
            PROJECT/"RUT_Science/delivery/g2_1_update/source_snapshot"/relative.removeprefix("RUT_Science/")]
        for source in candidates:
            if source.is_file() and sha(source) == original:
                target = HERE/"source_before"/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                changes[relative]["original_backup"] = target.relative_to(HERE).as_posix()
                break
    (HERE/"authorized_source_changes.json").write_text(json.dumps({"date": "2026-10-27", "files": changes}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    study = PROJECT/"RUT_Science/research/strategy_learning/studies/g2_4"
    old = study/"evidence/current_verification.json"
    target = HERE/"historical_before/g2_4_verification.json"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, target)
    print(json.dumps({"authorized_changed_source_files": len(changes)}))


if __name__ == "__main__":
    main()
