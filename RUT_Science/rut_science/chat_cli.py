"""PowerShell research conversation entry point."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import uuid

from .configuration import DEFAULT_API_CONFIG
from .planning_agent import session_lock
from .research_chat import ResearchChat

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Interactive scientific specification, confirmation, planning and recovery")
    parser.add_argument("--backend", choices=["api", "offline"], default="api")
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--api-config", type=Path, default=DEFAULT_API_CONFIG)
    parser.add_argument("--data", type=Path, default=ROOT/"data/darcy_cpu_v1")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--max-requests", type=int, default=12)
    parser.add_argument("--max-run-tokens", type=int, default=120_000)
    parser.add_argument("--max-seconds", type=float, default=180)
    parser.add_argument("--stop-after", type=int)
    parser.add_argument("--script", type=Path, help="JSON array of operator inputs; records scripted_operator, not a human evaluation")
    parser.add_argument("--prepare-only", action="store_true", help="Save confirmation without running scientific tools")
    parser.add_argument("--fault-tool", choices=["inspect_dataset", "validate_dataset", "split_dataset", "train_model", "select_model", "evaluate_model", "write_report"])
    parser.add_argument("--fault-count", type=int, default=0)
    args = parser.parse_args(argv)
    if args.resume and args.output is None:
        parser.error("--resume requires --output")
    output = (args.output or ROOT/"outputs"/("chat_"+datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:6])).resolve()
    try:
        with session_lock(output):
            chat = ResearchChat.restore(output) if args.resume else ResearchChat.create(output, data=args.data,
                backend=args.backend, model=args.model, api_config=args.api_config, recover=args.recover,
                max_requests=args.max_requests, max_tokens=args.max_run_tokens, max_seconds=args.max_seconds,
                fault_tool=args.fault_tool, fault_count=args.fault_count)
            print(f"Session: {output}\n描述数据、预测目标和约束；/spec 查看，/confirm 确认，/resume 继续执行，/exit 退出。", flush=True)
            if args.resume:
                chat.present()
            if args.script:
                inputs = json.loads(args.script.read_text(encoding="utf-8-sig"))
                if type(inputs) is not list or any(type(line) is not str for line in inputs):
                    raise ValueError("--script must contain a JSON array of strings")
                for line in inputs:
                    print("[scripted_operator] " + line, flush=True)
                    if line.strip() == "/exit":
                        break
                    chat.submit(line, actor="scripted_operator", execute=not args.prepare_only, stop_after=args.stop_after)
            else:
                while True:
                    try:
                        line = input("research> ")
                    except EOFError:
                        break
                    if line.strip() == "/exit":
                        break
                    try:
                        chat.submit(line, execute=not args.prepare_only, stop_after=args.stop_after)
                    except ValueError as exc:
                        print(str(exc), flush=True)
            latest = chat.state["executions"][-1] if chat.state["executions"] else None
            if latest is None and args.script and not args.prepare_only:
                print("Script ended without an authorized scientific execution; inspect conversation.json.", flush=True)
                return 2
            return 0 if latest is None or latest["phase"] == "paused" or latest.get("execution_success") is True else 2
    except (ValueError, OSError, ImportError) as exc:
        parser.error(str(exc))
    except KeyboardInterrupt:
        print(f"\n已保留会话：{output}")
        return 130
