"""science Bot terminal: quiet workspace, live events and persistent sessions."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import unicodedata
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from .contracts import BudgetedResearchSpec
from .session import ScienceSession, ROOT, DEFAULT_POLICY
from .model_output import ROLE_LABELS, STATUS_LABELS

COMMANDS = ["/help", "/workspace", "/files", "/read", "/confirm", "/status", "/experiments", "/pause", "/resume", "/cancel", "/report", "/model-output", "/events", "/clear", "/exit"]


def plain_model_text(value):
    """Escape terminal controls and directional overrides; never parse markup."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return "".join(f"\\u{ord(char):04x}" if char != "\n" and unicodedata.category(char) in {"Cc", "Cf", "Cs"}
                   else char for char in text)


def show_model_output(console, session, selector="latest"):
    saved = session.model_output(selector)
    if selector == "list":
        table = Table("调用", "角色", "模型", "状态", border_style="cyan")
        for item in saved["calls"]:
            table.add_row(Text(str(item["request_index"])),
                          Text(ROLE_LABELS.get(item["role"], plain_model_text(item["role"]))),
                          Text(plain_model_text(item["model"])),
                          Text(STATUS_LABELS.get(item["status"], "未知状态")))
        if saved["calls"]:
            console.print(table)
        else:
            console.print(Text("当前会话没有已保存的模型输出。"))
        return saved
    if saved is None:
        message = ("离线模式未调用大语言模型，当前会话没有模型输出。" if session.meta["backend"] == "offline"
                   else "当前会话尚无已保存的模型输出。")
        console.print(Text(message))
        return None
    labels = {"schema_version": "输出格式", "fields": "提取字段", "missing_required": "缺少信息",
              "conflicts": "冲突", "questions": "澄清问题", "candidates": "候选方案",
              "unresolved": "未解决项", "observation_ref": "观察引用", "action_id": "选择的行动",
              "evidence_refs": "证据引用", "reason": "模型选择理由", "summary": "摘要",
              "findings": "发现与证据", "limitations": "限制", "artifact_refs": "产物引用"}
    body = Text()
    body.append(STATUS_LABELS.get(saved["status"], "未知校验状态")+"\n", style="bold")
    body.append("模型内容与宿主科研报告分开记录；科研验收结果见 /report。\n\n", style="dim")
    response = saved["response"]
    if response is None:
        body.append("本次调用没有可展示的解析结果。\n")
    elif isinstance(response, dict):
        for key, value in response.items():
            body.append(labels.get(key, plain_model_text(key))+"\n", style="bold cyan")
            body.append(plain_model_text(value)+"\n\n")
    else:
        body.append(plain_model_text(response)+"\n")
    if saved["error_type"]:
        body.append("错误类型："+plain_model_text(saved["error_type"])+"\n", style="yellow")
    role = ROLE_LABELS.get(saved["role"], plain_model_text(saved["role"]))
    body.append("模型："+plain_model_text(saved["model"])+"\n", style="dim")
    body.append("保存位置："+plain_model_text(saved["output_ref"]), style="dim")
    console.print(Panel(body, title=Text(f"模型输出 #{saved['request_index']:04d} · {role}"), border_style="cyan"))
    return saved


def show_event(console, session, event):
    p = event["payload"]
    if event["kind"] == "model_output":
        try:
            show_model_output(console, session, str(p["request_index"]))
        except (ValueError, OSError) as exc:
            # Display failures must not change the underlying scientific run.
            console.print(Text(f"模型输出暂时无法显示：{type(exc).__name__}；可用 /model-output 重试。", style="yellow"))
    elif event["kind"] == "model_validation":
        console.print(Text(f"  模型输出 #{p['request_index']:04d}："+
                           STATUS_LABELS.get(p["status"], "未知状态"), style="cyan"))
    elif event["kind"] == "model_call_failed":
        console.print(Text("模型请求未完成："+plain_model_text(p["error_type"]), style="yellow"))
    elif event["kind"] == "selected":
        console.print(Text(f"  › {p['action']} · planner={session.meta['planner']} · "
                           f"{p['budget']['compute_units_remaining']:g} CU available", style="bright_magenta"))
    elif event["kind"] == "tool_result":
        completed = [e for e in p["observation"]["experiments"] if e["observed"]]
        best = min([e["validation_mean"] for e in completed], default=None)
        console.print(Text(f"    ✓ result recorded · best validation {best:.6f}" if best is not None else "    result recorded"))
    elif event["kind"] == "explanation_failed":
        console.print(Text("报告解释未采用："+plain_model_text(p["error_type"])+"；宿主科研报告仍可用 /report 查看。", style="yellow"))
    elif event["kind"] == "error":
        console.print(Text(f"  Paused: {p['type']} · {p['detail']}", style="yellow"))


