"""Extract and compare delivery archives without overwriting current files."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
AUDIT = ROOT / "maintenance" / "organization_2026-10-21"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def contained(path, root):
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Path escapes authorized project: " + str(path))
    return path


def main():
    AUDIT.mkdir(parents=True, exist_ok=True)
    archives = list(ROOT.glob("*.zip"))
    archives += list((PARENT / "RUT_Science" / ".venv").rglob("*.zip"))
    records = []
    for archive in archives:
        stage = AUDIT / "extracted" / archive.stem
        if stage.exists():
            raise ValueError("Extraction destination already exists")
        record = {"archive": str(archive), "sha256": sha(archive),
                  "compressed_bytes": archive.stat().st_size,
                  "dependency_fixture": ".venv" in archive.parts, "files": []}
        with zipfile.ZipFile(archive) as z:
            seen = set()
            for entry in z.infolist():
                rel = PurePosixPath(entry.filename)
                if rel.is_absolute() or ".." in rel.parts or "\\" in entry.filename or ":" in entry.filename:
                    raise ValueError("Unsafe ZIP entry")
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError("ZIP symlink refused")
                if entry.is_dir():
                    continue
                if entry.filename.casefold() in seen:
                    raise ValueError("Duplicate ZIP entry")
                seen.add(entry.filename.casefold())
                out = contained(stage.joinpath(*rel.parts), stage)
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(entry) as source, out.open("xb") as dest:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        dest.write(block)
                if record["dependency_fixture"]:
                    existing = archive.parent.joinpath(*rel.parts)
                else:
                    if rel.parts[0] not in {"RUT_Science", "LangGraph_RL_Agent"}:
                        raise ValueError("Unexpected archive project root")
                    existing = contained(PARENT.joinpath(*rel.parts), PARENT)
                digest = sha(out)
                status = "identical" if existing.is_file() and sha(existing) == digest else (
                    "historical_difference" if existing.exists() else "archive_only")
                record["files"].append({"entry": entry.filename, "bytes": entry.file_size,
                                        "sha256": digest, "status": status})
        record["counts"] = {key: sum(f["status"] == key for f in record["files"])
                            for key in ("identical", "historical_difference", "archive_only")}
        records.append(record)
    (AUDIT / "archive_inspection.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps([{k: v for k, v in r.items() if k != "files"} for r in records], ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
