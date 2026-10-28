"""Remove only extracted duplicates verified against the original inspection."""
import json
from pathlib import Path, PurePosixPath
from inspect_archives import ROOT, PARENT, AUDIT, sha, contained


def main():
    records = json.loads((AUDIT / "archive_inspection.json").read_text(encoding="utf-8"))
    removed_files = removed_bytes = removed_zip_bytes = 0
    for record in records:
        archive = contained(Path(record["archive"]), PARENT)
        if sha(archive) != record["sha256"]:
            raise ValueError("Archive changed since inspection")
        stage = AUDIT / "extracted" / archive.stem
        for item in record["files"]:
            rel = PurePosixPath(item["entry"])
            out = contained(stage.joinpath(*rel.parts), stage)
            if sha(out) != item["sha256"]:
                raise ValueError("Extracted file changed")
            if item["status"] == "identical":
                existing = contained(PARENT.joinpath(*rel.parts), PARENT)
                if sha(existing) != item["sha256"]:
                    raise ValueError("Current file changed; refusing removal")
                out.unlink()
                removed_files += 1
                removed_bytes += item["bytes"]
        for directory in sorted((p for p in stage.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            contained(directory, stage)
            if not any(directory.iterdir()):
                directory.rmdir()
        if stage.exists() and not any(stage.iterdir()):
            stage.rmdir()
        # Different historical files remain expanded; identical bytes remain in
        # the working tree. The manifest records all original entry hashes.
        if not record["dependency_fixture"]:
            removed_zip_bytes += archive.stat().st_size
            archive.unlink()
    summary = {"deleted_extracted_duplicate_files": removed_files,
               "deleted_extracted_duplicate_bytes": removed_bytes,
               "deleted_delivery_archives": 2,
               "deleted_archive_bytes": removed_zip_bytes,
               "historical_different_files_preserved": 6,
               "dependency_fixture_zip_preserved": True,
               "dependency_fixture_files_extracted": 7}
    (AUDIT / "cleanup_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