def banner(console, session):
    title = Text("science ", style="bold bright_cyan") + Text("Bot", style="bold bright_magenta")
    console.print()
    console.print(Panel(title+Text("\nresearch, with evidence.", style="dim"), border_style="bright_black", padding=(1, 3)))
    console.print(f"  [cyan]{session.meta['backend']}[/cyan] · {session.meta['planner']} · {session.meta['model']} · session {session.meta['id'][:8]}")
    console.print("  [dim]/help commands   /model-output model replies   /pause safe pause   Ctrl+D save & exit[/dim]\n")


def show_status(console, session):
    status = session.status()
    spec, obs = status["spec"], status["observation"]
    table = Table.grid(padding=(0, 2))
    for label, value in (("Phase", status["phase"]), ("Dataset", spec["dataset"]),
                         ("Project root", status["workspace"]["root"] if status["workspace"] else "built-in research session"),
                         ("Metric", "mean_relative_l2"), ("Engineering threshold", str(spec["quality_threshold"])),
                         ("Search CU", f"{obs['budget']['compute_units_remaining']:g} / {spec['compute_units']} remaining"),
                         ("Finalization reserve", "2 CU + 2 tool operations + 1 model request"),
                         ("Policy", status["policy_hash"][:16]), ("Draft hash", status["draft_hash"]),
                         ("Confirmed", str(status["confirmed"]))):
        table.add_row(Text(label, style="dim"), Text(value, overflow="fold"))
    console.print(Panel(table, title="research workspace", border_style="cyan"))
    console.print("[dim]Defaults: full registered mean/ridge catalog; threshold from pilot configuration. Review before /confirm.[/dim]")


def show_experiments(console, session):
    table = Table("Experiment", "State", "Validation L2", "Attempts", border_style="bright_black")
    for e in session.env.observe()["experiments"]:
        if e["status"] != "untried":
            table.add_row(e["candidate_ref"], e["status"], f"{e['validation_mean']:.6f}" if e["observed"] else "—", str(e["attempts"]))
    console.print(table)


def open_session(args):
    if args.resume:
        return ScienceSession.restore(args.resume, workspace=args.workspace)
    return ScienceSession.create(args.sessions, backend=args.backend, planner=args.planner,
        checkpoint=args.checkpoint, model=args.model, workspace=args.workspace,
        spec=BudgetedResearchSpec(dataset=args.dataset, split="demo", compute_units=args.budget))


def project_command(session, command, argument=""):
    """Local project reads do not consume CU or submit source to the model API."""
    if session.workspace is None:
        raise ValueError("Open a project using --workspace <directory>")
    if command == "/workspace":
        return session.workspace.describe()
    if command == "/files":
        pattern = argument.strip().strip('"\'') or "*"
        return session.workspace.files(pattern)
    if command == "/read":
        return session.workspace.read_text(argument)
    raise ValueError("Unknown workspace command")


