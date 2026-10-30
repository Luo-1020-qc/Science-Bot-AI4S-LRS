"""Concrete contracts and deployment status; only implemented tools can execute."""
import math
import re

STRING = {"type": "string", "minLength": 1, "maxLength": 2000}
REF = {"type": "string", "pattern": "[a-f0-9]{64}"}
ANY = {}
OBJECT = {"type": "object"}
BOOLEAN = {"type": "boolean"}
NUMBER = {"type": "number"}
NULLABLE_REF = {"type": ["string", "null"]}


def enum(*values):
    return {"type": "string", "enum": list(values)}


def array(items=ANY, low=0, high=1000):
    return {"type": "array", "items": items, "minItems": low, "maxItems": high}


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def output(*keys):
    refs = {"project_ref", "claim_ref", "plan_ref", "review_ref", "alignment_ref", "resolution_ref", "freeze_ref", "workflow_ref", "analysis_ref", "assessment_ref", "report_ref"}
    bools = {"live_agent_registered", "synthetic", "prior_review_invalidated", "execution_authorized", "expert_calibrated", "ready_for_review", "can_test_conditionally", "real_world_assumptions_verified", "all_clear", "passed", "real_execution_authorized", "reused", "real_training_performed", "model_assumptions_verified", "posthoc_model_selection", "practical_benefit_supported", "real_scientific_claim_verified", "automatic_retest", "change_success_threshold", "required_new_version_for_followup"}
    lists = {"tools", "changes", "finding_codes", "resolved", "still_blocked", "new_findings", "topological_order", "interval", "limitations"}
    numbers = {"units", "effect", "confidence", "df", "original_unit_count"}
    objects = {"artifact", "checks", "statistical_evidence", "next_action"}
    nulls = {"claim_supported", "scientific_success"}
    return obj({key: REF if key in refs else NULLABLE_REF if key == "job_ref" else BOOLEAN if key in bools else array() if key in lists else NUMBER if key in numbers else OBJECT if key in objects else {"type": "null"} if key in nulls else STRING for key in keys})


def spec(name, group, purpose, inputs, outputs, preconditions, acceptance, *, mode="offline_implemented", effects="sandbox_artifacts_only", failures=(), next_tools=()):
    return {"name": name, "group": group, "purpose": purpose, "implementation": mode,
        "input_schema": obj(inputs), "output_schema": outputs, "preconditions": list(preconditions), "acceptance": list(acceptance),
        "effects": effects, "idempotency": "Content-addressed immutable outputs; mock job key is frozen-plan identity",
        "failure_contract": list(failures) or ["Invalid schema or stale artifact: fail before action; do not silently default"],
        "authorization": "local_mock_only; never grants real execution", "next_tools": list(next_tools)}


