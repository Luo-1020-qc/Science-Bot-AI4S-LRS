"""Protected interview checks; absence of evidence is not a scientific pass."""
from ..experiment import ExperimentSpec, ExecutionPlan
from ..adapters.tabular import validate_data
from .state import missing_fields, contract_hash

SPEC_FIELDS = {"data_path", "research_question", "design", "response", "unit", "provenance", "sampling_note",
               "factor", "levels", "features", "randomization_note", "missing_policy", "alpha", "seed"}


def make_spec(state):
    return ExperimentSpec.from_dict({key: value for key, value in state["fields"].items() if key in SPEC_FIELDS})


def verify(state, parent=None):
    checks = []
    def add(code, status, detail, fields=()):
        checks.append({"code": code, "status": status, "detail": detail, "fields": list(fields)})
    missing = missing_fields(state)
    if missing:
        add("missing_fields", "blocked", "尚缺："+", ".join(missing), missing)
    if state["unknown"]:
        add("unknown_facts", "blocked", "用户不知道的科学事实不能由模型补造", state["unknown"])
    if state["conflicts"]:
        add("conflicting_declarations", "blocked", "请使用 /resolve 显式解决冲突", state["conflicts"])
    if state["turns"] >= state["max_turns"]:
        add("interview_budget", "blocked", "访谈已达到24轮上限，保存后可开始新访谈")
    values = state["fields"]
    structure, design = values.get("unit_structure"), values.get("design")
    if structure in {"clustered", "temporal"}:
        add("unsupported_structure", "blocked", "区组/聚类或时间依赖需要其他工具，不会套用独立或配对设计", ["unit_structure"])
    elif design and structure and ((design == "paired") != (structure == "paired_units")):
        add("design_structure_mismatch", "blocked", "设计与单位关系不一致，请修订明确的声明", ["design", "unit_structure"])
    if not any(c["status"] == "blocked" for c in checks):
        try:
            spec = make_spec(state)
        except ValueError as exc:
            add("invalid_specification", "blocked", str(exc))
        else:
            add("specification", "passed", "字段结构与已注册方法匹配")
            if parent is not None:
                try:
                    if parent.workspace is None:
                        raise ValueError("尚未绑定数据工作区")
                    profile = state.get("profile")
                    if not profile or profile["path"] != spec.data_path:
                        raise ValueError("尚未通过 csv_inspect 检查显式选择的 CSV")
                    source = parent.workspace.read_text(spec.data_path)
                    if source["sha256"] != profile["sha256"]:
                        add("data_identity_changed", "blocked", "CSV自检查后发生变化；/interview-refresh 重新检查并形成新版本", ["data_path"])
                    else:
                        data = validate_data(spec, source["text"])
                        add("data_structure", "passed", f"保留{data['units']}个声明单位；排除{data['missing_units']}个缺失单位")
                        needed = len(ExecutionPlan.build(spec, profile["sha256"]).nodes)+(0 if state.get("draft") else 1)
                        remaining = parent.limits["tool_calls"]-parent.meta["tool_attempts"]
                        add("tool_budget", "passed" if remaining >= needed else "blocked",
                            f"还需准备及执行{needed}次工具，当前剩余{remaining}次")
                except (ValueError, OSError) as exc:
                    code = "missing_data_policy" if "缺失值" in str(exc) else "data_validation"
                    add(code, "blocked", str(exc), ["missing_policy"] if code == "missing_data_policy" else ())
    add("scientific_assumptions", "unverified", "来源、独立性、随机化和样本依据是用户声明；未通过列检查证明")
    return {"schema_version": "design_validation_v1", "contract_hash": contract_hash(state),
            "ready": not any(c["status"] == "blocked" for c in checks), "checks": checks,
            "missing": missing, "execution_authorized": False, "scientific_success": None}
