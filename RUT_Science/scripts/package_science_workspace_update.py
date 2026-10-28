"""Verify and package the workspace update without changing the original v1 ZIP."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile
from rut_science.science_bot.session import ROOT, ScienceSession
from rut_science.util import write_json


def main():
    output = ROOT/"delivery"/"workspace_update"
    log = (output/"tests.log").read_text(encoding="utf-8", errors="replace")
    count = re.search(r"Ran (\d+) tests", log)
    skipped = re.search(r"OK \(skipped=(\d+)\)", log)
    if not count or "\nOK" not in log or "FAILED (" in log:
        raise ValueError("Complete passing regression log required")
    project = ROOT/"outputs"/"workspace_smoke"/"workspace demo 项目"
    records = list((project/".sciencebot"/"sessions").glob("*/session.json"))
    session = next((ScienceSession.restore(p.parent, workspace=project) for p in records
                    if p.parent.name == "3ca6b34b5ce64c2c9314bcebb85d77ec"), None)
    if session is None:
        raise ValueError("Interactive workspace smoke evidence is missing")
    history = (session.folder/"terminal.history").read_text(encoding="utf-8")
    restore_code = ("import json,sys; from rut_science.science_bot.session import ScienceSession; "
                    "s=ScienceSession.restore(sys.argv[1],workspace=sys.argv[2]); "
                    "print(json.dumps({'id':s.meta['id'],'workspace_id':s.workspace.binding['workspace_id']}))")
    restored = subprocess.run([sys.executable, "-c", restore_code, session.meta["id"], str(project)], cwd=ROOT,
                              capture_output=True, timeout=60)
    (output/"restore_process.log").write_bytes(restored.stdout+restored.stderr)
    restore_result = json.loads(restored.stdout) if restored.returncode == 0 else {}
    checks = {"full_regression_suite": True,
              "workspace_bound_to_caller_directory": session.workspace.root == project.resolve(),
              "local_commands_exercised": all("+"+c in history for c in ("/workspace", "/files *.py", "/read dynamic_cvit_demo.py")),
              "same_session_exited_and_restored": restore_result.get("id") == session.meta["id"] and
                  restore_result.get("workspace_id") == session.workspace.binding["workspace_id"],
              "local_reads_used_no_scientific_resources": session.env.state["cu"] == 0 and session.env.state["requests"] == 0,
              "trained_policy_loads": session.policy.identity == session.meta["policy_identity"],
              "windows_junction_cases_passed": all(re.search(re.escape(name)+r".*\.\.\. ok", log)
                  for name in ("test_directory_junction_escape_is_not_listed_or_read", "test_workspace_state_cannot_be_redirected",
                               "test_default_session_directory_cannot_be_redirected"))}
    if not all(checks.values()):
        raise ValueError("Workspace acceptance check failed: "+", ".join(k for k, value in checks.items() if not value))
    files = [ROOT/p for p in (
        "rut_science/science_bot/workspace.py", "rut_science/science_bot/session.py",
        "rut_science/science_bot/terminal.py", "rut_science/science_bot/api.py",
        "tests/test_science_workspace.py", "docs/Science_Bot_Workspace_zh.md",
        "delivery/README_运行与复现.md", "scripts/package_science_workspace_update.py")]
    files += [ROOT.parent/p for p in ("Start-ScienceBot.ps1", "science-bot.cmd", "science_Bot_交付.md")]
    verification = {"schema_version": "workspace_update_v1", "passed": True, "checks": checks,
        "tests": {"run": int(count[1]), "skipped": int(skipped[1]) if skipped else 0},
        "skip_reason": "Windows account cannot create file symlinks; directory junction tests passed",
        "smoke_session": str(session.folder), "commands": ["/workspace", "/files *.py", "/read dynamic_cvit_demo.py", "/exit"],
        "api": "server-bound workspace creation and client path override rejection verified by regression tests",
        "scope": "project identity, local file reads, isolated sessions and restoration; scientific actions unchanged",
        "rl_retrained": False, "new_live_model_api_calls": 0,
        "source_hashes": {p.relative_to(ROOT.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    write_json(output/"verification.json", verification)
    files += [output/"verification.json", output/"tests.log", output/"restore_process.log", output/"README.md"]
    destination = ROOT.parent/"science_Bot_workspace_update.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            if not path.resolve().is_relative_to(ROOT.parent.resolve()):
                raise ValueError("Artifact escaped project root")
            archive.write(path, path.relative_to(ROOT.parent).as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Workspace update ZIP is corrupt")
    print(json.dumps({"passed": True, "tests": verification["tests"], "zip": str(destination),
                      "bytes": destination.stat().st_size}, ensure_ascii=True))


if __name__ == "__main__":
    main()
