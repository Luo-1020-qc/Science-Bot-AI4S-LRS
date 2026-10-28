"""Audit saved model-output acceptance evidence; never makes model requests."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil

from rich.console import Console
from rut_science.configuration import load_api_config
from rut_science.science_bot.session import ROOT, ScienceSession
from rut_science.science_bot.terminal import show_model_output
from rut_science.util import write_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT/"delivery"/"model_output_update"
    info = json.loads((output/"live_session.json").read_text(encoding="utf-8"))
    session = ScienceSession.restore(info["session"])
    ledger = json.loads((session.folder/"llm_ledger.json").read_text(encoding="utf-8"))
    before = json.loads((output/"replay_before.json").read_text(encoding="utf-8"))
    after = {"requests": ledger["requests"], "accounted_tokens": ledger["accounted_tokens"],
             "cu": session.env.state["cu"], "evaluation_reads": session.env.state["evaluation_reads"]}
    calls = session.model_output("list")["calls"]
    history = (session.folder/"terminal.history").read_text(encoding="utf-8")
    raw_log = (output/"tests.log").read_bytes()
    log = raw_log.decode("utf-16" if raw_log.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8")
    # Normalize the Windows shell capture for portable reading.
    (output/"tests.log").write_text(log, encoding="utf-8")
    count = re.search(r"Ran (\d+) tests", log)
    skipped = re.search(r"OK \(skipped=(\d+)\)", log)
    stream = io.StringIO()
    console = Console(file=stream, width=110, highlight=False, force_terminal=False)
    for call in calls:
        show_model_output(console, session, str(call["request_index"]))
    show_model_output(console, session, "list")
    (output/"terminal_replay.txt").write_text(stream.getvalue(), encoding="utf-8")
    roles = [call["role"] for call in calls]
    checks = {
        "regression_tests": bool(count and int(count[1]) == 171 and "FAILED (" not in log and "\nOK" in log),
        "real_provider_calls": len(ledger["calls"]) == 3 and all(c["status"] == "ok" for c in ledger["calls"]),
        "actual_outputs_saved_and_host_accepted": all(c["status"] == "accepted" for c in calls),
        "rl_has_no_fabricated_llm_selector": roles == ["intake_v2", "candidate_generator_v1", "report_explainer_v1"] and session.meta["planner"] == "rl",
        "replay_resource_ledger_unchanged": before == after,
        "real_terminal_replay_commands_exercised": all("+"+cmd in history for cmd in ("/confirm", "/model-output list", "/model-output 3", "/model-output", "/exit")),
        "scientific_report_retained": bool(session.env.state["report"]["scientific_success"] and (session.folder/"report.json").exists()),
        "explanation_checked_and_saved": (session.folder/"explanation.json").exists() and not session.meta.get("explanation_error"),
        "single_sealed_evaluation": session.env.state["evaluation_reads"] == 1,
        "no_new_distribution_zip": not list(output.rglob("*.zip")) and not list(ROOT.parent.glob("*.zip")),
    }
    # Inspect the new evidence only; never print the credential or HTTP headers.
    secret = load_api_config()["api_key"].encode("utf-8")
    checks["credential_not_in_new_evidence"] = not any(secret in p.read_bytes() for p in output.rglob("*") if p.is_file())
    files = [ROOT/p for p in (
        "rut_science/science_bot/model_output.py", "rut_science/science_bot/llm.py",
        "rut_science/science_bot/session.py", "rut_science/science_bot/terminal.py",
        "tests/test_model_output.py", "docs/Science_Bot_Model_Output_zh.md",
        "scripts/verify_model_output_update.py")]
    files += [ROOT.parent/"science-bot.cmd", ROOT.parent/"Start-ScienceBot.ps1"]
    for path in files:
        dest = output/"source_snapshot"/path.relative_to(ROOT.parent)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    result = {"schema_version": "model_output_update_v1", "passed": all(checks.values()), "checks": checks,
              "tests": {"run": int(count[1]) if count else None,
                        "passed": int(count[1])-int(skipped[1]) if count and skipped else None,
                        "skipped": int(skipped[1]) if skipped else 0},
              "new_live_model_api_calls": len(ledger["calls"]),
              "usage": {k: ledger[k] for k in ("reported_prompt_tokens", "reported_completion_tokens", "accounted_tokens", "monetary_cost")},
              "live_session": str(session.folder), "after_replay": after,
              "source_hashes": {p.relative_to(ROOT.parent).as_posix(): sha(p) for p in files},
              "weights_hash": session.policy_identity, "rl_retrained": False,
              "distribution": "in_place_source_and_documents_no_zip",
              "terminal_observation": "Existing CMD launcher used for the live run and a second process; output panels and saved-history replay inspected in the real terminal",
              "limitations": ["Displays parsed application JSON, not complete HTTP envelopes or streaming output",
                              "Host checks preserve their existing scope; they do not prove every model statement",
                              "Real API acceptance used one generated-task RL session; selector and failure cases use mock HTTP tests",
                              "The one skipped regression requires Windows file-symlink privileges"]}
    write_json(output/"verification.json", result)
    if not result["passed"]:
        raise ValueError("Model-output verification failed: "+", ".join(k for k,v in checks.items() if not v))
    print(json.dumps({"passed": True, "tests": result["tests"], "calls": result["new_live_model_api_calls"],
                      "tokens": result["usage"]["accounted_tokens"], "replay_unchanged": before == after}))


if __name__ == "__main__":
    main()