async def interactive(args):
    console = Console(highlight=False)
    session = open_session(args)
    banner(console, session)
    show_status(console, session)
    console.print(f"[dim]Session saved at {session.folder}[/dim]")
    task = None

    def on_event(event):
        show_event(console, session, event)
    session.event_callback = on_event
    prompt = PromptSession(history=FileHistory(str(session.folder/"terminal.history")),
                           completer=WordCompleter(COMMANDS), complete_while_typing=False)

    def toolbar():
        return HTML(f" science Bot  |  {session.meta['phase']}  |  {session.env.state['cu']:g}/{session.spec.compute_units} search CU  |  /help ")

    async def work():
        try:
            await asyncio.to_thread(session.run)
            if session.env.state["report"]:
                report = session.env.state["report"]
                console.print(Panel(Text(f"Scientific success: {report['scientific_success']}\nSealed relative L2: {report['sealed_error']}\nReport: {session.folder / 'report.md'}"),
                                    title="research complete", border_style="green"))
            else:
                console.print(f"[yellow]Session {session.meta['phase']}. /resume to continue.[/yellow]")
        except Exception as exc:
            console.print(Text(f"Run paused: {type(exc).__name__}: {exc}", style="yellow"))

    with patch_stdout(raw=True):
        while True:
            try:
                line = (await prompt.prompt_async(HTML("<ansicyan><b>you › </b></ansicyan>"), bottom_toolbar=toolbar)).strip()
            except KeyboardInterrupt:
                session.pause(); console.print("[yellow]Pause requested; current job will be reconciled.[/yellow]"); continue
            except EOFError:
                line = "/exit"
            if not line:
                continue
            running = task is not None and not task.done()
            command, _, argument = line.partition(" ")
            try:
                if command == "/exit":
                    if running:
                        session.pause(); await task
                    session.save(); break
                elif command == "/help":
                    console.print(Panel("\n".join(COMMANDS)+"\n\n/workspace: current project and state directory\n/files [glob]: list project files\n/read <path>: display UTF-8 text locally (not sent to the model)\n/model-output [list|number]: replay saved model output locally; no new calls\n\nDescribe a research task to revise the draft.\nOffline parser: generated / Darcy; 预算10; 门槛0.20.\nExecution starts after /confirm. Use --resume <session-folder> after restarting.", title="commands"))
                elif command == "/status":
                    show_status(console, session)
                elif command in {"/workspace", "/files", "/read"}:
                    result = project_command(session, command, argument)
                    if command == "/read":
                        console.print(Panel(Text(result["text"]), title=Text(result["path"]), border_style="cyan"))
                        console.print(Text(f"{result['bytes']} bytes · sha256 {result['sha256'][:16]} · local read", style="dim"))
                    elif command == "/files":
                        table = Table("Project file", "Bytes", border_style="bright_black")
                        for item in result["files"]:
                            table.add_row(Text(item["path"]), str(item["bytes"]))
                        console.print(table)
                        if result["truncated"]:
                            console.print("Listing truncated. Use a narrower glob.")
                    else:
                        console.print_json(data=result)
                elif command == "/experiments":
                    show_experiments(console, session)
                elif command == "/pause":
                    session.pause(); console.print("Pause requested.")
                elif command == "/cancel":
                    session.cancel()
                    if not running:
                        session.env.state["phase"] = "cancelled"; session.meta["phase"] = "cancelled"; session.save()
                    console.print("Cancellation requested.")
                elif command == "/clear":
                    console.clear(); banner(console, session)
                elif command == "/events":
                    console.print_json(data=session.events()[-8:])
                elif command == "/report":
                    console.print_json(data=session.env.state["report"] or {"status": "not finalized"})
                elif command == "/model-output":
                    show_model_output(console, session, argument.strip() or "latest")
                elif command in {"/confirm", "/resume"}:
                    if running:
                        console.print("A run is already active."); continue
                    if command == "/confirm":
                        session.confirm(argument or session.confirmation)
                    task = asyncio.create_task(work())
                elif line.startswith("/"):
                    console.print("Unknown command. /help")
                elif running:
                    console.print("[yellow]Use /pause before submitting another research message.[/yellow]")
                else:
                    with console.status("Understanding research request…", spinner="dots"):
                        response = await asyncio.to_thread(session.message, line)
                    if "questions" in response:
                        console.print(Text("\n".join(response["questions"])))
                    show_status(console, session)
            except Exception as exc:
                console.print(Text(f"{type(exc).__name__}: {exc}", style="yellow"))
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="science-bot", description="science Bot · auditable scientific terminal")
    parser.add_argument("--backend", choices=["api", "offline"], default="api")
    parser.add_argument("--planner", choices=["rl", "bc", "llm", "adaptive", "cheap", "dense", "search", "random"], default="rl")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--dataset", choices=["generated", "darcy"], default="generated")
    parser.add_argument("--budget", type=int, default=10)
    parser.add_argument("--workspace", type=Path, help="Open an existing project; default state: <project>/.sciencebot")
    parser.add_argument("--sessions", type=Path, help="Explicit session storage override (relative to launch directory)")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--demo", action="store_true", help="Explicitly confirm and execute one noninteractive demo")
    parser.add_argument("--preview", action="store_true", help="Render the terminal entry without creating a session")
    args = parser.parse_args(argv)
    try:
        if args.preview:
            console = Console(width=100)
            console.print(Panel("[bold cyan]science[/bold cyan] [bold magenta]Bot[/bold magenta]\n[dim]research, with evidence.[/dim]", padding=(2, 4), border_style="bright_black"))
            console.print("  describe → review → confirm → experiment → verify\n\n  /status   /experiments   /pause   /resume   /report   /model-output\n\n[cyan]you ›[/cyan]")
            return 0
        if args.demo:
            session = open_session(args)
            if not args.resume:
                session.message("Darcy pressure_field" if args.dataset == "darcy" else "generated regression_output")
            session.confirm(session.confirmation)
            session.event_callback = lambda event: print(json.dumps(event, ensure_ascii=False), flush=True)
            session.run()
            print(session.folder)
            return 0 if session.env.state["report"] else 2
        return asyncio.run(interactive(args))
    except (ValueError, OSError, ImportError) as exc:
        Console().print(Text(f"science Bot startup failed: {type(exc).__name__}: {exc}", style="red"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
