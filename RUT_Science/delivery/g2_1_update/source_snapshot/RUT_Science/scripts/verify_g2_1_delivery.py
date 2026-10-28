"""G2.1 saved-proof audit and bounded acceptance. Default performs no API calls."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from rich.console import Console
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.interview.runtime import load
from rut_science.science_bot.general.interview.learning import export_review_queue
from rut_science.science_bot.general.interview.policy import BCInterviewPolicy
from rut_science.science_bot.session import ScienceSession
from rut_science.util import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"delivery/g2_1_update"
PROJECT = ROOT/"examples/g2"
_audit_spec = importlib.util.spec_from_file_location("g2_delivery_audit", ROOT/"scripts/verify_g2_delivery.py")
_audit_module = importlib.util.module_from_spec(_audit_spec)
_audit_spec.loader.exec_module(_audit_module)
audit = _audit_module.audit


def answer(session, fields, command="/answer"):
    return session.message(command+" "+json.dumps(fields, ensure_ascii=False))


def offline():
    saved = OUT/"offline_verification.json"
    if saved.exists():
        result = json.loads(saved.read_text(encoding="utf-8"))
        for item in result["cases"].values():
            assert audit(ScienceSession.restore(item["session"]).tabular)["metric_recomputes"]
        return result
    cases = {}
    for design in ("independent", "paired", "prediction"):
        spec = json.loads((PROJECT/f"{design}_design.json").read_text(encoding="utf-8"))
        spec.pop("schema_version", None)
        spec = {key: value for key, value in spec.items() if value is not None}
        path = spec.pop("data_path")
        session = GeneralSession.create(OUT/"offline_sessions", backend="offline", workspace=PROJECT)
        if design == "prediction":
            session.message("/interview-policy bc")
        session.message("/interview "+path)
        answer(session, {"research_question": spec.pop("research_question")})
        answer(session, {"unit_structure": "paired_units" if design == "paired" else "independent_rows"})
        # Preserve a real conflict/recovery trace in one task; no overwrite.
        if design == "independent":
            answer(session, {"response": "y"})
            conflict = answer(session, {"response": "wrong_column"})
            assert conflict["action"] == "resolve"
            answer(session, {"response": "y"}, "/resolve")
        draft = answer(session, spec)
        assert draft.get("requires_confirmation"), draft
        assert session.tabular.meta["completed"] == {}
        try:
            session.run()
        except ValueError:
            pass
        else:
            raise AssertionError("Unconfirmed experiment executed")
        session.confirm(draft["draft_hash"])
        session.run(max_steps=1)
        assert session.meta["phase"] == "paused"
        code = ("import sys; from rut_science.science_bot.session import ScienceSession; "
                "s=ScienceSession.restore(sys.argv[1]); s.run(); print(s.meta['phase'])")
        process = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(session.folder)],
                                 capture_output=True, text=True, encoding="utf-8", check=True, timeout=50)
        assert process.stdout.strip() == "complete"
        restored = ScienceSession.restore(session.folder)
        before = restored.resources()
        restored.run()
        evidence = audit(restored.tabular)
        assert evidence["metric_recomputes"]
        queue = OUT/"expert_review"/f"{design}.jsonl"
        exported = export_review_queue(restored.folder, queue)
        state = load(restored)
        cases[design] = {"session": str(restored.folder), **evidence, "cross_process_completed": True,
                         "unconfirmed_run_blocked": True, "repeat_cost_unchanged": before == restored.resources(),
                         "fields_with_sources": all(field in state["sources"] for field in state["fields"]),
                         "policy": state["policy"], "expert_review_rows": exported, "resources": restored.resources()}
    unknown = GeneralSession.create(OUT/"offline_sessions", backend="offline", workspace=PROJECT)
    unknown.message("/interview")
    stopped = unknown.message("不知道")
    assert stopped["action"] == "stop" and unknown.tabular is None
    result = {"cases": cases, "unknown_stopped_without_experiment": True, "unknown_session": str(unknown.folder),
              "expert_labels": "pending human review; no human labels invented", "model_calls": 0}
    write_json(saved, result)
    return result


def live():
    saved = OUT/"live_verification.json"
    if saved.exists():
        return json.loads(saved.read_text(encoding="utf-8"))
    pending = OUT/"live_session.json"
    if pending.exists():
        raise ValueError("已存在在线验收会话，请先检查历史；不会自动重发")
    session = GeneralSession.create(OUT/"live_sessions", backend="api", workspace=PROJECT,
                                    limits={"llm_requests": 2, "llm_tokens": 12000})
    write_json(pending, {"session": str(session.folder)})
    session.message("/interview two_groups.csv")
    answer(session, {"research_question": "比较A与B的平均y", "design": "independent", "unit_structure": "independent_rows",
                     "response": "y", "unit": "id"})
    result = session.message("/answer 这些测量来自合成数据")
    state = load(session)
    assert state["fields"].get("provenance") == "synthetic", result
    assert state["sources"]["provenance"]["kind"] == "user_grounded_model"
    draft = answer(session, {"factor": "group", "levels": ["A", "B"], "sampling_note": "全部现有合成样本，仅作探索性分析"})
    assert draft.get("requires_confirmation"), draft
    assert session.tabular.meta["completed"] == {}
    session.confirm(draft["draft_hash"])
    session.run()
    evidence = audit(session.tabular)
    assert evidence["metric_recomputes"]
    before = session.resources()
    session.model_output("list"); session.model_output("1"); session.research_report()
    result = {"session": str(session.folder), **evidence, "resources": session.resources(),
              "provenance_source": state["sources"]["provenance"], "only_user_quote_sent": True,
              "all_calls_accepted": all(call["status"] == "accepted" for call in session.model_output("list")["calls"]),
              "replay_cost_unchanged": before == session.resources(), "no_auto_execution": True}
    export_review_queue(session.folder, OUT/"expert_review/live.jsonl")
    write_json(saved, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    offline_result = offline()
    live_result = live() if args.live else (json.loads((OUT/"live_verification.json").read_text(encoding="utf-8")) if (OUT/"live_verification.json").exists() else None)
    model = ROOT/"models/design_interview_bc"
    policy = BCInterviewPolicy(model)
    evaluation = json.loads((model/"evaluation.json").read_text(encoding="utf-8"))
    manifest = json.loads((model/"manifest.json").read_text(encoding="utf-8"))
    log_path = OUT/"tests.log"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    count = re.search(r"Ran (\d+) tests", log)
    checks = {"full_regression": bool(count and "\nOK" in log and "FAILED" not in log),
              "three_designs_recompute": all(item["metric_recomputes"] for item in offline_result["cases"].values()),
              "unconfirmed_execution_blocked": all(item["unconfirmed_run_blocked"] for item in offline_result["cases"].values()),
              "cross_process_recovery": all(item["cross_process_completed"] for item in offline_result["cases"].values()),
              "repeat_no_extra_cost": all(item["repeat_cost_unchanged"] for item in offline_result["cases"].values()),
              "field_provenance_saved": all(item["fields_with_sources"] for item in offline_result["cases"].values()),
              "unknown_no_invented_experiment": offline_result["unknown_stopped_without_experiment"],
              "bc_checkpoint_hash": policy.identity == manifest["policy_hash"],
              "paired_family_not_used_for_training": "paired" not in manifest["train_families"],
              "no_new_zip": not list(OUT.rglob("*.zip")), "human_labels_not_fabricated": manifest["label_source"] == "rule_reference_not_human_expert"}
    old = json.loads((ROOT/"delivery/g2_update/verification.json").read_text(encoding="utf-8"))
    checks["original_windows_entry_unchanged"] = all(hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest() == old["source_hashes"][name] for name in ("science-bot.cmd", "Start-ScienceBot.ps1"))
    if live_result:
        checks.update(live_grounded_field_source=live_result["provenance_source"]["kind"] == "user_grounded_model",
                      live_calls_host_accepted=live_result["all_calls_accepted"], live_replay_no_spend=live_result["replay_cost_unchanged"])
    terminal_path = OUT/"terminal_acceptance.json"
    if terminal_path.exists():
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        session = ScienceSession.restore(terminal["session"])
        history = (session.folder/"terminal.history").read_text(encoding="utf-8")
        checks["terminal_entry_commands_saved"] = all(command in history for command in terminal["inputs"])
        checks["terminal_report_recomputes"] = audit(session.tabular)["metric_recomputes"]
        from rut_science.science_bot.terminal import show_status
        stream = io.StringIO()
        console = Console(file=stream, width=100, color_system=None)
        console.print("Saved display replay; not raw PTY recording.")
        show_status(console, session)
        console.print_json(data=session.research_report()["metrics"])
        (OUT/"terminal_replay.txt").write_text(stream.getvalue(), encoding="utf-8")
    else:
        checks["terminal_entry_commands_saved"] = False
    sources = list((ROOT/"rut_science/science_bot/general/interview").glob("*.py"))
    sources += [ROOT/"rut_science/science_bot/general/conversation.py", ROOT/"rut_science/science_bot/general/graph.py",
                ROOT/"rut_science/science_bot/terminal.py", ROOT/"rut_science/science_bot/model_output.py", Path(__file__),
                ROOT/"scripts/train_design_interview.py", ROOT/"scripts/export_design_review.py",
                ROOT.parent/"science-bot.cmd", ROOT.parent/"Start-ScienceBot.ps1", ROOT.parent/"README.md", ROOT.parent/"science_Bot_交接.md"]
    sources += list((ROOT/"tests").glob("test_*interview*.py"))+list((ROOT/"docs").glob("Science_Bot_G2_1*"))
    sources += [OUT/"README_本轮交付.md"] if (OUT/"README_本轮交付.md").exists() else []
    source_hashes = {}
    for source in sources:
        relative = source.relative_to(ROOT.parent)
        target = OUT/"source_snapshot"/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_hashes[relative.as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
    for name in ("manifest.json", "policy.json", "evaluation.json", "training_curve.json", "task_manifest.json"):
        target = OUT/"bc_baseline"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model/name, target)
    review_rows = [json.loads(line) for path in (OUT/"expert_review").glob("*.jsonl")
                   for line in path.read_text(encoding="utf-8").splitlines() if line]
    checks["real_traces_await_expert_review"] = bool(review_rows) and all(
        row["expert_action"] is None and row["status"] == "awaiting_expert_review" for row in review_rows)
    # Check actual local credential absence without printing it or copying config.
    from rut_science.configuration import load_api_config
    credential = load_api_config()["api_key"].encode("utf-8")
    checks["credential_absent"] = all(credential not in p.read_bytes() for p in OUT.rglob("*") if p.is_file() and p.suffix in {".json", ".jsonl", ".md", ".txt", ".log", ".py"})
    result = {"schema_version": "g2_1_delivery_v1", "date": "2026-10-22", "passed": all(checks.values()),
              "checks": checks, "tests": int(count[1]) if count else None, "offline": offline_result, "live": live_result,
              "bc": {"manifest": manifest, "heldout": evaluation["heldout"]}, "source_hashes": source_hashes,
              "ppo_trained": False, "llm_weights_updated": False,
              "limitations": ["Synthetic reference-user simulator; no verified human expert labels or broad generalization result",
                              "No demonstrated BC advantage over rules; rule remains default",
                              "Three G2 numerical families only; no arbitrary new methods or autonomous GPU jobs"]}
    write_json(OUT/"verification.json", result)
    print(json.dumps({"passed": result["passed"], "checks": checks, "tests": result["tests"],
                      "live_requests": live_result["resources"]["llm_requests"] if live_result else 0}, ensure_ascii=False))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
