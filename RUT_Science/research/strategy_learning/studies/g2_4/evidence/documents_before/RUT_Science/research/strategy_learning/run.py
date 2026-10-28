"""Unified launcher for research; each study stays in its own guarded process."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
STUDIES = ("g2_2", "g2_3")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["list", "test", "verify", "demo", "status"])
    parser.add_argument("--study", choices=["all", *STUDIES], default="all")
    args = parser.parse_args(argv)
    selected = STUDIES if args.study == "all" else (args.study,)
    if args.action == "list":
        print(json.dumps({"studies": list(STUDIES), "root": str(ROOT), "live_tools_connected": False,
                          "live_policy": "unchanged; production general interview defaults to rule"}, ensure_ascii=False))
        return 0
    results = []
    for study in selected:
        folder = ROOT/"studies"/study
        if args.action == "status":
            current = folder/"evidence/current_verification.json"
            report = json.loads(current.read_text(encoding="utf-8")) if current.exists() else {"passed": False, "note": "Run test then verify"}
            print(json.dumps({"study": study, "passed": report["passed"], "tests": report.get("tests"), "path": str(folder)}, ensure_ascii=False))
            continue
        completed = subprocess.run([sys.executable, "-B", str(folder/"run.py"), args.action], cwd=folder,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
        if completed.stdout:
            print(completed.stdout.strip())
        if completed.stderr:
            print(completed.stderr.strip(), file=sys.stderr)
        results.append({"study": study, "action": args.action, "exit_code": completed.returncode})
    if results:
        path = ROOT/"integration_results"
        path.mkdir(exist_ok=True)
        (path/(args.action+".json")).write_text(json.dumps({"date": "2026-10-27", "results": results,
             "no_training_requested": True, "no_real_tools_requested": True}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return 0 if all(item["exit_code"] == 0 for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
