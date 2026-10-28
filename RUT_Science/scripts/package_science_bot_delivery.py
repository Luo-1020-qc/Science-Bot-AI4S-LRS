"""Package source, evidence and trained weights; exclude data and credentials."""
from pathlib import Path
import hashlib
import json
import zipfile
from rut_science.science_bot.session import ROOT, MODELS
from rut_science.configuration import load_profiles
from rut_science.util import write_json


def main():
    parent = ROOT.parent
    destination = parent/"science_Bot_delivery_2026-10-20.zip"
    files = set()
    for folder in (ROOT/"rut_science", ROOT/"scripts", ROOT/"tests", ROOT/"prompts", ROOT/"delivery", MODELS):
        for path in folder.rglob("*"):
            if (path.is_file() and "__pycache__" not in path.parts and ".matplotlib" not in path.parts
                    and path.name != "file_manifest.json" and not path.name.endswith(".pyc")):
                files.add(path)
    for filename in ("pyproject.toml", "README.md", "requirements-darcy.lock.txt", "requirements-planning.lock.txt"):
        files.add(ROOT/filename)
    for filename in ("Start-ScienceBot.ps1", "science-bot.cmd", "science_Bot_交付.md", "LangGraph_RL_demo_规划.md", "阶段性总结1.md"):
        files.add(parent/filename)
    secrets_to_check = []
    try:
        for profile in load_profiles():
            for key, value in profile.items():
                if ("API" in key.upper() or "KEY" in key.upper()) and isinstance(value, str) and len(value) > 16 and not value.startswith("http"):
                    secrets_to_check.append(value.encode("utf-8"))
    except ValueError:
        pass
    index = []
    for path in sorted(files):
        if not path.resolve().is_relative_to(parent.resolve()):
            raise ValueError("Artifact escaped project root")
        if path.name in {"API_key_Agent.json", ".local_token"}:
            raise ValueError("Credential file selected for packaging")
        raw = path.read_bytes()
        if any(secret in raw for secret in secrets_to_check):
            raise ValueError("Credential content found in selected artifact; packaging stopped")
        index.append({"path": path.relative_to(parent).as_posix(), "bytes": len(raw),
                      "sha256": hashlib.sha256(raw).hexdigest()})
    manifest_path = ROOT/"delivery"/"file_manifest.json"
    write_json(manifest_path, {"files": index, "manifest_excludes_itself": True,
               "credential_scan_passed": True, "local_credentials_available_for_scan": bool(secrets_to_check),
               "excluded": ["raw and bundled Darcy data", "virtual environment", "API credentials", "local service token", "development pilot weights"]})
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
        for path in sorted(files | {manifest_path}):
            archive.write(path, path.relative_to(parent).as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Delivery ZIP integrity check failed")
    print(json.dumps({"zip": str(destination), "files": len(index)+1, "bytes": destination.stat().st_size,
                      "credential_scan_passed": True}, ensure_ascii=True))


if __name__ == "__main__":
    main()
