"""Persisted LangGraph interview: collect -> verify -> choose -> present.

No learning action can execute an experiment. A complete interview prepares the
existing G2 draft; normal confirmation and execution remain mandatory.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from ....util import canonical, digest, write_json
from ..provider import _strict_json
from .state import new_state, validate_state, apply_fields, contract_hash, FIELDS
from .validation import verify, make_spec
from .intake import local_extract, model_extract
from .policy import choose, RuleInterviewPolicy, BCInterviewPolicy, ACTIONS

COMMANDS = {"/interview", "/answer", "/revise", "/resolve", "/interview-status", "/interview-options",
            "/interview-refresh", "/interview-reset", "/interview-policy", "/design-feedback"}
QUESTIONS = {
    "research_question": "你希望回答的研究问题是什么？请描述比较/预测目标。",
    "data_path": "请选择当前项目中的一个CSV相对路径；没有绑定项目时，请用 -Workspace 启动。",
    "unit_structure": "数据中的实验单位是什么关系？",
    "response": "响应变量是哪一列？请给出准确列名。", "unit": "哪个列标识实验单位？种子和行号不能自动当作独立重复。",
    "provenance": "这些数据来自哪里？", "sampling_note": "当前样本数/实验数的依据是什么？可以明确说明仅使用现有样本作探索性分析。",
    "factor": "分组/处理因素是哪一列？", "levels": "要比较的两个水平是什么？按先减后顺序填写，例如 /answer {\"levels\":[\"A\",\"B\"]}。",
    "features": "预测使用哪些数值特征列？例如 /answer {\"features\":[\"x1\",\"x2\"]}。",
    "randomization_note": "请说明实际随机分配过程；未知时回答“不知道”，不能由模型补造。",
    "missing_policy": "所选数值列有缺失。保留reject并修复数据，还是明确采用完整案例删除？配对设计会删除整个缺失单位。",
}
OPTIONS = {
    "unit_structure": [("independent_rows", "每行对应不同、独立且可交换的单位"), ("paired_units", "同一单位在两个条件下各测量一次"),
                       ("clustered", "存在区组/聚类或多次重复结构（当前不支持）"), ("temporal", "存在时间依赖（当前不支持）")],
    "provenance": [("observational", "观察性数据"), ("randomized", "实际随机分配的实验数据，需补充随机化过程"), ("synthetic", "合成数据")],
    "design": [("independent", "独立两组Welch：比较两个水平的均值差，需要独立单位和分组列"),
               ("paired", "配对t检验：按同一单位匹配两个水平，分析单位内差值"),
               ("prediction", "均值基线/OLS预测：独立单位，固定60/20/20划分，以验证MSE选择后一次测试")],
    "missing_policy": [("reject", "拒绝缺失，不删除样本"), ("drop_complete_case", "完整案例删除，报告排除单位；可能引入选择偏差")],
}


def load(session):
    ref = session.meta.get("interview_ref")
    if not ref:
        return None
    if not re.fullmatch(r"design_interviews/[a-f0-9]{32}/state.json", ref):
        raise ValueError("Invalid interview reference")
    path = session.folder/ref
    if path.resolve() != path:
        raise ValueError("Interview state cannot be redirected")
    state = json.loads(path.read_text(encoding="utf-8"))
    validate_state(state)
    if digest(state) != session.meta.get("interview_hash"):
        raise ValueError("Interview state hash mismatch")
    return state


def save(session, state):
    ref = f"design_interviews/{state['id']}/state.json"
    write_json(session.folder/ref, state)
    session.meta.update(interview_ref=ref, interview_hash=digest(state))
    session.save()


def route_override(session, text, request):
    command = text.partition(" ")[0]
    if command in COMMANDS:
        return True
    if request.intent == "design":
        return True
    if re.search(r"访谈|逐步设计|一步步.{0,8}实验|design interview", text, re.I):
        return not bool(re.search(r"不要|禁止|don't|do not|什么是|如何|怎么", text, re.I))
    state = load(session)
    if not state or not state["active"] or state.get("draft") or not state.get("pending"):
        return False
    if request.intent in {"numeric", "project_qa", "tabular", "unsupported"}:
        return False
    if text in {"不知道", "不清楚", "不确定", "unknown"} or re.fullmatch(r"[1-4]", text.strip()):
        return True
    if re.match(r"\s*\{", text) or re.search(r"(?:"+"|".join(FIELDS)+r")\s*[:=]", text):
        return True
    if text.strip() in {value for options in OPTIONS.values() for value, _ in options}:
        return True
    # A free-form answer is accepted through /answer. Unrelated questions keep
    # their normal routing and suspend the interview rather than become facts.
    return False


def summary(state):
    return {"id": state["id"], "revision": state["revision"], "active": state["active"],
            "fields": deepcopy(state["fields"]), "unknown": list(state["unknown"]), "conflicts": deepcopy(state["conflicts"]),
            "pending": deepcopy(state["pending"]), "validation": deepcopy(state["validation"]), "policy": state["policy"],
            "turns": state["turns"], "max_turns": state["max_turns"], "draft": deepcopy(state["draft"])}


def bound_draft_valid(session):
    binding = session.tabular.meta.get("interview_binding") if session.tabular else None
    if not binding:
        return
    state = load(session)
    if (not state or binding["contract_hash"] != contract_hash(state) or not state.get("draft")
            or state["draft"]["draft_hash"] != session.tabular.confirmation or not verify(state, session)["ready"]):
        raise ValueError("访谈设计版本、数据或预算已变化；请重新检查并生成草案")


def _inspect(session, state, turn):
    path = state["fields"].get("data_path")
    if not path:
        return
    if state["profile"] and state["profile"]["path"] == path:
        return
    context = {"workspace": session.workspace, "allowed_paths": {path}}
    state["profile"] = session._execute_tool("csv_inspect", {"path": path}, context, f"interview_{state['id']}_{turn}_inspect")


def _prepare(session, state, turn):
    validation = verify(state, session)
    if not validation["ready"]:
        raise ValueError("访谈设计未通过校验")
    existing = state.get("draft")
    if existing and existing["contract_hash"] == contract_hash(state):
        return {"answer": "该版本已有草案，请用 /status 检查并 /confirm；未重复创建实验。", **existing,
                "requires_confirmation": True}
    spec = make_spec(state)
    context = {"csv_evidence": {spec.data_path: state["profile"]}}
    def callback(chosen, evidence):
        if chosen.to_dict() != spec.to_dict() or evidence["sha256"] != state["profile"]["sha256"]:
            raise ValueError("规格或证据不匹配")
        return session._prepare_tabular(chosen)
    context["prepare_tabular"] = callback
    arguments = {key: value for key, value in spec.to_dict().items() if key != "schema_version" and value is not None}
    result = session._execute_tool("prepare_tabular_experiment", arguments, context, f"interview_{state['id']}_{state['revision']}_prepare")
    state["draft"] = {"draft_hash": result["draft_hash"], "experiment_ref": result["experiment_ref"], "contract_hash": contract_hash(state)}
    session.tabular.meta["interview_binding"] = {"id": state["id"], "revision": state["revision"], "contract_hash": contract_hash(state)}
    session.tabular.save()
    state["pending"] = None
    return result


class InterviewTurn(TypedDict, total=False):
    text: str
    turn: int
    action: str
    result: dict


def run_interview(session, request, turn):
    text = request["raw_text"]
    command, _, argument = text.partition(" ")
    current = load(session)
    fresh = (current is None or command == "/interview-reset" or command == "/interview" and bool(argument.strip())
             or command not in COMMANDS and bool(re.search(r"新实验|另一个实验|重新设计", text)))
    state = new_state() if fresh else deepcopy(current)
    state["policy"] = session.meta.get("interview_policy", "rule")
    session.meta.update(active_task="design_interview", phase="needs_input")
    result_ref = f"design_interviews/{state['id']}/turns/{turn:04d}.json"
    path = session.folder/result_ref
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["result"]
    updates, quotes, unknown = {}, {}, []
    errors, special = [], None
    observation = action = policy_id = None
    before = deepcopy(state)

    def collect(_graph):
        nonlocal updates, quotes, unknown, special
        if command == "/interview-status":
            special = {"answer": json.dumps(summary(state), ensure_ascii=False, indent=2)}
            return {}
        if command == "/interview-options":
            special = {"answer": "当前注册设计（选择仍需满足单位关系）：\n"+"\n".join(
                f"{i+1}. {description} ({value})" for i, (value, description) in enumerate(OPTIONS["design"]))+
                '\n可用 /answer {"design":"所选值"}，已有声明需用 /revise 明确更改。'}
            return {}
        if command == "/interview-policy":
            if argument.strip() not in {"rule", "bc"}:
                raise ValueError("访谈策略可选 rule / bc；不接受模型路径")
            if argument.strip() == "bc":
                BCInterviewPolicy(Path(__file__).resolve().parents[4]/"models/design_interview_bc")
            session.meta["interview_policy"] = state["policy"] = argument.strip()
            special = {"answer": "访谈策略已选择："+state["policy"]+"。执行权限与验证规则保持固定。"}
            return {}
        if command == "/design-feedback":
            value = _strict_json(argument)
            if type(value) is not dict or set(value) != {"rating", "note"} or type(value["rating"]) is not int or not 1 <= value["rating"] <= 5 or type(value["note"]) is not str or len(value["note"]) > 2000:
                raise ValueError('反馈格式为 /design-feedback {"rating":1至5,"note":"说明"}')
            if len(state["feedback"]) >= 100:
                raise ValueError("本访谈最多保存100条待审反馈")
            state["feedback"].append({**value, "turn": turn, "review_status": "pending_human_review"})
            special = {"answer": "反馈已进入待审记录；没有自动训练或更新部署权重。"}
            return {}
        if state["turns"] >= state["max_turns"]:
            return {}
        state["turns"] += 1
        state["active"] = True
        state["last_errors"] = []
        if command == "/interview-refresh":
            state["profile"] = state["validation"] = state["draft"] = None
            state["revision"] += 1
        payload = argument if command in {"/answer", "/revise", "/resolve"} else (argument.strip() if command == "/interview" else "")
        try:
            if command == "/interview" and payload and not payload.startswith("{"):
                if session.workspace is None:
                    raise ValueError("请先使用 -Workspace 绑定CSV项目")
                path = session.workspace.resolve_file(payload.strip('"\'')).relative_to(session.workspace.root).as_posix()
                updates, quotes = {"data_path": path}, {"data_path": payload}
            elif payload:
                updates, quotes, unknown = local_extract(payload, state["pending"])
            elif not fresh and command not in {"/interview", "/interview-options", "/interview-refresh"}:
                updates, quotes, unknown = local_extract(text, state["pending"])
            elif fresh and not command.startswith("/"):
                if request.get("input_paths"):
                    updates = {"data_path": request["input_paths"][0]}
                    quotes = {"data_path": text}
            if command == "/resolve" and (not updates or not set(updates) <= set(state["conflicts"])):
                raise ValueError("/resolve 只能显式解决当前冲突字段")
            model_used = False
            if not updates and not unknown and payload and session.meta["backend"] == "api":
                updates, quotes, unknown = model_extract(session, payload)
                model_used = True
            apply_fields(state, updates, turn=turn, quote=quotes, unknown=unknown,
                         resolve=command in {"/revise", "/resolve"}, source="user_grounded_model" if model_used else
                         ("user_structured" if payload.startswith("{") else "user_answer"))
            _inspect(session, state, turn)
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
            state["last_errors"] = errors[:]
        return {}

    def validate(_graph):
        if special is None:
            state["validation"] = verify(state, session)
            if errors:
                state["validation"]["checks"].append({"code": "input_rejected", "status": "blocked", "detail": errors[0], "fields": []})
                state["validation"]["ready"] = False
        return {}

    def select(_graph):
        nonlocal action, observation, policy_id
        if special is not None:
            return {}
        policy = BCInterviewPolicy(Path(__file__).resolve().parents[4]/"models/design_interview_bc") if state["policy"] == "bc" else RuleInterviewPolicy()
        action, observation, policy_id = choose(state, policy=policy)
        return {"action": action}

    def present(_graph):
        if special is not None:
            result = {"intent": "design", **special, "interview": summary(state)}
        elif action == "prepare":
            result = {"intent": "tabular", **_prepare(session, state, turn), "interview": summary(state)}
        else:
            known = ", ".join(key+"="+str(value) for key, value in state["fields"].items() if state["sources"].get(key, {}).get("kind") != "protocol_default")
            prefix = ("已记录："+known+"\n") if known else "已进入实验设计访谈，尚未授权执行。\n"
            if errors:
                prefix += "本轮未接受："+"；".join(errors)+"\n"
            if action.startswith("ask:") or action == "options:design":
                field = action.split(":", 1)[1]
                options = [{"number": i+1, "value": value, "description": description} for i, (value, description) in enumerate(OPTIONS.get(field, []))]
                question = QUESTIONS.get(field, "请选择实验设计。各方法需要满足相应单位关系，不代表可以互相替换。")
                state["pending"] = {"action": action, "field": field, "question": question, "options": options}
                answer = prefix+question+"\n"+"\n".join(f"{o['number']}. {o['description']} ({o['value']})" for o in options)
                answer += "\n可回复选项编号，或 /answer {字段JSON}；不知道时请明确说明。"
            elif action == "resolve":
                state["pending"] = {"action": action, "field": None, "options": []}
                answer = prefix+"存在声明冲突，未覆盖原值：\n"+json.dumps(state["conflicts"], ensure_ascii=False)+"\n请用 /resolve {字段:确认值} 解决。"
            else:
                state["pending"] = None
                state["active"] = False
                state["closed_reason"] = "needs_external_information"
                reasons = [c["detail"] for c in state["validation"]["checks"] if c["status"] == "blocked"]
                answer = prefix+"当前停止准备，未执行实验。\n"+"\n".join(reasons)+"\n补充信息后可 /answer {字段JSON}；/revise 显式修订已有声明。"
            result = {"intent": "design", "answer": answer, "interview": summary(state), "validation": state["validation"], "action": action}
        if result.get("intent") != "tabular":
            session.meta.update(active_task="design_interview", phase="needs_input" if state["active"] else "design_blocked")
        save(session, state)
        record = {"schema_version": "design_trace_v1", "turn": turn, "interview_id": state["id"],
                  "revision_before": before["revision"], "revision_after": state["revision"], "input": text,
                  "updates": updates, "unknown": unknown, "errors": errors, "observation": observation,
                  "selected_action": action, "policy_hash": policy_id, "validation": state["validation"],
                  "expert_action": None, "annotation_status": "unreviewed", "result": result}
        write_json(session.folder/result_ref, record)
        session.emit("design_decision", {"action": action, "interview_id": state["id"], "revision": state["revision"], "trace_ref": result_ref})
        return {"result": result}

    builder = StateGraph(InterviewTurn)
    for name, function in (("collect_fields", collect), ("verify_design", validate), ("choose_action", select), ("present_decision", present)):
        builder.add_node(name, function)
    builder.add_edge(START, "collect_fields")
    builder.add_edge("collect_fields", "verify_design")
    builder.add_edge("verify_design", "choose_action")
    builder.add_edge("choose_action", "present_decision")
    builder.add_edge("present_decision", END)
    with SqliteSaver.from_conn_string(str(session.folder/"design_graph.sqlite")) as saver:
        graph = builder.compile(checkpointer=saver)
        result = graph.invoke({"text": text, "turn": turn}, {"configurable": {"thread_id": state["id"]}, "recursion_limit": 12})
    return result["result"]
