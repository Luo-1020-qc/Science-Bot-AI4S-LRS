import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import platform
import sys
from datetime import datetime, timezone

from . import __version__
from .agents import JSONHTTPAgent, RuleAgent
from .analysis import report_markdown, summarize
from .benchmark import build_dialogues, build_tasks, response_dialogues
from .contracts import SYSTEM_PROMPT
from .environment import ScientificMLEnvironment, make_initial_state
from .evaluator import evaluate
from .runtime import run_episode
from .util import canonical, digest, write_json
from .validation import validate_benchmark
from .configuration import DEFAULT_API_CONFIG, load_api_config
from .budget import RunBudget
from .clarification import RUBRIC_VERSION
from .research_spec import ResearchSpec


def main(argv: list[str] | None = None) -> int:
    selected = sys.argv[1:] if argv is None else argv
    if selected and selected[0] == "science":
        from .science_bot.terminal import main as science_main
        return science_main(selected[1:])
    if selected and selected[0] == "serve":
        from .science_bot.api import main as serve_main
        return serve_main(selected[1:])
    if selected and selected[0] == "chat":
        from .chat_cli import main as chat_main
        return chat_main(selected[1:])
    if selected and selected[0] == "plan":
        from .planning_cli import main as planning_main
        return planning_main(selected[1:])
    if selected and selected[0] == "darcy":
        from .darcy_workflow import main as darcy_main
        return darcy_main(selected[1:])
    parser = argparse.ArgumentParser(description="RUT-inspired scientific evaluation (development MVP)")
    parser.add_argument("command", choices=["validate", "run"])
    parser.add_argument("--agents", nargs="+", default=["rule_latest", "rule_context", "rule_dag"],
                        choices=["rule_latest", "rule_context", "rule_dag", "api_direct", "api_clarify", "api_dag"])
    parser.add_argument("--seeds", nargs="+", type=int, default=[0])
    parser.add_argument("--task", choices=[f"science_{i:03d}" for i in range(1, 6)])
    parser.add_argument("--output", type=Path, default=Path("outputs/demo"))
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--max-seconds", type=float, default=60)
    parser.add_argument("--model", help="Required for API runs; use a model available to your account")
    parser.add_argument("--api-config", type=Path, default=DEFAULT_API_CONFIG,
                        help="Defaults to project API_key_Agent.json, independent of working directory")
    parser.add_argument("--profile", type=int, default=0)
    parser.add_argument("--credential-field", default="API")
    parser.add_argument("--max-requests", type=int, default=1200)
    parser.add_argument("--max-run-tokens", type=int, default=3_000_000)
    parser.add_argument("--max-context-bytes", type=int, default=120_000)
    parser.add_argument("--max-service-errors", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.max_steps < 1 or not math.isfinite(args.max_seconds) or args.max_seconds <= 0:
        parser.error("Step and time limits must be positive")
    if len(set(args.agents)) != len(args.agents) or len(set(args.seeds)) != len(args.seeds):
        parser.error("Agents and seeds must be unique")
    api_run = any(a.startswith("api_") for a in args.agents)
    args.endpoint = None
    api_key = None
    if args.command == "run" and api_run:
        if args.api_config is not None:
            try:
                configuration = load_api_config(args.api_config, args.profile, args.credential_field)
            except (ValueError, OSError) as exc:
                parser.error(str(exc))
            api_key = configuration["api_key"]
            args.endpoint = configuration["endpoint"]
            args.model = args.model or configuration["model"]
        if not args.model:
            parser.error("--model is required for API runs")
        # Validate connectivity configuration/key presence without issuing a model call.
        JSONHTTPAgent(args.endpoint, args.model, api_key=api_key)
        if min(args.max_requests, args.max_run_tokens, args.max_context_bytes, args.max_service_errors) < 1:
            parser.error("Whole-run limits must be positive")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()) and not args.resume:
        parser.error("Output directory must be new or empty; select a fresh --output to preserve existing runs")
    if args.resume and (args.command != "run" or not (output / "manifest.json").exists()):
        parser.error("--resume requires an existing run manifest")
    tasks = [t for t in build_tasks() if args.task is None or t.task_id == args.task]
    qa = validate_benchmark(tasks)
    output.mkdir(parents=True, exist_ok=True)
    task_dicts = [asdict(t) | {"optimal_action_budget": t.optimal_action_budget} for t in tasks]
    dialogues = [asdict(d) for t in tasks for d in build_dialogues(t) + response_dialogues(t)]
    def write_benchmark():
        write_json(output / "validation.json", qa)
        write_json(output / "benchmark" / "tasks.json", task_dicts)
        write_json(output / "benchmark" / "dialogues.json", dialogues)
        write_json(output / "benchmark" / "initial_state.json", make_initial_state())
        write_json(output / "benchmark" / "research_specs.json",
                   {t.task_id: ResearchSpec.from_task(t, make_initial_state()).to_dict() for t in tasks})
    if args.command == "validate":
        write_benchmark()
        print(f"Validated {len(tasks)} root tasks / {len(tasks)*7} paired dialogues: {output}")
        return 0
    sources = {p.name: digest(p.read_text(encoding="utf-8")) for p in sorted(Path(__file__).parent.glob("*.py"))}
    manifest = {
        "version": __version__, "python": sys.version, "platform": platform.platform(),
        "task_count": len(tasks), "seeds": args.seeds, "agents": args.agents, "split": "development",
        "max_steps": args.max_steps, "max_seconds": args.max_seconds,
        "system_prompt_hash": digest(SYSTEM_PROMPT), "tools_hash": digest(ScientificMLEnvironment().available_tools()),
        "benchmark_hash": digest({"tasks": task_dicts, "dialogues": dialogues}), "source_hashes": sources,
        "api_endpoint": args.endpoint if api_run else None, "requested_model": args.model if api_run else None,
        "api_temperature": 0 if api_run else None, "provider_seed_supported": False,
        "response_rubric_version": RUBRIC_VERSION,
        "run_limits": {"max_requests": args.max_requests, "max_tokens": args.max_run_tokens,
                       "max_context_bytes": args.max_context_bytes, "max_service_errors": args.max_service_errors},
        "api_profile": args.profile if api_run else None,
        "credential_field": args.credential_field if api_run else None,
        "api_config_file": args.api_config.name if api_run else None,
        "protocol": "JSON actions, sequential user turns; sealed single test; no official RUT reproduction claim",
    }
    if api_run and "api.moonshot." in args.endpoint:
        manifest["api_temperature"] = "provider_default"
    if args.resume:
        old = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        for key, value in manifest.items():
            if old.get(key) != value:
                parser.error(f"Resume configuration differs in {key}; use a new output directory")
        manifest = old
    else:
        manifest["created_utc"] = datetime.now(timezone.utc).isoformat()
        write_benchmark()
    budget = RunBudget(args.max_requests, args.max_run_tokens, args.max_context_bytes,
                       path=output / "budget.json") if api_run else None
    if budget is not None and args.resume and budget.path.exists():
        budget.calls = json.loads(budget.path.read_text(encoding="utf-8"))["calls"]
    manifest.update(status="running", updated_utc=datetime.now(timezone.utc).isoformat())
    write_json(output / "manifest.json", manifest)
    if budget is not None:
        budget.persist()
    records, halted = [], False
    schedule = [(agent_name, task, dialogue, seed) for agent_name in args.agents for task in tasks
                for dialogue in build_dialogues(task)+response_dialogues(task) for seed in args.seeds]
    manifest["planned_episodes"] = len(schedule)
    write_json(output / "manifest.json", manifest)
    try:
        for agent_name, task, dialogue, seed in schedule:
                    run_id = f"{agent_name}__{task.task_id}__{dialogue.behavior}__seed_{seed}"
                    episode_path = output / "episodes" / f"{run_id}.json"
                    if args.resume and episode_path.exists():
                        records.append(json.loads(episode_path.read_text(encoding="utf-8")))
                        continue
                    if halted:
                        continue
                    agent = (RuleAgent(agent_name.removeprefix("rule_")) if agent_name.startswith("rule_") else
                             JSONHTTPAgent(args.endpoint, args.model, policy=agent_name.removeprefix("api_"),
                                           api_key=api_key, budget=budget, episode_id=run_id))
                    spec = ResearchSpec.from_task(task, make_initial_state()) if dialogue.mode == "execute" else None
                    episode = run_episode(agent, ScientificMLEnvironment(), dialogue, seed, args.max_steps, args.max_seconds,
                                          research_spec=spec)
                    score = evaluate(task, dialogue, episode)
                    score["score_status"] = "scored"
                    if episode["termination"] in {"service_error", "adapter_error"}:
                        score.update(execution_success=None, interaction_success=None, primary_failure=None,
                                     score_status="infrastructure_error")
                    elif episode["termination"] == "run_limit":
                        score.update(execution_success=None, interaction_success=None, primary_failure=None,
                                     score_status="run_limit")
                        halted = True
                    record = {"task_id": task.task_id, "agent": agent_name, "behavior": dialogue.behavior,
                              "suite": dialogue.suite, "seed": seed, "score": score, "episode": episode}
                    write_json(episode_path, record)
                    events_path = output / "trajectories" / f"{run_id}.jsonl"
                    events_path.parent.mkdir(exist_ok=True)
                    events_path.write_text("\n".join(canonical(e) for e in episode["events"]) + "\n", encoding="utf-8")
                    records.append(record)
                    manifest.update(completed_episodes=len(records), updated_utc=datetime.now(timezone.utc).isoformat())
                    write_json(output / "manifest.json", manifest)
                    if budget is not None:
                        print(f"{len(records)}/{len(schedule)} {run_id}: {episode['termination']}; requests={len(budget.calls)}", flush=True)
                        failures = sum(r["episode"]["termination"] in {"service_error", "adapter_error"} for r in records)
                        if failures >= args.max_service_errors:
                            halted = True
    except KeyboardInterrupt:
        halted = True
        manifest["interrupted"] = True
    results = summarize(records)
    manifest.update(status="complete" if len(records) == len(schedule) and not halted else "partial",
                    completed_episodes=len(records), pending_episodes=len(schedule)-len(records),
                    updated_utc=datetime.now(timezone.utc).isoformat())
    write_json(output / "manifest.json", manifest)
    write_json(output / "summary.json", results)
    report = report_markdown(results, manifest)
    report += f"\nRun status: {manifest['status']}; completed/planned episodes: {len(records)}/{len(schedule)}.\n"
    if budget is not None:
        ledger = budget.snapshot()
        report += (f"\nWhole-run requests: {ledger['requests']}; reported input/output tokens: "
                   f"{ledger['reported_prompt_tokens']}/{ledger['reported_completion_tokens']}; "
                   f"unresolved token reservations: {ledger['unresolved_token_reservations']}. "
                   "Monetary cost is not configured; token limits use conservative admission estimates.\n")
    (output / "report.md").write_text(report, encoding="utf-8")
    for name, data in results.items():
        sr = data["overall_execution_sr"]
        displayed = f"{sr:.1%}" if sr is not None else "N/A"
        print(f"{name}: execution SR={displayed}; infrastructure errors={data['infrastructure_errors']}")
    print(f"Saved {len(records)} episodes and report: {output}")
    return 0 if manifest["status"] == "complete" else 2
