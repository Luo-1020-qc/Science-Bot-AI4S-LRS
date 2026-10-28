"""PowerShell-friendly structured planning commands."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import uuid
from dataclasses import replace

from .configuration import DEFAULT_API_CONFIG
from .plan_spec import PlanSpec
from .planning_agent import PlanningSession, read_checkpoint, session_lock
from .planning_evaluation import environment_for, verify_artifacts
from .research_spec import ResearchSpec
from .util import canonical

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Structured scientific planning Agent with LangGraph and local checkpoints")
    parser.add_argument("command", choices=["run", "resume", "status", "revise", "validate", "verify"])
    parser.add_argument("--workflow", choices=["darcy", "synthetic"], default="darcy")
    parser.add_argument("--backend", choices=["offline", "api", "file"], default="offline")
    parser.add_argument("--data", type=Path, default=ROOT / "data/darcy_cpu_v1")
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--reason", default="Operator revision of unexecuted nodes")
    parser.add_argument("--task", default="science_001", choices=[f"science_{i:03d}" for i in range(1, 6)])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--api-config", type=Path, default=DEFAULT_API_CONFIG)
    parser.add_argument("--profile", type=int, default=0)
    parser.add_argument("--credential-field", default="API")
    parser.add_argument("--max-seconds", type=float, default=180)
    parser.add_argument("--max-tool-calls", type=int, default=12)
    parser.add_argument("--max-plan-attempts", type=int, default=3)
    parser.add_argument("--max-requests", type=int, default=3)
    parser.add_argument("--max-run-tokens", type=int, default=80_000)
    parser.add_argument("--stop-after", type=int, help="Pause after this many successful nodes in this invocation")
    parser.add_argument("--validation-select", action="store_true", help="Authorize two candidate fits and validation-only selection")
    parser.add_argument("--recover", action="store_true", help="Enable bounded atomic transient retries")
    parser.add_argument("--fault-tool", choices=["inspect_dataset", "validate_dataset", "split_dataset", "train_model", "select_model", "evaluate_model", "write_report"])
    parser.add_argument("--fault-count", type=int, default=0, help="Explicit before-invocation fault fixture; not a real service outage")
    args = parser.parse_args(argv)
    if args.output is None and args.command in {"resume", "status", "revise", "verify"}:
        parser.error("--output must identify an existing session")
    if args.output is None:
        stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
        args.output = ROOT / "outputs" / f"plan_{args.backend}_{stamp}_{uuid.uuid4().hex[:6]}"
    output = args.output.resolve()
    try:
        if args.command == "status":
            checkpoint = read_checkpoint(output)
            public = json.loads((output / "status.json").read_text(encoding="utf-8"))
            if public["phase"] != checkpoint["phase"]:
                raise ValueError("Status and checkpoint phase differ")
            print(json.dumps(public, ensure_ascii=False, indent=2))
            return 0
        if args.command == "verify":
            with session_lock(output):
                print(canonical(verify_artifacts(output)))
            return 0
        if args.command in {"resume", "revise"}:
            if not (output / "manifest.json").exists():
                raise ValueError("Select an existing planning session")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            env = environment_for(manifest)
            with session_lock(output):
                session = PlanningSession.restore(output, env, progress=lambda line: print(line, flush=True))
                if args.command == "revise":
                    if args.plan_file is None:
                        raise ValueError("revise requires --plan-file")
                    plan = PlanSpec.from_dict(json.loads(args.plan_file.read_text(encoding="utf-8-sig")))
                    session.revise(plan, args.reason)
                    print(f"Saved revised plan v{plan.version}; run resume to execute")
                    return 0
                status = session.run(args.stop_after)
        else:
            if args.workflow == "darcy":
                from .darcy_workflow import DarcyEnvironment
                env = DarcyEnvironment(args.data)
                spec = ResearchSpec(**json.loads((args.spec or args.data / "research_spec.json").read_text(encoding="utf-8-sig")))
                if args.validation_select:
                    spec = replace(spec, model="validation_select", max_train_calls=2)
                if spec.model == "validation_select":
                    from .adaptive_workflow import SelectionDarcyEnvironment
                    env = SelectionDarcyEnvironment(args.data)
                task_id = "darcy_cpu_001"
            else:
                from .benchmark import build_tasks
                from .environment import ScientificMLEnvironment
                env = ScientificMLEnvironment()
                task = next(t for t in build_tasks() if t.task_id == args.task)
                spec = ResearchSpec.from_task(task, env.snapshot())
                if args.spec is not None:
                    supplied = ResearchSpec(**json.loads(args.spec.read_text(encoding="utf-8-sig")))
                    if supplied != spec:
                        raise ValueError("Synthetic benchmark spec must match its selected public task")
                task_id = task.task_id
            if args.command == "validate":
                if args.plan_file is None:
                    raise ValueError("validate requires --plan-file")
                plan = PlanSpec.from_dict(json.loads(args.plan_file.read_text(encoding="utf-8-sig")))
                print(canonical(plan.validate(spec, env.available_tools(), args.max_tool_calls)))
                return 0
            with session_lock(output):
                session = PlanningSession.create(output, env, spec, workflow=args.workflow,
                    data=args.data if args.workflow == "darcy" else None, task_id=task_id, backend=args.backend,
                    plan_file=args.plan_file, model=args.model, api_config=args.api_config, profile=args.profile,
                    credential_field=args.credential_field, max_seconds=args.max_seconds, max_tool_calls=args.max_tool_calls,
                    max_plan_attempts=args.max_plan_attempts, max_requests=args.max_requests, max_tokens=args.max_run_tokens,
                    recovery_policy={"enabled": args.recover, "max_total_retries": 2, "max_retries_per_node": 1},
                    fault_injection={"tool": args.fault_tool, "count": args.fault_count, "error_code": "transient_unavailable"},
                    progress=lambda line: print(line, flush=True))
                status = session.run(args.stop_after)
        print(f"Session: {output}")
        print(f"Phase: {status['phase']}; nodes: {status['nodes']}; tool calls: {status['tool_calls']}")
        return 0 if status["phase"] == "paused" or status["execution_success"] is True else 2
    except (ValueError, OSError, ImportError) as exc:
        parser.error(str(exc))
