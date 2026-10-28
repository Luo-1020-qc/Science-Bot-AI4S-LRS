"""Local, offline smoke checks for the consolidated installation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import torch
from rut_science.configuration import DEFAULT_API_CONFIG, load_api_config
from rut_science.science_bot.contracts import BudgetedResearchSpec
from rut_science.science_bot.session import ScienceSession, ROOT as PROJECT

ROOT = PROJECT.parent
AUDIT = ROOT / "maintenance" / "organization_2026-10-21"


def main():
    torch.set_num_threads(1)
    if (AUDIT / "smoke_sessions").exists():
        raise ValueError("Smoke output already exists")
    results = {}
    for dataset in ("generated", "darcy"):
        session = ScienceSession.create(AUDIT / "smoke_sessions", backend="offline", planner="rl",
                                       spec=BudgetedResearchSpec(dataset=dataset, split="demo"))
        session.confirm(session.confirmation)
        session.run(max_steps=1)
        attempts_at_pause = session.env.state["attempts"]
        code = (
            "import json,sys,torch; torch.set_num_threads(1); "
            "from rut_science.science_bot.session import ScienceSession; "
            "s=ScienceSession.restore(sys.argv[1]); s.run(); "
            "print(json.dumps({'phase':s.meta['phase'],'report':s.env.state['report']}))"
        )
        completed = subprocess.run([sys.executable, "-c", code, str(session.folder)],
                                   capture_output=True, text=True, check=True, timeout=55)
        value = json.loads(completed.stdout)
        restored = ScienceSession.restore(session.folder)
        attempts_before = restored.env.state["attempts"]
        restored.run()
        if restored.env.state["attempts"] != attempts_before:
            raise AssertionError("Completed session repeated an experiment")
        results[dataset] = {"session": str(session.folder), "attempts_at_pause": attempts_at_pause,
                            "completed": value["phase"] == "completed",
                            "scientific_success": value["report"]["scientific_success"],
                            "evaluation_reads": value["report"]["evaluation_reads"],
                            "llm_requests": restored.env.state["requests"],
                            "repeat_run_did_not_repeat_experiment": True}

    records = json.loads((AUDIT / "archive_inspection.json").read_text(encoding="utf-8"))
    preserved = []
    for record in records:
        for item in record["files"]:
            if item["status"] != "historical_difference":
                continue
            path = AUDIT / "extracted" / Path(record["archive"]).stem / item["entry"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise AssertionError("Historical archive file changed")
            preserved.append(item["entry"])
    manifest = json.loads((PROJECT / "models/planner/v1/selected/manifest.json").read_text())
    weights = PROJECT / "models/planner/v1/selected/weights.pt"
    result = {"project_root": str(ROOT), "old_sibling_project_absent": not (ROOT.parent / "RUT_Science").exists(),
              "credential_config_inside_project": DEFAULT_API_CONFIG.parent == ROOT,
              "credential_config_valid": bool(load_api_config()["api_key"]),
              "selected_weights_hash_unchanged": hashlib.sha256(weights.read_bytes()).hexdigest() == manifest["weights_hash"],
              "historical_archive_files_verified": len(preserved), "smoke": results,
              "new_live_model_api_calls": 0}
    assert all(v["completed"] and v["evaluation_reads"] == 1 and v["llm_requests"] == 0
               for v in results.values())
    assert result["selected_weights_hash_unchanged"]
    (AUDIT / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