CATALOG = [
spec("tool_catalog", "discovery", "查看工具输入输出、状态、权限与后续步骤", {}, output("tools", "live_agent_registered"), [], ["清楚区分已实现、已有入口与待实现契约"]),
spec("project_create", "project", "建立项目目标与本地模拟工作区身份", {"title": STRING, "objective": STRING}, output("project_ref"), [], ["项目目标和运行模式有来源"], next_tools=("claim_define", "plan_create")),
spec("claim_define", "claim", "将研究结论写成可检查的响应、对比、单位、方向和范围", {
    "project_ref": REF, "statement": STRING, "response": STRING, "primary_term": STRING, "direction": enum("lower", "higher"),
    "practical_margin": {"type": "number", "minimum": 0, "maximum": 1e6}, "population_scope": STRING,
    "factor_levels": array(obj({"factor": STRING, "baseline": STRING, "candidate": STRING}), 1, 2), "expected_unit_definition": STRING},
    output("claim_ref"), ["项目已建立", "单一预设主要对比"], ["自由文本与结构化ClaimSpec由用户核对，不能由字符串匹配证明科学含义"], next_tools=("claim_check_plan",)),
spec("plan_create", "plan", "从受限DOE家族建立可修改方案及其需求证据", {"project_ref": REF, "family": enum("crd_two_arm", "rcbd_two_arm", "factorial_2x2")},
    output("plan_ref", "synthetic", "execution_authorized"), ["有效项目"], ["生成显式标记的合成模板", "没有自动执行"], next_tools=("plan_patch", "plan_review")),
spec("plan_patch", "plan", "基于预期哈希修改具体字段，保留父版本和原因", {"plan_ref": REF, "expected_contract_hash": REF,
    "changes": array(obj({"path": STRING, "value": ANY}), 1, 20), "reason": STRING}, output("plan_ref", "prior_review_invalidated", "execution_authorized"),
    ["基础方案身份未变化", "调用者明确提出修改"], ["原版本不可变", "新需求证据绑定新方案", "重新编译并强制新复核"], failures=("Stale hash", "Forbidden identity/authorization patch", "Invalid DOE schema"), next_tools=("plan_diff", "plan_review", "claim_check_plan")),
spec("plan_diff", "plan", "比较两版方案，明确科学与执行协议变化", {"old_plan_ref": REF, "new_plan_ref": REF}, output("changes", "old_plan_ref", "new_plan_ref"),
    ["同一项目的两个版本"], ["列出真实字段差异而非语言总结"], next_tools=("plan_review",)),
spec("artifact_read", "evidence", "读取已登记且哈希正确的类型化制品", {"artifact_ref": REF}, output("artifact"), ["只接受本沙箱登记的完整哈希"], ["没有任意文件路径读取"], effects="read_only"),
spec("plan_review", "review", "固定verifier独立检查设计、来源、预算、矩阵和条件功效", {"plan_ref": REF},
    output("review_ref", "ready_for_review", "finding_codes", "expert_calibrated"), ["当前方案"], ["复核与规划函数分离", "问题绑定方案哈希", "未验证现实假设保留"], next_tools=("plan_patch", "review_resolve", "claim_check_plan")),
spec("claim_check_plan", "claim", "检查方案能否条件性地检验指定结论；不判断结果是否支持", {"claim_ref": REF, "plan_ref": REF},
    output("alignment_ref", "claim_ref", "plan_ref", "checks", "can_test_conditionally", "claim_supported", "real_world_assumptions_verified", "note"),
    ["ClaimSpec和当前方案已登记"], ["对齐响应、单位、处理水平、主要对比和目标范围", "不能自动证明因果或全领域泛化"], next_tools=("plan_patch", "plan_freeze")),
spec("review_resolve", "review", "以新版本的实际复核结果关闭旧问题，不能自行标记已解决", {"old_review_ref": REF, "new_review_ref": REF},
    output("resolution_ref", "old_review_ref", "new_review_ref", "resolved", "still_blocked", "new_findings", "all_clear"),
    ["新复核属于旧方案的后代版本"], ["旧阻断消失才关闭", "新问题继续保留"], next_tools=("plan_patch", "plan_freeze")),
spec("plan_freeze", "control", "冻结当前方案、主要对比和复核身份，仅用于模拟", {"plan_ref": REF, "review_ref": REF, "alignment_ref": REF},
    output("freeze_ref", "real_execution_authorized"), ["同一版本的复核通过", "结论与计划对齐"], ["旧复核不能冻结新方案", "真实授权始终false"], next_tools=("workflow_compile",)),
spec("workflow_compile", "workflow", "为冻结方案生成带工具、依赖与每步验收的DAG", {"freeze_ref": REF}, output("workflow_ref"),
    ["已冻结模拟计划"], ["步骤包含检查、对账、模拟、分析、结论复核、下一步与报告"], next_tools=("workflow_verify",)),
spec("workflow_verify", "workflow", "验证步骤引用、工具可用性和DAG拓扑", {"workflow_ref": REF}, output("passed", "topological_order", "mode", "scientific_success"),
    ["结构化DAG"], ["无重复节点、缺失依赖或环", "不得包含未实现工具"], next_tools=("job_reconcile_mock",)),
spec("job_reconcile_mock", "job", "按冻结方案身份查询已有模拟作业", {"freeze_ref": REF}, output("job_ref", "status", "reused"),
    ["有效冻结引用"], ["已有作业必须匹配方案", "不得仅凭同名文件判定完成"], next_tools=("job_run_mock", "job_poll_mock")),
spec("job_run_mock", "job", "创建或复用本地合成观测作业，没有真实Darcy或CViT训练", {"freeze_ref": REF, "scenario": enum("benefit", "null", "harm")},
    output("job_ref", "status", "reused"), ["模拟冻结证书", "显式教学场景"], ["同一冻结身份最多一份作业", "已有作业不能换场景刷结果"], next_tools=("job_poll_mock",)),
spec("job_poll_mock", "job", "核对模拟作业状态和实验单位数", {"job_ref": REF}, output("job_ref", "status", "units", "real_training_performed"),
    ["登记作业"], ["明确模拟来源", "未启动真实GPU"], next_tools=("result_analyze",)),
spec("result_analyze", "analysis", "按冻结全模型和主要对比分析合成单位级观测，计算效应与t区间", {"job_ref": REF},
    output("analysis_ref", "job_ref", "freeze_ref", "plan_ref", "response", "primary_term", "effect", "interval", "confidence", "df", "model_assumptions_verified", "source_kind", "original_unit_count", "decision_rule", "posthoc_model_selection", "scientific_success"),
    ["单位完整且唯一", "模型满秩且有残差自由度", "只处理本库合成作业"], ["分析锁定主要对比", "不把网格点冒充训练重复", "报告假设仍未核验"], next_tools=("claim_assess",)),
spec("claim_assess", "claim", "判断已有合成证据是否条件支持方向与实际重要性", {"claim_ref": REF, "analysis_ref": REF},
    output("assessment_ref", "claim_ref", "analysis_ref", "status", "practical_benefit_supported", "interval", "evidence_scope", "real_scientific_claim_verified", "limitations"),
    ["分析与结论的计划、响应、对比、单位和范围匹配"], ["区分支持方向、相反方向和不确定", "不把未显著当等效", "不把模拟支持当真实结论"], next_tools=("loop_next_action", "report_build")),
spec("loop_next_action", "control", "根据证据选择报告或另行预注册后续研究", {"assessment_ref": REF},
    output("next_step", "automatic_retest", "change_success_threshold", "required_new_version_for_followup", "real_execution_authorized"),
    ["已有结论复核"], ["不自动加样本直到显著", "不修改原验收阈值"], next_tools=("report_build", "plan_patch")),
spec("report_build", "report", "把设计、模拟完成、证据范围与限制编为可追溯报告", {"assessment_ref": REF, "workflow_ref": REF},
    output("report_ref", "assessment_ref", "workflow_ref", "design_status", "execution_status", "statistical_evidence", "real_scientific_claim_verified", "next_action", "source"),
    ["工作流与证据引用同一冻结方案"], ["结论逐项引用证据", "保留负结果与不确定性"]),
]

