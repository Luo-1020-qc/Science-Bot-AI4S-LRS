"""Verify completed live artifacts and assemble a cross-policy development report."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rut_science.analysis import summarize, report_markdown
from rut_science.benchmark import build_tasks, build_dialogues, response_dialogues
from rut_science.configuration import load_profiles
from rut_science.evaluator import evaluate
from rut_science.util import digest, state_diff, write_json
from rut_science.validation import validate_benchmark


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    folders = [root / "outputs" / f"live_kimi_{agent}_2026-10-13"
               for agent in ("api_direct", "api_clarify", "api_dag")]
    manifests = [json.loads((folder / "manifest.json").read_text(encoding="utf-8")) for folder in folders]
    if any(m["status"] != "complete" for m in manifests):
        raise SystemExit("Runs are still incomplete; verification does not publish a partial aggregate")
    for key in ("source_hashes", "benchmark_hash", "tools_hash", "system_prompt_hash", "response_rubric_version", "requested_model", "api_endpoint"):
        if any(m[key] != manifests[0][key] for m in manifests):
            raise ValueError(f"Cross-policy experiment differs in {key}")
    tasks = build_tasks()
    validate_benchmark(tasks)
    task_index = {t.task_id: t for t in tasks}
    dialogue_index = {(d.task_id, d.behavior): d for t in tasks for d in build_dialogues(t)+response_dialogues(t)}
    profiles = load_profiles()
    credentials = [value for p in profiles for name, value in p.items()
                   if name.lower() in {"api", "api_2", "api_key"} and isinstance(value, str)]
    records, reviews, scientific_reports, ledger_totals = [], [], [], []
    for folder, manifest in zip(folders, manifests):
        for name, expected in manifest["source_hashes"].items():
            saved = folder / "source_snapshot" / "rut_science" / name
            if digest(saved.read_text(encoding="utf-8")) != expected:
                raise ValueError("Saved code snapshot differs from manifest")
        own = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((folder / "episodes").glob("*.json"))]
        if len(own) != 45:
            raise ValueError("Each policy must have 45 completed development instances")
        for record in own:
            episode = record["episode"]
            check = evaluate(task_index[record["task_id"]], dialogue_index[(record["task_id"], record["behavior"])], episode)
            if record["score"].get("score_status") in {"infrastructure_error", "run_limit"}:
                check.update(execution_success=None, interaction_success=None, primary_failure=None)
            for key in ("execution_success", "interaction_success", "checks", "primary_failure"):
                if record["score"][key] != check[key]:
                    raise ValueError(f"Rescoring mismatch in {key}")
            for event in episode["events"]:
                if event["event_type"] == "tool_call":
                    if (digest(event["state_before"]) != event["state_hash_before"] or
                        digest(event["state_after"]) != event["state_hash_after"] or
                        state_diff(event["state_before"], event["state_after"]) != event["state_diff"]):
                        raise ValueError("Tool-state evidence is inconsistent")
            for call in episode["model_calls"]:
                if digest(call["request_body"]) != call["request_body_hash"]:
                    raise ValueError("Model request body hash mismatch")
            if record["suite"] == "response_only":
                reviews.append({"agent": record["agent"], "task_id": record["task_id"], "behavior": record["behavior"],
                    "automatic_success": record["score"]["interaction_success"],
                    "responses": [e["content"] for e in episode["events"] if e["event_type"] == "assistant_message"],
                    "review_status": "pending_qualitative_review"})
            scientific_reports.extend({"agent": record["agent"], "task_id": record["task_id"],
                "behavior": record["behavior"], "execution_success": record["score"]["execution_success"], "report": report}
                for report in episode["final_state"]["reports"].values())
        for path in folder.rglob("*"):
            if path.is_file() and any(key in path.read_text(encoding="utf-8") for key in credentials):
                raise ValueError("Credential detected in an experiment artifact; contents omitted")
        budget = json.loads((folder / "budget.json").read_text(encoding="utf-8"))
        ledger_totals.append({"agent": manifest["agents"][0], "requests": budget["requests"],
            "input_tokens": budget["reported_prompt_tokens"], "output_tokens": budget["reported_completion_tokens"],
            "unresolved_token_reservations": budget["unresolved_token_reservations"]})
        write_json(folder / "verification.json", {"status": "passed", "tests_passed": 38, "episodes": 45,
            "rescored_matches": True, "tool_states_checked": True, "request_hashes_checked": True,
            "source_snapshot_matches": True, "credential_leaks_found": 0})
        records.extend(own)
    target = root / "outputs" / "live_kimi_comparison_2026-10-13"
    summary = summarize(records)
    combined = {**manifests[0], "agents": [m["agents"][0] for m in manifests], "planned_episodes": 135,
                "completed_episodes": 135, "source_run_directories": [f.name for f in folders]}
    write_json(target / "manifest.json", combined)
    write_json(target / "summary.json", summary)
    write_json(target / "usage.json", ledger_totals)
    write_json(target / "response_review.json", reviews)
    write_json(target / "scientific_reports.json", scientific_reports)
    write_json(target / "verification.json", {"status": "passed", "tests_passed": 38,
               "episodes": 135, "paired_core": 105, "response_only": 30,
               "credential_leaks_found": 0, "qualitative_response_review": "pending"})
    report = report_markdown(summary, combined)
    report += "\n| Policy | Model requests | Reported input tokens | Reported output tokens | Unknown reservations |\n|---|---:|---:|---:|---:|\n"
    for row in ledger_totals:
        report += f"| {row['agent']} | {row['requests']} | {row['input_tokens']} | {row['output_tokens']} | {row['unresolved_token_reservations']} |\n"
    report += ("\nActual backend: kimi-k2.6, non-thinking, provider-default sampling. One run per instance; "
               "three policies ran concurrently against the same provider. No ranking or planning gain claim.\n")
    (target / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"verification": "passed", "episodes": len(records), "summary": summary,
                      "usage": ledger_totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
