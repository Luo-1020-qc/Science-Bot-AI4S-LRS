"""Copy public synthetic examples and read-only reference tests, no credentials."""
from pathlib import Path
from .guard import LAB, PROJECT, file_hash, write_json, ensure_local


def copy_fixtures():
    sources = []
    app = PROJECT/"RUT_Science"
    for folder, pattern in ((app/"examples/g2", "*.csv"), (app/"examples/g2", "*_design.json"),
                            (app/"tests", "test_*interview*.py"),
                            (app/"rut_science/science_bot/general/interview", "*.py")):
        sources.extend(sorted(folder.glob(pattern)))
    sources += [app/"tests/test_tabular_g2.py", app/"models/design_interview_bc/manifest.json",
                app/"models/design_interview_bc/policy.json", app/"models/design_interview_bc/evaluation.json",
                app/"docs/Science_Bot_G2_1_设计访谈与学习环境_zh.md"]
    records = []
    for source in sources:
        relative = source.relative_to(app)
        target = ensure_local(LAB/"reference_copy"/relative)
        if source.resolve() != source or source.suffix not in {".csv", ".json", ".py", ".md"}:
            raise ValueError("Reference source must be an ordinary explicitly selected file")
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        if target.exists() and target.read_bytes() != raw:
            raise ValueError("Never replace a changed reference copy")
        if not target.exists():
            target.write_bytes(raw)
        records.append({"source": str(source), "copy": target.relative_to(LAB).as_posix(), "sha256": file_hash(target), "bytes": len(raw)})
    value = {"files": records, "count": len(records), "copied_code_executed": False,
             "purpose": "Read-only reference; lab tests never import these modules or register their real tools"}
    write_json(LAB/"evidence/copied_files.json", value)
    return {"copied_files": len(records), "matched": all(file_hash(Path(r["source"])) == r["sha256"] for r in records)}