PLANNED = [
    ("requirement_intake", "requirements", "将自然语言目标转换为ResearchRequest，保留未确认项", {"text": STRING}, "ResearchRequest", "contract_only"),
    ("question_next", "requirements", "根据缺项和冲突生成下一问题与选项", {"request_ref": REF, "review_ref": REF}, "Clarification", "contract_only"),
    ("context_read", "context", "工作区内显式选中文件读取，行号与哈希引用", {"relative_path": STRING, "max_lines": {"type": "integer", "minimum": 1, "maximum": 400}}, "FileEvidence", "existing_agent_entry"),
    ("literature_attach", "evidence", "登记文献版本、短摘录及其支持的假设；不自动信任内容", {"source_uri": STRING, "claim_ref": REF}, "SourceEvidence", "contract_only"),
    ("dataset_register", "data", "登记数据来源、版本、使用范围和许可", {"dataset_manifest": OBJECT}, "DatasetRef", "contract_only"),
    ("dataset_inspect", "data", "检查显式CSV的列、类型和缺失；已有G2入口只支持CSV", {"relative_path": STRING}, "DatasetProfile", "existing_agent_entry"),
    ("dataset_lineage_review", "data", "检查来源祖先、样本/场/任务家族与划分泄漏", {"dataset_ref": REF, "split_manifest_ref": REF}, "LineageReview", "contract_only"),
    ("unit_structure_review", "doe", "识别独立、配对、嵌套、聚类和伪重复", {"unit_declarations": OBJECT, "source_refs": array(REF)}, "UnitReview", "contract_only"),
    ("metric_define", "claim", "定义指标公式、聚合单位、方向和工程阈值", {"metric_definition": OBJECT}, "MetricSpec", "contract_only"),
    ("design_matrix_build", "doe", "生成设计矩阵、别名与可估计性诊断；现有只限三个DOE家族", {"plan_ref": REF}, "DesignMatrix", "existing_via_plan_review"),
    ("sample_size_compute", "doe", "依据目标差异、方差来源、alpha与功效/精度计算样本量", {"design_ref": REF, "effect_spec": OBJECT, "variance_source_ref": REF}, "SampleSizeReport", "contract_only"),
    ("randomization_generate", "doe", "生成按单位/区组约束的随机分配与执行顺序", {"design_ref": REF, "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647}}, "RandomizationManifest", "existing_via_plan_create"),
    ("missingness_review", "doe", "评估缺失、失败实验与预先约定的处理规则", {"plan_ref": REF, "outcome_manifest_ref": REF}, "MissingnessReview", "contract_only"),
    ("causal_identification_review", "review", "人工核对干预、随机化、干扰、混杂和因果范围", {"claim_ref": REF, "plan_ref": REF, "source_refs": array(REF)}, "CausalReview", "human_review_required"),
    ("environment_inspect", "execution", "读取已授权执行环境的依赖和硬件状态，不运行训练", {"adapter_id": STRING}, "EnvironmentProfile", "contract_only"),
    ("cost_estimate", "execution", "依据可追溯pilot估计时间、内存、GPU与失败风险", {"plan_ref": REF, "pilot_evidence_ref": REF}, "ResourceEstimate", "contract_only"),
    ("human_approval_record", "control", "宿主记录真实操作者对确定版本与预算的授权，模型不能自批", {"plan_ref": REF, "operator_record": OBJECT}, "ApprovalCertificate", "human_review_required"),
    ("darcy_fit_real", "execution", "真实Darcy适配器拟合；本库禁用，已有数值入口另行确认", {"freeze_ref": REF, "approval_ref": REF, "dataset_ref": REF}, "RealJobRef", "disabled_real_execution"),
    ("cvit_train_real", "execution", "配置化真实CViT作业；本库与当前项目研究模式禁用", {"freeze_ref": REF, "approval_ref": REF, "dataset_ref": REF}, "RealJobRef", "disabled_real_execution"),
    ("job_cancel_real", "execution", "按已登记真实作业ID取消，保留部分结果与成本", {"job_ref": REF, "approval_ref": REF}, "JobCancellation", "disabled_real_execution"),
    ("sealed_test_evaluate_real", "analysis", "选择冻结后一次读取封存测试并保存预测和评价来源", {"freeze_ref": REF, "selected_model_ref": REF, "approval_ref": REF}, "SealedEvaluation", "disabled_real_execution"),
    ("result_diagnostics", "analysis", "检查残差、异常值、异方差和相关性，不凭小样本检验确认假设", {"analysis_ref": REF, "unit_manifest_ref": REF}, "Diagnostics", "contract_only"),
    ("multiplicity_plan", "analysis", "预先定义多重比较家族和校正规则；不事后挑显著项", {"claim_refs": array(REF, 1, 100), "alpha": {"type": "number", "minimum": .001, "maximum": .2}}, "MultiplicitySpec", "contract_only"),
    ("equivalence_noninferiority_review", "claim", "使用预设界值和专用检验审查等效或非劣；不复用普通不显著结论", {"claim_ref": REF, "margin_source_ref": REF}, "SpecialClaimReview", "contract_only"),
    ("out_of_distribution_evaluate", "validation", "以独立来源/机制/物理分布留出检验泛化范围", {"freeze_ref": REF, "holdout_manifest_ref": REF}, "GeneralizationReport", "contract_only"),
]
for name, group, purpose, inputs, kind, mode in PLANNED:
    CATALOG.append(spec(name, group, purpose, inputs, obj({"artifact_ref": REF, "artifact_type": {"const": kind}, "status": STRING}),
        ["适配器、数据边界、核验规则或人工权限尚需实现"], ["不可由工具目录存在推断功能已接入"], mode=mode,
        effects="none_in_this_library", failures=("Not implemented: fail closed; do not simulate a successful real action",)))


def validate(value, schema, path="$"):
    kind = schema.get("type")
    kinds = kind if type(kind) is list else [kind] if kind else []
    tests = {"object": lambda v: type(v) is dict, "array": lambda v: type(v) is list,
        "string": lambda v: type(v) is str, "number": lambda v: type(v) in (int, float) and math.isfinite(v),
        "integer": lambda v: type(v) is int, "boolean": lambda v: type(v) is bool, "null": lambda v: v is None}
    if kinds and not any(tests[k](value) for k in kinds):
        raise ValueError(path+": wrong type")
    if "const" in schema and value != schema["const"] or "enum" in schema and value not in schema["enum"]:
        raise ValueError(path+": unsupported value")
    if type(value) is dict and schema.get("properties") is not None:
        props = schema["properties"]
        if set(schema.get("required", []))-set(value) or schema.get("additionalProperties") is False and set(value)-set(props):
            raise ValueError(path+": missing/extra keys")
        for key in set(value)&set(props):
            validate(value[key], props[key], path+"/"+key)
    elif type(value) is list and kind == "array":
        if not schema["minItems"] <= len(value) <= schema["maxItems"]:
            raise ValueError(path+": array length")
        for i, item in enumerate(value):
            validate(item, schema["items"], path+"/"+str(i))
    elif type(value) is str:
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1000000) or "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise ValueError(path+": string shape")
    elif type(value) in (int, float):
        if not math.isfinite(value) or value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise ValueError(path+": numeric bounds")
