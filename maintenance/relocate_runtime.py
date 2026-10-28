"""Repair local runtime paths after moving RUT_Science into this project root.

Scientific reports, checkpoints, weights and historical delivery evidence are
not rewritten. Original mutable session metadata is preserved before rebasing.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "RUT_Science"
OLD = ROOT.parent / "RUT_Science"
AUDIT = ROOT / "maintenance" / "organization_2026-10-21"
BACKUPS = AUDIT / "runtime_before_relocation"
CHANGES = []


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, raw):
    original = path.read_bytes()
    if original == raw:
        return
    backup = BACKUPS / path.relative_to(ROOT)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        raise ValueError("Backup already exists: " + str(backup))
    backup.write_bytes(original)
    path.write_bytes(raw)
    CHANGES.append({"path": path.relative_to(ROOT).as_posix(),
                    "before_sha256": digest(original), "after_sha256": digest(raw)})


def rebase(value):
    if isinstance(value, str):
        for old, new in ((str(OLD), str(PROJECT)), (OLD.as_posix(), PROJECT.as_posix())):
            if value == old or value.startswith(old + ("\\" if "\\" in old else "/")):
                return new + value[len(old):]
        return value
    if isinstance(value, dict):
        return {key: rebase(item) for key, item in value.items()}
    if isinstance(value, list):
        return [rebase(item) for item in value]
    return value


def main():
    # Editable install: only installation metadata is changed, never package code.
    site = PROJECT / ".venv" / "Lib" / "site-packages"
    for path in site.glob("__editable__*rut_science*finder.py"):
        text = path.read_text(encoding="utf-8")
        text = text.replace(repr(str(OLD / "rut_science")), repr(str(PROJECT / "rut_science")))
        save(path, text.encode("utf-8"))
    direct = site / "rut_science-0.5.0.dist-info" / "direct_url.json"
    data = json.loads(direct.read_text(encoding="utf-8"))
    data["url"] = PROJECT.as_uri()
    save(direct, json.dumps(data).encode("utf-8"))
    paths = [PROJECT / ".venv" / "pyvenv.cfg"]
    paths += list((PROJECT / ".venv" / "Scripts").glob("activat*"))
    paths += list((PROJECT / ".venv" / "Scripts").glob("Activat*"))
    for path in paths:
        raw = path.read_bytes().replace(str(OLD).encode(), str(PROJECT).encode())
        save(path, raw)

    # Recreate native console launchers with the relocated interpreter shebang.
    # Existing scripts from other packages remain owned by their distributions.
    from pip._vendor.distlib.scripts import ScriptMaker
    target = PROJECT / ".venv" / "Scripts"
    maker = ScriptMaker(None, str(target))
    maker.executable = str(target / "python.exe")
    maker.clobber = True
    maker.variants = {""}
    entries = {ep.name: ep.value for dist in importlib.metadata.distributions()
               for ep in dist.entry_points if ep.group == "console_scripts"}
    if "pip" in entries:
        entries["pip3"] = entries["pip"]
        entries["pip3.12"] = entries["pip"]
    recreated = []
    for name, value in sorted(entries.items()):
        launcher = target / (name + ".exe")
        if launcher.exists():
            backup = BACKUPS / launcher.relative_to(ROOT)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(launcher, backup)
        recreated.extend(maker.make(f"{name} = {value}"))

    # Rebase mutable science-bot sessions only; frozen delivery evidence stays intact.
    for path in (PROJECT / "outputs").rglob("session.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not {"id", "backend", "planner", "checkpoint"} <= data.keys():
            continue
        moved = rebase(data)
        if moved != data:
            # A changed workspace binding changes the reviewable confirmation hash.
            if moved.get("workspace") != data.get("workspace"):
                moved["confirmed"] = None
                if moved.get("phase") not in {"completed", "abstained", "cancelled"}:
                    moved["phase"] = "paused"
            save(path, (json.dumps(moved, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    for path in (PROJECT / "outputs").rglob("workspace.json"):
        if path.parent.name != ".sciencebot":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        moved = rebase(data)
        if moved != data:
            save(path, (json.dumps(moved, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    # Root-level navigation follows the new folder layout. Frozen evidence stays unchanged.
    path = ROOT / "science_Bot_交付.md"
    save(path, path.read_text(encoding="utf-8").replace("../RUT_Science/", "RUT_Science/").encode("utf-8"))
    result = {"old_project": str(OLD), "new_project": str(PROJECT),
              "changed_runtime_files": CHANGES, "recreated_console_launchers": recreated,
              "frozen_scientific_artifacts_rewritten": False,
              "shared_parent_api_config_retained": True}
    (AUDIT / "relocation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"runtime_files_rebased": len(CHANGES), "console_launchers_recreated": len(recreated)}))


if __name__ == "__main__":
    main()
