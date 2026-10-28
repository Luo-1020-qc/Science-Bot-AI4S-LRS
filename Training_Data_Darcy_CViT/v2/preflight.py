"""Run approved expert task extensions through the actual offline tool environment."""
import argparse
import json
from pathlib import Path
from protocol import ROOT, digest, sha, verify_runtime, write
from build_dataset import reference_episode


def preflight(path):
    path = Path(path).absolute()
    if path.resolve() != path or not path.is_relative_to(ROOT): raise ValueError("Select a v2-local imported extension")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value["version"] != "expert_task_extension_v2" or digest(value["records"]) != value["records_hash"]:
        raise ValueError("Imported extension changed")
    reports = []
    for task in value["records"]:
        try:
            ep = reference_episode(task)
            reports.append({"task_id": task["task_id"], "passed": True, "steps": len(ep["steps"]), "classification": ep["classification"]})
        except Exception as exc:
            reports.append({"task_id": task["task_id"], "passed": False, "error": str(exc)[:300]})
    result = {"passed": all(r["passed"] for r in reports), "records_hash": value["records_hash"], "catalog_hash": verify_runtime(),
        "environment_hash": sha(ROOT/"environment.py"), "reward_protocol_hash": sha(ROOT/"protocol.py"),
        "reports": reports, "scope": "Tool/schema/reward mechanical compatibility; expert correctness and generalization not established"}
    write(path.with_suffix(".preflight.json"), result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extension", type=Path)
    args = parser.parse_args()
    result = preflight(args.extension)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)
