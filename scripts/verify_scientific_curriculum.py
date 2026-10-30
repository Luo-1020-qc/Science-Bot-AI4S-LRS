"""Recheck the public-data curriculum without changing historical integrity receipts."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT/"Training_Data/scientific_dialogue_v1"
sys.path.insert(0, str(CURRICULUM))
from acquire import check_raw
from annotation import validate_dialogue
from common import lines, manifest, read, sha, source_code_hashes, verify_files, write
from models import verify_run


def verify(work, run, run_tests=False):
    work = work.resolve()
    evidence = CURRICULUM/"evidence"
    before = read(evidence/"before_training.json")
    verify_files(ROOT, before["sha256"])
    # Local data/models remain ignored, outside the shareable evidence directory.
    for local_name, public_name in (("prepared_001/manifest.json", "public_data_manifest.json"),
            ("sft_001/manifest.json", "public_sft_manifest.json"),
            (run+"/manifest.json", "public_run_manifest.json"),
            (run+"/results.json", "results.json"),
            ("annotation_001/audit.json", "teammate_audit.json")):
        if read(work/local_name) != read(evidence/public_name):
            raise ValueError("Saved curriculum evidence disagrees with local run: "+public_name)
    raw = check_raw(work/"raw_001")
    verify_files(work/"sft_001", read(work/"sft_001/manifest.json")["files"])
    verify_files(work/"annotation_001", read(work/"annotation_001/manifest.json")["files"])
    pending = lines(work/"annotation_001/pending.jsonl")
    rejected = 0
    for item in pending:
        try:
            validate_dialogue(item)
        except (ValueError, KeyError, TypeError):
            rejected += 1
    if rejected != len(pending) or len(pending) != read(evidence/"teammate_audit.json")["scenarios"]:
        raise ValueError("Pending scenario templates leaked into reviewed dialogue data")
    recomputed = verify_run(work/"prepared_001", work/run)
    result = {"passed": True, "checked_utc": datetime.now(timezone.utc).isoformat(),
        "existing_files_unchanged": len(before["sha256"]), "public_downloads_verified": len(raw["files"]),
        "independent_metrics_recomputed": recomputed["recomputed_metrics"],
        "pending_templates_rejected": rejected, "reviewed_scientific_dialogues": 0,
        "model_api_calls": 0, "online_deployment": False,
        "preexisting_repository_check": before["preexisting_repository_check"],
        "source_code_sha256": source_code_hashes(), "verifier_sha256": sha(Path(__file__)),
        "test_sha256": manifest(CURRICULUM, [p.relative_to(CURRICULUM).as_posix()
                                                for p in (CURRICULUM/"tests").glob("test_*.py")])}
    if run_tests:
        code_before = source_code_hashes()
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(CURRICULUM/"tests"), "-v"]
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, encoding="utf-8", timeout=60)
        if completed.returncode or code_before != source_code_hashes():
            raise ValueError("Curriculum tests failed or source changed: "+completed.stderr[-2000:])
        result["tests"] = {"passed": True, "output": completed.stderr.strip(), "command": "unittest discover -s Training_Data/scientific_dialogue_v1/tests -v"}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT/".local/scientific_dialogue_v1")
    parser.add_argument("--run", default="run_002")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--receipt", type=Path, help="Save a new receipt; existing receipts are never overwritten")
    args = parser.parse_args()
    if not args.run.startswith("run_") or "/" in args.run or "\\" in args.run or ":" in args.run:
        raise ValueError("Expected local run directory name")
    result = verify(args.work, args.run, args.run_tests)
    if args.receipt:
        write(args.receipt, result)
    print(json.dumps({k: v for k, v in result.items() if k not in {"tests", "source_code_sha256", "test_sha256"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
