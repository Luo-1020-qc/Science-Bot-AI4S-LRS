"""Current portable research audit; historical migration proofs are archived."""
import json
from pathlib import Path
import re
import runpy

HUB = Path(__file__).resolve().parent
PROJECT = HUB.parents[2]

def verify_study(folder):
    folder = Path(folder).resolve()
    study = folder.name
    if folder.parent != HUB/"studies" or study not in {"g2_2", "g2_3", "g2_4"}:
        raise ValueError("Unknown study")
    protected = runpy.run_path(str(PROJECT/"scripts/integrity.py"))["check_project"](PROJECT)
    manifest = json.loads((HUB/"online_artifacts.json").read_text(encoding="utf-8"))["studies"][study]
    sha = runpy.run_path(str(PROJECT/"scripts/integrity.py"))["sha"]
    if any(sha(folder/name) != checksum for name, checksum in manifest.items()):
        raise ValueError("Frozen research changed")
    log = (folder/"evidence/current_tests.log").read_text(encoding="utf-8")
    count = re.search(r"Ran (\d+) tests", log)
    if not count or "\nOK" not in log or "FAILED" in log: raise ValueError("Current study tests have not passed")
    value = {"study": study, "passed": True, "tests": int(count[1]), "frozen_artifacts_checked": len(manifest),
        "protected_harness_files_checked": protected["protected_files_checked"], "policies_retrained": False,
        "real_tool_executions": 0, "scope": "Current cleaned layout; original migration baselines remain in external archive"}
    (folder/"evidence/current_verification.json").write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")
    return value

if __name__ == "__main__":
    for study in ("g2_2", "g2_3", "g2_4"): print(json.dumps(verify_study(HUB/"studies"/study)))
