"""Local research tools: fixed read-only workers, durable evidence, no live jobs."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

from ...util import digest, write_json
from .contracts import ToolSpec
from .provider import _strict_json

HUB = Path(__file__).resolve().parents[3]/"research/strategy_learning"
COMMANDS = {"/research", "/doe"}
STUDIES = ("g2_2", "g2_3", "g2_4")
HELP = """研究接口已接入：G2.2 / G2.3 / G2.4（本地研究模式）。
/research status | results [g2_2|g2_3|g2_4] | verify [study]
/research simulate g2_2 [--policy rule|bc] [--seed 21|37|59] [--scenario ordinary_comparison]
/research simulate g2_3 [--policy rule|bc|bc_ppo|ppo_scratch|feedback_baseline|feedback_ppo] [--domain cvit|tabular] [--scenario existing_running]
/research compare g2_3 [--seed 21] [--domain cvit] [--scenario existing_running]
/research review-export g2_2 | review-import g2_2 <工作区内已审阅JSONL路径>
/doe demo | template [crd_two_arm|rcbd_two_arm|factorial_2x2]
/doe validate <需求JSON路径> <草案JSON路径>（两个文件须位于绑定工作区）
/doe validate {"request":{...},"contract":{...}}（显式结构化输入）
/doe recheck | status | report | review-export
/doe review-import <工作区内已审阅JSONL路径>
默认规则访谈不变。策略仅运行开发集模拟，无真实计算/模型API/GPU/重训。
DOE通过表示可审阅，未完成专家校准，也不授权实验执行。完整结果保存在当前会话 research/ 下。"""


def alias(value):
    return {"g2.2": "g2_2", "g2.3": "g2_3", "g2.4": "g2_4"}.get(value.casefold(), value.casefold())


def recognizes(text):
    return text.strip().partition(" ")[0] in COMMANDS


def natural_command(text):
    """Only bounded explicit requests; explanation/negation remains normal chat."""
    if recognizes(text):
        return text
    if re.search(r"不要|禁止|别|do not|don't|如何|怎么|什么|是否|能否|[?？]", text, re.I):
        return None
    if re.search(r"(?:运行|演示|展示|启动).{0,10}(?:G2[._]4|DOE).{0,10}(?:演示|示例|demo)|(?:运行|演示).{0,6}DOE$", text, re.I):
        return "/doe demo"
    if re.search(r"(?:运行|启动|演示).{0,12}CViT.{0,12}模拟", text, re.I):
        return "/research simulate g2_3"
    match = re.search(r"(?:查看|检查|展示).{0,8}(G2[._][234]).{0,8}(?:研究)?(?:结果|状态|接口)", text, re.I)
    if match:
        return "/research results "+alias(match[1])
    return None


def worker(payload):
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    if len(body) > 512000:
        raise ValueError("研究请求过大")
    try:
        completed = subprocess.run([sys.executable, "-I", "-B", str(HUB/"online_worker.py")],
            input=body, capture_output=True, text=True, encoding="utf-8", errors="strict", cwd=HUB,
            timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ValueError("研究进程未完成："+type(exc).__name__) from None
    if len(completed.stdout) > 2*1024*1024:
        raise ValueError("研究返回超过上限")
    try:
        value = _strict_json(completed.stdout)
    except (ValueError, TypeError):
        raise ValueError("研究进程未返回有效JSON；没有启动真实任务") from None
    if completed.returncode or not value.get("ok"):
        raise ValueError(value.get("error", "Research process failed"))
    if any(value.get(key) != 0 for key in ("real_tool_executions", "real_model_requests", "real_gpu_jobs", "formal_training_transitions")):
        raise ValueError("研究边界不一致")
    return value["result"]


def saved(session, *, doe=False):
    record = session.meta.get("research_doe_latest" if doe else "research_latest")
    if not record:
        return None
    relative = record.get("result_ref", "")
    if not re.fullmatch(r"research/(?:[a-f0-9]{16}|[a-f0-9]{64})/result.json", relative):
        raise ValueError("Invalid saved research reference")
    path = session.folder/relative
    if path.resolve() != path or path.stat().st_size > 2*1024*1024:
        raise ValueError("Saved research result redirected or oversized")
    value = _strict_json(path.read_text(encoding="utf-8"))
    if digest(value) != record["result_hash"]:
        raise ValueError("Saved research evidence changed")
    return value


def summary(session):
    value = saved(session)
    doe_value = saved(session, doe=True)
    return {"available": True, "mode": "research_only", "studies": list(STUDIES), "default_interview_policy": "rule",
        "doe": {"ready_for_review": doe_value["result"]["validation"]["ready_for_review"],
                "result_ref": session.meta["research_doe_latest"]["result_ref"]} if doe_value else None,
        "execution_authorized": False, "latest": {k: session.meta["research_latest"][k] for k in ("study", "action", "result_ref")} if value else None}


def register(registry):
    registry.register(ToolSpec("research_interface", "Explicit local research request. Frozen development simulations, results, DOE validation and review only. No live experiments or training.",
        {"type": "object", "properties": {"payload": {"type": "object"}}, "required": ["payload"], "additionalProperties": False},
        domain="research", read_only=True, preconditions=("explicit_research_request",)),
        lambda args, context: worker(args["payload"]) if context.get("explicit_research_request") is True else _denied())


def _denied():
    raise ValueError("研究工具需要明确的研究请求")


def _read_selected(session, path):
    if session.workspace is None:
        raise ValueError("请先用 -Workspace 绑定输入文件所在项目，或提交内联JSON")
    result = session.workspace.read_text(path)
    return result, {"path": result["path"], "sha256": result["sha256"], "bytes": result["bytes"]}


def parse(session, text):
    command, _, tail = text.strip().partition(" ")
    if command == "/doe" and tail.startswith("validate {"):
        value = _strict_json(tail[len("validate "):])
        if type(value) is not dict or set(value) != {"request", "contract"}:
            raise ValueError("DOE内联JSON需且只需request和contract")
        return {"study": "g2_4", "action": "validate", **value}, []
    # posix=False preserves Windows backslashes in explicitly quoted filenames.
    tokens = [item.strip('"') for item in shlex.split(tail, posix=False)]
    if command == "/research":
        if not tokens or tokens == ["help"]:
            return None, []
        action = tokens.pop(0)
        if action in {"status", "report"} and not tokens:
            return {"local": action}, []
        if action not in {"results", "verify", "simulate", "compare", "review-export", "review-import"}:
            raise ValueError("研究入口只开放状态、结果、完整性检查和开发模拟，不开放训练/真实执行")
        study = alias(tokens.pop(0)) if tokens and not tokens[0].startswith("--") else "g2_4"
        if study not in STUDIES:
            raise ValueError("请选择g2_2、g2_3或g2_4")
        payload = {"study": study, "action": action}
        if action in {"review-export", "review-import"}:
            if study != "g2_2":
                raise ValueError("G2.2审阅使用此命令；G2.4使用 /doe review-export 或 review-import")
            if action == "review-export" and not tokens:
                return {"study": study, "action": "review-queue"}, []
            if action == "review-import" and len(tokens) == 1:
                source, evidence = _read_selected(session, tokens[0])
                return {"study": study, "action": action, "records": [_strict_json(line) for line in source["text"].splitlines() if line.strip()]}, [evidence]
            raise ValueError("审阅导入需提供一个工作区JSONL路径")
        if len(tokens) % 2:
            raise ValueError("模拟选项需要 --名称 值")
        for option, value in zip(tokens[::2], tokens[1::2]):
            if option not in {"--policy", "--seed", "--domain", "--scenario"} or option[2:] in payload:
                raise ValueError("未知或重复研究参数")
            payload[option[2:]] = int(value) if option == "--seed" and value.isdigit() else value
        if action in {"results", "verify"} and len(payload) != 2:
            raise ValueError("结果和完整性检查不接受模拟参数")
        if action in {"simulate", "compare"} and study == "g2_4":
            raise ValueError("G2.4请使用 /doe demo 或 /doe validate")
        return payload, []
    if command != "/doe":
        raise ValueError("Unknown research command")
    if not tokens or tokens == ["help"]:
        return None, []
    action = tokens.pop(0)
    if action in {"status", "report"} and not tokens:
        return {"local": action}, []
    if action in {"demo", "template"} and len(tokens) <= 1:
        return {"study": "g2_4", "action": action, **({"family": tokens[0]} if tokens else {})}, []
    if action == "recheck" and not tokens:
        value = saved(session, doe=True)
        if not value or value["study"] != "g2_4" or not all(k in value["result"] for k in ("request", "contract")):
            raise ValueError("当前没有可复核的DOE草案")
        # Re-read explicitly selected original inputs; changed data forms a new result.
        paths = value.get("input_evidence", [])
        if len(paths) == 2:
            return parse(session, '/doe validate "'+paths[0]["path"]+'" "'+paths[1]["path"]+'"')
        return {"study": "g2_4", "action": "validate", "request": value["result"]["request"], "contract": value["result"]["contract"]}, []
    if action == "validate" and len(tokens) == 2:
        values = [_read_selected(session, path) for path in tokens]
        return {"study": "g2_4", "action": "validate", "request": _strict_json(values[0][0]["text"]), "contract": _strict_json(values[1][0]["text"])}, [v[1] for v in values]
    if action == "review-export" and not tokens:
        return {"study": "g2_4", "action": "review-queue"}, []
    if action == "review-import" and len(tokens) == 1:
        source, evidence = _read_selected(session, tokens[0])
        records = [_strict_json(line) for line in source["text"].splitlines() if line.strip()]
        return {"study": "g2_4", "action": "review-import", "records": records}, [evidence]
    raise ValueError("研究命令或参数不支持；输入 /research 查看用法")


def describe(payload, value):
    action, study = payload["action"], payload["study"]
    suffix = "\n真实工具/模型API/GPU/策略训练均未执行；实验执行未授权。"
    if "validation" in value:
        v = value["validation"]
        codes = [r["code"] for r in v["checks"] if r["status"] == "blocked"]
        d = v.get("diagnostics") or {}
        return (f"G2.4 DOE {'可进入审阅' if v['ready_for_review'] else '需要修订'}。"+
            ("这是合成示例，请替换为有依据的实际声明。" if value.get("synthetic_template") else "")+
            f"\n阻断项：{', '.join(codes) or '无'}\n计划单位：{d.get('runs')}；残差自由度：{d.get('residual_df')}；条件名义功效：{d.get('nominal_power')}"+
            "\n现实假设仍待核实；真人专家校准尚未完成。"+suffix)
    if action == "simulate":
        return (f"{study} 开发模拟，策略={value['policy']}；场景={value['scenario']}。\n严格/当前协议成功={value['success']}；决策={value['decisions']}；模拟启动={value['mock_launches']}。\n"+
                " → ".join(value["actions"])+"\nmetric=null；模拟结果不代表真实科研精度。"+suffix)
    if action == "compare":
        return "同一开发场景的冻结策略比较：\n"+"\n".join(f"{r['policy']}: 成功={r['success']}, 决策={r['decisions']}" for r in value["comparisons"])+suffix
    if action == "review-queue":
        return f"已导出{len(value['records'])}条训练案例待审副本到当前会话。真人专家标签0；请在绑定项目中另存审阅文件后导入。"+suffix
    if action == "review-import":
        return f"已验证并保存{len(value['records'])}条外部声明的审阅记录。身份未独立核验，不触发训练、改规则或授权。"+suffix
    if action == "verify":
        return f"{study} 冻结制品完整性检查通过，检查{value['artifacts_checked']}个文件。"+suffix
    return f"{study} 历史研究结果：\n"+json.dumps(value, ensure_ascii=False, indent=2)+suffix


def respond(session, text, turn):
    payload, evidence = parse(session, text)
    if sum(row["bytes"] for row in evidence) > session.limits["read_bytes"]:
        raise ValueError("研究输入超过当前会话的文件读取预算；请缩小单批审阅或输入文件")
    if payload is None:
        session.meta["phase"] = "answered"
        return {"intent": "research", "answer": HELP, "execution_authorized": False}
    if "local" in payload:
        previous = saved(session, doe=text.startswith("/doe"))
        value = summary(session) if payload["local"] == "status" else previous
        session.meta["phase"] = "answered"
        return {"intent": "research", "answer": json.dumps(value or {"status": "尚无研究结果"}, ensure_ascii=False, indent=2), "research": value, "execution_authorized": False}
    request_hash = digest([payload, evidence])
    # Keep full identities in the record/cache while limiting Windows path length.
    ref = "research/"+request_hash[:16]+"/result.json"
    path = session.folder/ref
    if path.resolve() != path:
        raise ValueError("Research output path cannot be redirected")
    if path.exists() and payload["action"] != "verify":
        cached = session.meta.get("research_cache", {}).get(request_hash)
        if not cached or path.resolve() != path:
            raise ValueError("Untracked or redirected research cache")
        record = _strict_json(path.read_text(encoding="utf-8"))
        if digest(record) != cached or record.get("request_hash") != request_hash:
            raise ValueError("Research cache integrity mismatch")
    else:
        value = session._execute_tool("research_interface", {"payload": payload}, {"explicit_research_request": True},
            "research_"+request_hash+(f"_verify_{turn}" if payload["action"] == "verify" else ""))
        record = {"schema_version": "online_research_result_v1", "study": payload["study"], "action": payload["action"],
                  "request_hash": request_hash, "input_evidence": evidence, "result": value, "execution_authorized": False}
        write_json(path, record)
        session.meta.setdefault("research_cache", {})[request_hash] = digest(record)
    session.meta["research_latest"] = {"study": payload["study"], "action": payload["action"], "result_ref": ref, "result_hash": digest(record)}
    if payload["study"] == "g2_4" and "validation" in record["result"]:
        session.meta["research_doe_latest"] = dict(session.meta["research_latest"])
    # Standalone editable copies live in the session; frozen queues stay read-only.
    folder = path.parent
    if record["action"] == "review-queue":
        copied = folder/"pending_review_copy.jsonl"
        if not copied.exists():
            copied.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n" for row in record["result"]["records"]), encoding="utf-8")
    if "validation" in record["result"]:
        for name in ("request", "contract", "validation"):
            write_json(folder/(name+".json"), record["result"][name])
    session.meta.update(phase="research_review", last_report_kind="research")
    session.save()
    session.emit("research_result", {"study": payload["study"], "action": payload["action"], "result_ref": ref})
    return {"intent": "research", "answer": describe(payload, record["result"])+"\n结果："+str(path),
            "research": record, "result_ref": ref, "requires_confirmation": False, "execution_authorized": False}
