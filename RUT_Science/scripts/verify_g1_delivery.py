"""Audit G1 saved live evidence and run bounded offline acceptance; no API calls."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import torch
from rich.console import Console

from rut_science.configuration import load_api_config
from rut_science.science_bot.general.conversation import GeneralSession, ROOT
from rut_science.science_bot.session import ScienceSession
from rut_science.science_bot.terminal import show_model_output
from rut_science.util import write_json

OUT = ROOT/"delivery"/"g1_update"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def offline_acceptance():
    saved = OUT/"offline_verification.json"
    if saved.exists():
        return json.loads(saved.read_text(encoding="utf-8"))
    torch.set_num_threads(1)
    project = OUT/"fixture_project"
    session = GeneralSession.create(OUT/"offline_sessions", backend="offline", workspace=project)
    fresh_has_no_environment = session.env is None and not (session.folder/"environment.json").exists()
    cases = {}
    for text in ("什么是区组设计？", "未知任务abc", "运行 Darcy 预测温度场", "在 generated 做分类实验",
                 "运行 generated 实验，预算6.5", "运行 Darcy，门槛-0.2", "用 CViT 训练当前模型",
                 "运行 Darcy 实验，alpha=0.1", "设计一个新实验"):
        value = session.message(text)
        cases[text] = {"intent": value["intent"], "no_numeric_environment": session.env is None}
    read = session.message("读取 model.py")
    reference = read["evidence_refs"][0]
    numeric = {}
    for dataset in ("generated", "darcy"):
        child_parent = GeneralSession.create(OUT/"offline_sessions", backend="offline", planner="rl")
        child_parent.message(f"运行 {dataset} 实验，预算6，门槛0.20")
        child_parent.confirm(child_parent.confirmation)
        child_parent.run(max_steps=1)
        paused_attempts = child_parent.env.state["attempts"]
        code = ("import json,sys,torch; torch.set_num_threads(1); "
                "from rut_science.science_bot.session import ScienceSession; "
                "s=ScienceSession.restore(sys.argv[1]); s.run(); "
                "print(json.dumps({'success':s.env.state['report']['scientific_success'],'evaluation_reads':s.env.state['evaluation_reads']}))")
        process = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(child_parent.folder)],
                                 capture_output=True, text=True, encoding="utf-8", timeout=55, check=True)
        value = json.loads(process.stdout)
        restored = GeneralSession.restore(child_parent.folder)
        before_attempts = restored.env.state["attempts"]
        restored.run()
        numeric[dataset] = {"session": str(restored.folder), "attempts_at_pause": paused_attempts,
                            **value, "repeat_run_did_not_repeat_experiment": restored.env.state["attempts"] == before_attempts,
                            "model_requests": restored.resources()["llm_requests"]}
    legacy = ROOT/"delivery/model_output_update/sessions/63a68b63e8b9488a930fc79b4ca77d4e"
    old_files = {p.relative_to(legacy).as_posix(): sha(p) for p in legacy.rglob("*") if p.is_file()}
    old = ScienceSession.restore(legacy)
    old_status = old.status()
    result = {"fresh_no_numeric_environment": fresh_has_no_environment, "route_cases": cases,
              "offline_file_reference": reference,
              "file_reference_matches_sha": sha(project/"model.py")[:12] in reference,
              "model_requests_for_routing_and_local_read": session.resources()["llm_requests"],
              "numeric": numeric,
              "legacy_snapshot_restores": old_status["report_available"] and old.env.done,
              "legacy_snapshot_unchanged": old_files == {p.relative_to(legacy).as_posix(): sha(p) for p in legacy.rglob("*") if p.is_file()}}
    write_json(saved, result)
    return result


def main():
    offline = offline_acceptance()
    info = json.loads((OUT/"live_session.json").read_text(encoding="utf-8"))
    session = GeneralSession.restore(info["session"])
    ledger = json.loads((session.folder/"llm_ledger.json").read_text(encoding="utf-8"))
    before = json.loads((OUT/"replay_before.json").read_text(encoding="utf-8"))
    history = (session.folder/"terminal.history").read_text(encoding="utf-8")
    log = (OUT/"tests.log").read_text(encoding="utf-8")
    count = re.search(r"Ran (\d+) tests", log)
    skipped = re.search(r"OK \(skipped=(\d+)\)", log)
    calls = session.model_output("list")["calls"]
    roles = [call["role"] for call in calls]
    tools = [json.loads(p.read_text(encoding="utf-8")) for p in (session.folder/"tool_results").glob("*.json")]
    actual_reads = [tool for tool in tools if "text" in tool and "sha256" in tool]
    turns = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((session.folder/"turns").glob("*_result.json"))]
    project_answers = [turn for turn in turns if turn["intent"] == "project_qa"]
    wire = json.loads((session.folder/"turns/0002_messages.json").read_text(encoding="utf-8"))
    proposed_ids = {c["id"] for message in wire for c in message.get("tool_calls", [])}
    result_ids = {message["tool_call_id"] for message in wire if message["role"] == "tool"}
    default_sessions = list((OUT/"fixture_project/.sciencebot/sessions").glob("*/session.json"))
    default_cli_ok = False
    for path in default_sessions:
        restored = ScienceSession.restore(path.parent)
        if restored.meta.get("engine_version") == "general_v1" and restored.env is None and restored.resources()["llm_requests"] == 0:
            default_cli_ok = True
    checks = {
        "full_regression": bool(count and "FAILED (" not in log and "\nOK" in log),
        "fresh_no_implicit_numeric": offline["fresh_no_numeric_environment"],
        "unknown_and_unsupported_no_numeric": all(case["no_numeric_environment"] for case in offline["route_cases"].values()),
        "offline_reads_have_real_source": offline["file_reference_matches_sha"] and offline["model_requests_for_routing_and_local_read"] == 0,
        "both_datasets_restore_and_finish": all(case["success"] and case["evaluation_reads"] == 1 and case["repeat_run_did_not_repeat_experiment"] and case["model_requests"] == 0 for case in offline["numeric"].values()),
        "old_session_compatible_without_rewriting": offline["legacy_snapshot_restores"] and offline["legacy_snapshot_unchanged"],
        "live_general_numeric_general_shared_history": roles == ["general_chat", "project_qa", "project_qa", "candidate_generator_v1", "report_explainer_v1", "general_chat"],
        "live_native_tool_ids_match_results": bool(proposed_ids) and proposed_ids == result_ids,
        "live_file_citations_match_read_evidence": bool(project_answers and actual_reads) and set(project_answers[0]["evidence_refs"]) <= {item["evidence_ref"] for item in actual_reads} and actual_reads[0]["sha256"] == sha(OUT/"fixture_project/model.py"),
        "live_model_outputs_host_accepted": all(call["status"] == "accepted" for call in calls),
        "live_provider_requests_successful": all(call["status"] == "ok" for call in ledger["calls"]),
        "live_numeric_report_retained": bool(session.research_report()["scientific_success"]),
        "replay_cost_unchanged": before == session.resources(),
        "real_terminal_commands_saved": all("+"+cmd in history for cmd in ("/confirm", "/model-output list", "/model-output 2", "/report", "/exit")),
        "default_existing_entry_is_general": default_cli_ok,
        "no_new_zip": not list(OUT.rglob("*.zip")) and not list(ROOT.parent.glob("*.zip")),
    }
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, width=110, highlight=False)
    for call in calls:
        show_model_output(console, session, str(call["request_index"]))
    (OUT/"terminal_replay.txt").write_text(stream.getvalue(), encoding="utf-8")
    files = list((ROOT/"rut_science/science_bot/general").rglob("*.py"))
    files += [ROOT/p for p in ("rut_science/science_bot/api.py", "rut_science/science_bot/terminal.py",
        "rut_science/science_bot/session.py", "rut_science/science_bot/llm.py", "rut_science/science_bot/model_output.py",
        "docs/Science_Bot_G1_通用入口_zh.md", "scripts/verify_g1_delivery.py")]
    files += list((ROOT/"tests").glob("test_general*.py"))
    files += [ROOT.parent/"science-bot.cmd", ROOT.parent/"Start-ScienceBot.ps1"]
    for path in files:
        target = OUT/"source_snapshot"/path.relative_to(ROOT.parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    credential = load_api_config()["api_key"].encode("utf-8")
    checks["credential_absent_in_new_evidence"] = not any(credential in p.read_bytes() for p in OUT.rglob("*") if p.is_file())
    result = {"schema_version": "science_bot_g1_delivery_v1", "date": "2026-10-22", "passed": all(checks.values()),
              "checks": checks, "tests": {"run": int(count[1]) if count else None, "skipped": int(skipped[1]) if skipped else 0},
              "new_live_model_api_calls": len(ledger["calls"]),
              "usage": {key: ledger[key] for key in ("reported_prompt_tokens", "reported_completion_tokens", "accounted_tokens", "monetary_cost")},
              "live_session": str(session.folder), "numeric_report": session.research_report(),
              "weights_hash": session.numeric.policy_identity, "rl_retrained": False,
              "offline": offline, "entry_point": str(ROOT.parent/"science-bot.cmd"),
              "source_hashes": {p.relative_to(ROOT.parent).as_posix(): sha(p) for p in files},
              "limitations": ["Conservative host routing; ambiguous phrasing asks for clarification",
                 "Citations verify source identity and read coverage, not every semantic statement",
                 "G2 statistical experiment execution, G3 CViT training, editing, shell and web search remain unimplemented",
                 "Live proof uses one synthetic file fixture and one generated regression; it is not a broad generalization benchmark"]}
    write_json(OUT/"verification.json", result)
    if not result["passed"]:
        raise ValueError("G1 checks failed: "+", ".join(key for key, value in checks.items() if not value))
    print(json.dumps({"passed": True, "tests": result["tests"], "live_calls": len(ledger["calls"]),
                      "tokens": ledger["accounted_tokens"], "replay_unchanged": checks["replay_cost_unchanged"]}))


if __name__ == "__main__":
    main()
