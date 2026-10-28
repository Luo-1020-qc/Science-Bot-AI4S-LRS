"""Portable post-cleanup protection checks; no historical absolute paths required."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""): h.update(chunk)
    return h.hexdigest()


def check_project(root=ROOT):
    root = Path(root).resolve()
    manifest = json.loads((root/"docs/cleanup/2026-10-28/protected_current.json").read_text(encoding="utf-8"))
    integration = root/"docs/integration/tool_library_2026-10-28"
    edits = json.loads((integration/"authorized_source_changes.json").read_text(encoding="utf-8"))["files"] if (integration/"authorized_source_changes.json").exists() else {}
    allowed = {"RUT_Science/rut_science/science_bot/general/registry.py", "RUT_Science/rut_science/science_bot/general/router.py",
               "RUT_Science/rut_science/science_bot/general/conversation.py", "RUT_Science/rut_science/science_bot/terminal.py"}
    if set(edits)-allowed: raise ValueError("Integration overlay exceeds authorized host wiring")
    if any(row["before_sha256"] != manifest["sha256"].get(name) for name, row in edits.items()):
        raise ValueError("Integration overlay is not based on the original protected source")
    changed = [name for name, checksum in manifest["sha256"].items() if not (root/name).is_file() or sha(root/name) != edits.get(name, {}).get("sha256", checksum)]
    runtime = json.loads((integration/"runtime_manifest.json").read_text(encoding="utf-8")) if (integration/"runtime_manifest.json").exists() else {"sha256": {}}
    changed += [name for name, checksum in runtime["sha256"].items() if not (root/name).is_file() or sha(root/name) != checksum]
    if changed: raise ValueError("Protected Harness/weight files changed: "+str(changed[:12]))
    return {"passed": True, "protected_files_checked": len(manifest["sha256"]), "authorized_host_changes": len(edits), "integration_runtime_files_checked": len(runtime["sha256"]), "changed": []}


if __name__ == "__main__": print(json.dumps(check_project()))
