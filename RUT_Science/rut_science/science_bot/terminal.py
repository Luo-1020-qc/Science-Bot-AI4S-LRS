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

COMMANDS = ["/help", "/workspace", "/files", "/read", "/design", "/confirm", "/status", "/experiments", "/pause", "/resume", "/cancel", "/report", "/model-output", "/events", "/clear", "/exit"]
from .general.interview.runtime import COMMANDS as INTERVIEW_COMMANDS
from .general.research import COMMANDS as RESEARCH_COMMANDS
COMMANDS += sorted(INTERVIEW_COMMANDS)
COMMANDS += sorted(RESEARCH_COMMANDS)
from .general.tool_library import COMMANDS as DETAILED_COMMANDS
COMMANDS += sorted(DETAILED_COMMANDS)
from .general.planning.runtime import COMMANDS as PLANNING_COMMANDS
COMMANDS += sorted(PLANNING_COMMANDS)
COMMANDS += ['/home', '/deliver']


def plain_model_text(value):
    """Escape terminal controls and directional overrides; never parse markup."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return "".join(f"\\u{ord(char):04x}" if char != "\n" and unicodedata.category(char) in {"Cc", "Cf", "Cs"}
                   else char for char in text)


def response_text(response):
    """Render the host answer, or structured/legacy clarification questions."""
    answer=response.get('answer')
    if answer:
        return plain_model_text(answer)
    questions=response.get('questions') or []
    if not isinstance(questions,list):questions=[questions]
    lines=[]
    for question in questions:
        if not isinstance(question,dict):
            lines.append(plain_model_text(question));continue
        prompt=question.get('question') or question.get('text')
        if prompt:lines.append(plain_model_text(prompt))
        else:lines.append(plain_model_text(question));continue
        if question.get('rationale') and not question.get('choice_id'):
            lines.append('为什么问：'+plain_model_text(question['rationale']))
        options=question.get('options') or []
        if not isinstance(options,list):options=[options]
        for i,option in enumerate(options,1):
            label=option.get('label',option.get('value',option)) if isinstance(option,dict) else option
            lines.append(f'{i}. '+plain_model_text(label))
    return '\n'.join(lines)


def show_response(console,response,title='science Bot'):
    text=response_text(response)
    if text:console.print(Panel(Text(text),title=title,border_style='cyan'))
    refs=response.get('evidence_refs') or []
    if not isinstance(refs,list):refs=[refs]
    if refs:
        console.print(Text('来源：\n'+'\n'.join(plain_model_text(ref) for ref in refs),style='dim'))


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
              "content": "模型回复", "tool_calls": "工具调用提议", "actual_model": "实际模型",
              "findings": "发现与证据", "limitations": "限制", "artifact_refs": "产物引用"}
    body = Text()
    body.append(STATUS_LABELS.get(saved["status"], "未知校验状态")+"\n", style="bold")
    body.append("模型返回与工具执行证据分开记录；科研任务的验收结果见 /report。\n\n", style="dim")
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
    elif event["kind"] == "task_routed":
        console.print(Text("  任务类型："+plain_model_text(p["intent"]), style="dim"))
    elif event["kind"] == "general_tool_result":
        console.print(Text("  ✓ "+plain_model_text(p["tool"])+" · "+plain_model_text(p["evidence_ref"]), style="green"))
    elif event["kind"] == "tabular_step":
        console.print(Text("  表格实验步骤完成："+plain_model_text(p["node"]), style="green"))
    elif event["kind"] == "design_decision":
        console.print(Text(f"  设计访谈 · 版本{p['revision']} · {p['action'] or '状态/反馈'}", style="dim"))
    elif event["kind"] == "general_error":
        console.print(Text("任务暂停："+plain_model_text(p["error_type"])+"；未自动启动默认实验。", style="yellow"))
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
    if session.meta.get('engine_version') == 'general_v1':
        from .presentation import show_home, session_view
        show_home(console, session_view(session))
        return
    title = Text("science ", style="bold bright_cyan") + Text("Bot", style="bold bright_magenta")
    console.print()
    console.print(Panel(title+Text("\nresearch, with evidence.", style="dim"), border_style="bright_black", padding=(1, 3)))
    engine = "general · " if session.meta.get("engine_version") == "general_v1" else ""
    console.print(Text(f"  {engine}{session.meta['backend']} · numeric planner={session.meta['planner']} · {session.meta['model']} · session {session.meta['id'][:8]}"))
    console.print("  [dim]/help commands   /model-output model replies   /pause safe pause   Ctrl+D save & exit[/dim]\n")


def show_status(console, session):
    status = session.status()
    if status.get('planning') and status.get('active_task')=='research_planning':
        from .general.planning.ledger import load
        from .presentation import plan_view, show_planning
        show_planning(console, plan_view(load(session), example=session.meta.get('interface_example', False)))
        return
    detailed = status.get("tool_library", {}).get("state")
    if status.get("active_task") == "research" and detailed and detailed.get("calls"):
        console.print(Panel(Text(f"Phase: {status['phase']}\nMode: detailed offline tools\nRegistered: 20 implemented / 45 contracts\nCalls: {detailed['calls']}\nScenario: {detailed['scenario']}\nReferences: {', '.join(detailed['refs'])}\nExecution: not authorized"), title="detailed tool library", border_style="cyan"))
        return
    if status.get("active_task") == "research":
        research = status["research"]
        console.print(Panel(Text(f"Phase: {status['phase']}\nMode: research / simulation only\nStudies: G2.2 / G2.3 / G2.4\nDefault interview policy: rule\nLatest: {research['latest']}\nExecution: not authorized"), title="research workspace", border_style="cyan"))
        return
    if status.get("interview") and status["active_task"] == "design_interview":
        interview = status["interview"]
        pending = interview.get("pending") or {}
        console.print(Panel(Text(f"Phase: {status['phase']}\nInterview revision: {interview['revision']}\nPolicy: {interview['policy']}\nTurns: {interview['turns']}/{interview['max_turns']}\nKnown fields: {', '.join(interview['fields'])}\nUnknown: {', '.join(interview['unknown']) or 'none'}\nConflicts: {', '.join(interview['conflicts']) or 'none'}\nNext: {pending.get('question', '检查反馈并补充声明')}\nExecution: not authorized"), title="design interview", border_style="cyan"))
        return
    if status.get("tabular"):
        tabular = status["tabular"]
        console.print(Panel(Text(f"Phase: {status['phase']}\nDesign: {tabular['spec']['design']}\nCSV: {tabular['spec']['data_path']}\nResponse: {tabular['spec']['response']}\nUnit: {tabular['spec']['unit']}\nCompleted: {', '.join(tabular['completed']) or 'none'}\nDraft hash: {status['draft_hash']}\nConfirmed: {status['confirmed']}\nFolder: {tabular['folder']}"), title="tabular experiment", border_style="cyan"))
        return
    if status.get("engine_version") == "general_v1" and status["spec"] is None:
        from .presentation import show_planning
        show_planning(console, None)
        return
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
    if session.status().get("tabular"):
        console.print_json(data=session.status()["tabular"])
        return
    if session.env is None:
        console.print(Text("当前没有活动的数值实验。请先明确数据集与实验任务。"))
        return
    table = Table("Experiment", "State", "Validation L2", "Attempts", border_style="bright_black")
    for e in session.env.observe()["experiments"]:
        if e["status"] != "untried":
            table.add_row(e["candidate_ref"], e["status"], f"{e['validation_mean']:.6f}" if e["observed"] else "—", str(e["attempts"]))
    console.print(table)


def open_session(args):
    if getattr(args, 'example', False):
        from .interface_demo import create_example
        return create_example(args.sessions or ROOT.parent/'.local/interface_examples/terminal', workspace=args.workspace)
    if args.resume:
        return ScienceSession.restore(args.resume, workspace=args.workspace)
    from .general.conversation import GeneralSession
    return GeneralSession.create(args.sessions, backend=args.backend, planner=args.planner,
        checkpoint=args.checkpoint, model=args.model, workspace=args.workspace,
        spec=BudgetedResearchSpec(dataset=args.dataset, split="demo", compute_units=args.budget) if args.dataset else None)


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
        if event['kind'] == 'model_output' and not getattr(args, 'verbose_events', False):
            console.print(Text('  模型提议已保存；需要时用 /model-output 查看。', style='dim'))
        else:
            show_event(console, session, event)
    session.event_callback = on_event
    prompt = PromptSession(history=FileHistory(str(session.folder/"terminal.history")),
                           completer=WordCompleter(COMMANDS), complete_while_typing=False)

    def toolbar():
        resource = f"{session.env.state['cu']:g}/{session.spec.compute_units} search CU" if session.env is not None else "general conversation"
        return HTML(f" science Bot  |  {session.meta['phase']}  |  {resource}  |  /help ")

    async def work():
        try:
            await asyncio.to_thread(session.run)
            if hasattr(session, "tabular") and session.meta.get("active_task") == "tabular" and session.tabular.done:
                report = session.research_report()
                console.print(Panel(Text(f"CSV analysis complete\nDesign: {report['spec']['design']}\nReport: {session.tabular.folder / 'report.md'}"), title="research complete", border_style="green"))
                console.print_json(data=report["metrics"])
            elif session.env is not None and session.env.state["report"]:
                report = session.env.state["report"]
                report_folder = session.numeric.folder if hasattr(session, "numeric") and session.numeric else session.folder
                console.print(Panel(Text(f"Scientific success: {report['scientific_success']}\nSealed relative L2: {report['sealed_error']}\nReport: {report_folder / 'report.md'}"),
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
                    table = Table('你想做什么', '输入', border_style='green')
                    for goal, commands in [('开始与继续', '直接描述目标；/plan start；/plan resume'),
                        ('查看与理解', '/home；/status；/plan map；/plan explain 字段'),
                        ('修订与复核', '/plan revise 字段: 内容；/plan review；/plan accept 字段'),
                        ('论文证据', '/plan evidence list；/plan evidence add <JSON>'),
                        ('交付与导出', '/report；/deliver；/plan approve <当前哈希>'),
                        ('工作区与工具', '/workspace；/files；/read；/design；/tools；/research；/doe'),
                        ('诊断与退出', '/model-output；/events；/pause；/cancel；/exit')]:
                        table.add_row(goal, commands)
                    console.print(table)
                    console.print(Text('完整操作见项目 docs/USAGE.md 与 docs/HARNESS_PLANNING.md。规划确认不会启动实验。', style='dim'))
                elif command == '/home':
                    banner(console, session); show_status(console, session)
                elif command == "/status":
                    show_status(console, session)
                elif command in RESEARCH_COMMANDS or command in DETAILED_COMMANDS or command in PLANNING_COMMANDS:
                    if running:
                        console.print("Pause the current run before opening research tools."); continue
                    response = await asyncio.to_thread(session.message, line)
                    show_response(console,response,title='研究规划' if command in PLANNING_COMMANDS else 'research / DOE')
                    if response.get('intent') != 'planning':show_status(console, session)
                elif command == "/interview-status":
                    from .general.interview.runtime import load, summary
                    value = load(session)
                    console.print_json(data=summary(value) if value else {"status": "no design interview"})
                elif command in INTERVIEW_COMMANDS:
                    if running:
                        console.print("Pause the current run before changing design declarations."); continue
                    response = await asyncio.to_thread(session.message, line)
                    show_response(console,response,title='design interview')
                    show_status(console, session)
                elif command == "/design":
                    if running:
                        console.print("Pause the current run before preparing a new design."); continue
                    value = argument.strip()
                    if not value.startswith("{"):
                        if session.workspace is None:
                            raise ValueError("Use -Workspace before selecting a specification file")
                        value = session.workspace.read_text(value)["text"]
                    response = await asyncio.to_thread(session.message, "/design "+value)
                    show_response(console,response,title='experiment design')
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
                    if not running and session.env is not None and session.meta.get("engine_version") != "general_v1":
                        session.env.state["phase"] = "cancelled"; session.meta["phase"] = "cancelled"; session.save()
                    console.print("Cancellation requested.")
                elif command == "/clear":
                    console.clear(); banner(console, session)
                elif command == "/events":
                    console.print_json(data=session.events()[-8:])
                elif command == "/report":
                    if session.meta.get('last_report_kind') == 'research_planning':
                        from .presentation import show_delivery
                        show_delivery(console, session)
                    else:
                        report = session.research_report() if hasattr(session, "research_report") else session.env.state["report"]
                        console.print_json(data=report or {"status": "not finalized"})
                elif command == '/deliver':
                    if running:console.print('请先暂停当前运行，再导出交付物。');continue
                    from .presentation import export_bundle
                    bundle = await asyncio.to_thread(export_bundle, session)
                    body = Text('交付物已保存，保留草案/确认状态、缺口及未执行标记。\n\n')
                    for kind in ('html', 'markdown', 'json'):body.append(kind.upper()+'  '+plain_model_text(str(bundle[kind]))+'\n')
                    console.print(Panel(body, title='交付已生成', border_style='green'))
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
                    show_response(console,response)
                    if response.get('intent') != 'planning':show_status(console, session)
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
    parser.add_argument("--dataset", choices=["generated", "darcy"], help="Explicitly prepare a numeric draft; otherwise start a general conversation")
    parser.add_argument("--budget", type=int, default=10)
    parser.add_argument("--workspace", type=Path, help="Open an existing project; default state: <project>/.sciencebot")
    parser.add_argument("--sessions", type=Path, help="Explicit session storage override (relative to launch directory)")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--demo", action="store_true", help="Explicitly confirm and execute one noninteractive demo")
    parser.add_argument("--preview", action="store_true", help="Render the terminal entry without creating a session")
    parser.add_argument('--example', action='store_true', help='Open a fresh synthetic offline planning example')
    parser.add_argument('--preview-html', type=Path, help='Save a read-only terminal example as HTML without creating a session')
    parser.add_argument('--verbose-events', action='store_true', help='Show full model proposals during interactive use')
    args = parser.parse_args(argv)
    if args.example and (args.demo or args.dataset or args.resume):
        parser.error('--example不能与数值演示、数据集或旧会话恢复混用')
    try:
        if args.preview_html:
            from .presentation import terminal_preview_html
            args.preview_html.parent.mkdir(parents=True, exist_ok=True)
            args.preview_html.write_text(terminal_preview_html(), encoding='utf-8')
            print(args.preview_html)
            return 0
        if args.preview:
            from .presentation import example_view, show_home, show_planning
            console = Console(width=112)
            view = example_view(); show_home(console, view); show_planning(console, view['planning'])
            console.print(Text('先确认命题理解，再补充先导依据；/report 查看交付，/deliver 导出。\nyou ›', style='green'))
            return 0
        if args.demo:
            session = open_session(args)
            if not args.resume:
                if session.env is None:
                    session.message("Darcy pressure_field" if args.dataset == "darcy" else "generated regression_output")
            session.confirm(session.confirmation)
            session.event_callback = lambda event: print(json.dumps(event, ensure_ascii=False), flush=True)
            session.run()
            print(session.folder)
            return 0 if session.env is not None and session.env.state["report"] else 2
        return asyncio.run(interactive(args))
    except (ValueError, OSError, ImportError) as exc:
        Console().print(Text(f"science Bot startup failed: {type(exc).__name__}: {exc}", style="red"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
