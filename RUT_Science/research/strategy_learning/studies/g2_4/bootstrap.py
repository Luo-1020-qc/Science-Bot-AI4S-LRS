"""Copy reference material and navigation backups; never imports copied code."""
from pathlib import Path
import hashlib
import json
import shutil

LAB = Path(__file__).resolve().parent
PROJECT = LAB.parents[4]


def main():
    sources = [PROJECT/"Reference_Paper/Harness_Engineering_Agent_Insights.md",
        PROJECT/"RUT_Science/rut_science/science_bot/general/interview/validation.py",
        PROJECT/"RUT_Science/research/strategy_learning/studies/g2_3/evidence/scoring_audit.json",
        PROJECT/"RUT_Science/research/strategy_learning/studies/g2_3/lab/contracts.py",
        PROJECT.parent.parent/"DSC6008 Design of Experiments/Assignment2/Assignment2_参考答案与解析_中英对照.md"]
    records = []
    for i, source in enumerate(sources):
        target = LAB/"reference_copy"/f"{i:02d}_{source.name}"
        target.parent.mkdir(exist_ok=True)
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError("Never overwrite a different reference copy")
        shutil.copy2(source, target)
        records.append({"source": str(source), "copy": target.relative_to(LAB).as_posix(),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "reference_only_not_imported": True})
    manifest = LAB/"evidence/copied_files.json"
    if manifest.exists():
        raise ValueError("Reference manifest already exists")
    manifest.write_text(json.dumps({"files": records}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for relative in ("README.md", "science_Bot_交接.md", "science_Bot_交付.md", "阶段性总结2_2026-10-27.md",
                     "RUT_Science/README.md", "RUT_Science/research/strategy_learning/README.md", "RUT_Science/research/strategy_learning/run.py"):
        target = LAB/"evidence/documents_before"/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(PROJECT/relative, target)
    print(json.dumps({"copied_reference_files": len(records), "study": "g2_4"}))


if __name__ == "__main__":
    main()
