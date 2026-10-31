"""Pure scientific planning contracts, review checks and researcher-facing maps.

Planning readiness means a declaration is reviewable, never that a scientific
assumption has been verified or a real experiment has been authorized.
"""
from copy import deepcopy
import re

VERSION = "research_blueprint_v1"


def _field(label, prompt, rationale, options=(), required=True):
    return {"label": label, "prompt": prompt, "rationale": rationale,
            "options": [{"value": value, "label": text} for value, text in options], "required": required}


FIELDS = {
    "research_question": _field("研究问题", "你想弄清什么，结果将帮助你做什么决定？", "先确定问题，再选择工具，避免把训练一个模型当成研究结论。"),
    "objective_type": _field("研究目的", "本轮是在比较、预测、解释因果、探索，还是复现？", "不同目的需要不同证据，预测准确不能自动证明因果。", (("comparison", "比较方案或处理"), ("prediction", "预测未见样本"), ("causal", "估计因果效应"), ("exploration", "探索问题或机制"), ("replication", "复现既有结论"))),
    "hypothesis": _field("待检验命题", "请给出可能被否定的命题；探索阶段也可明确不预设方向。", "命题、能否检验、证据是否支持是三个不同判断。", required=False),
    "scope": _field("研究边界", "结论只适用于哪些对象、数据、条件和时间范围？", "把对象范围写清楚，避免从一个数据集推广到所有场景。"),
    "exclusions": _field("本轮不回答的问题", "本轮明确不研究什么，不准备声称什么？", "排除项帮助人保留对项目边界的控制。"),
    "experimental_unit": _field("实验与推断单位", "一次独立分配或观察是什么？哪些测量来自同一对象？", "数据行、网格点和随机种子不能自动当作独立重复。"),
    "factors": _field("因素与对比", "改变哪些因素和水平，主要比较谁与谁？", "先锁定主要对比，避免看到结果后改变问题。", required=False),
    "design": _field("设计结构", "单位之间是独立、配对、区组、多因素，还是观察性研究？", "设计要与单位关系匹配；工具不支持的设计可以形成待人工实现的计划。", (("crd", "独立随机分配"), ("paired", "同一单位配对"), ("rcbd", "区组设计"), ("factorial", "多因素设计"), ("observational", "观察性设计"), ("prediction", "预测评估设计"), ("custom", "另行说明的设计"))),
    "outcomes": _field("主要响应与测量", "主要指标是什么、哪个方向更好、怎样在实验单位上汇总？", "训练损失、测试指标、统计显著和实际重要性不能混用。"),
    "baseline": _field("基线与公平比较", "与哪个基线比较，如何保持数据、预算和评估条件公平？", "比较结果需要同口径基线，而不只是单个漂亮数字。", required=False),
    "data_source": _field("数据与证据来源", "使用已有数据、公开来源、自采数据还是合成数据？给出可追踪标识。", "用户声明与实测证据分开记录，不凭空补造先导数据。"),
    "sampling": _field("样本与重复依据", "样本量、重复数及其依据是什么？没有方差依据时是否先做先导？", "可以先规划先导阶段，不能用模板默认方差保证功效。"),
    "randomization": _field("分配与偏差控制", "怎样随机分配或控制顺序、区组和混杂；不随机时请说明原因与替代方法。", "随机化种子不是实际分配过程的证据。", required=False),
    "analysis": _field("分析与不确定性", "估计什么量、用什么方法，并怎样报告区间或不确定性？", "按预先声明的模型分析，不反复改方法直到显著。"),
    "acceptance": _field("验收和停止规则", "怎样判定完成或不支持命题？请给出阈值、阴性处理和停止条件。", "交付完成与得到预期结论分开，阴性结果也必须如实报告。"),
    "resources": _field("资源边界", "可用多少时间、计算、实验次数或经费？哪些上限不可突破？", "预算是计划前提，不能由 Agent 为过检而擅自提高。"),
    "risks": _field("风险与未决条件", "哪些假设最可能不成立？出现什么情况要交还人类判断？", "把未知列出来，防止计划完整的外观掩盖证据缺口。"),
    "reproducibility": _field("复现记录", "怎样记录数据版本、代码配置、随机种子、偏离和结果？", "保留做了什么、为什么改、哪些结果无法复现的轨迹。"),
    "human_roles": _field("人类职责", "谁确认边界、复核方案、执行实验，并对结论负责？", "Agent 提供建议和检查，人类保留方法选择与结论责任。"),
    "deliverable": _field("交付物", "最后交付什么：方案、脚本、表格、报告或可复现实验记录？", "让项目步骤最终对应可检查的产物。"),
}

_BASE_REQUIRED = tuple(key for key, spec in FIELDS.items() if spec["required"])
_PLACEHOLDERS = {"待定", "不知道", "未知", "不清楚", "随便", "都可以", "默认", "tbd", "unknown", "n/a", "na", "none", "无"}
_GENERIC = {"做个实验", "设计实验", "比较一下", "提高效果", "合理设计", "严谨分析", "结果更好", "统计分析", "合理阈值", "合理样本量", "正常执行", "科研计划", "实验方案"}


def non_actionable(value):
    clean = value.casefold().strip("。.!！ ")
    return clean in _PLACEHOLDERS | _GENERIC or (len(value) < 160 and bool(re.search(
        r'待澄清|尚未给出|未给出具体|尚未提供|尚未确定|待明确|用户希望.{0,30}澄清|先澄清适用范围|仅为占位', value)))


def _text(state, key):
    if key in state.get('unknown',[]):return ''
    item = state.get("facts", {}).get(key, {})
    return item.get("value", "").strip() if isinstance(item, dict) and isinstance(item.get("value"), str) else ""


def _has(text, pattern):
    return bool(re.search(pattern, text, re.I))


def _enum(value, options):
    clean = value.strip().lower()
    for candidate in options:
        if clean == candidate or clean.startswith(candidate+":") or clean.startswith(candidate+"："):
            return candidate
    aliases = {"比较": "comparison", "预测": "prediction", "因果": "causal", "探索": "exploration", "复现": "replication",
               "独立随机": "crd", "完全随机": "crd", "配对": "paired", "区组": "rcbd", "多因素": "factorial", "因子": "factorial", "观察性": "observational", "自定义": "custom"}
    for alias, candidate in aliases.items():
        if candidate in options and (clean == alias or clean.startswith(alias+"：") or clean.startswith(alias+":")):
            return candidate
    return None


def required_fields(state):
    """Dynamic requirements; exploration need not invent treatments or causality."""
    objective = _enum(_text(state, "objective_type"), {"comparison", "prediction", "causal", "exploration", "replication"})
    design = _enum(_text(state, "design"), {"crd", "paired", "rcbd", "factorial", "observational", "prediction", "custom"})
    needed = list(_BASE_REQUIRED)
    if objective in {"comparison", "prediction", "causal", "replication"}: needed.append("baseline")
    if objective in {"comparison", "causal", "replication"}: needed += ["hypothesis", "factors"]
    if design in {"crd", "paired", "rcbd", "factorial"} or objective in {"causal", "replication"}: needed.append("randomization")
    return [key for key in FIELDS if key in needed]


def review(state):
    """Check declarations and semantic completeness without pretending to validate science."""
    checks = []
    def add(field, code, ok, detail, needs_review=False):
        checks.append({"field": field, "code": code, "status": "needs_review" if needs_review else "passed" if ok else "blocked", "detail": detail})
    required = required_fields(state)
    facts = state.get("facts", {})
    unknown = set(state.get("unknown", []))
    conflicts = state.get("conflicts", {})
    for field in required:
        value = _text(state, field)
        if not value:
            add(field, "missing_declaration", False, FIELDS[field]["prompt"])
        elif non_actionable(value):
            add(field, "non_actionable_declaration", False, "当前只有占位或笼统描述；"+FIELDS[field]["prompt"])
        elif field not in unknown and field not in conflicts:
            add(field, "declaration_present", True, "已记录用户声明；这不等于外部事实验证。")
    for field in FIELDS:
        fact = facts.get(field)
        if isinstance(fact, dict) and fact.get("status") == "proposed":
            add(field, "unconfirmed_proposal", False, "这项仍是待用户确认的建议，不能作为已知实验事实。")
        if field in conflicts:
            add(field, "unresolved_conflict", False, "存在相互冲突的版本，请明确保留哪一项及修订理由。")
        if field in unknown:
            add(field, "explicit_unknown", False, "用户明确尚不知道；应先规划获取证据的步骤。", needs_review=field not in required)
        if field in state.get('stale',{}):
            add(field,'dependent_declaration_stale',False,state['stale'][field])
    objective = _enum(_text(state, "objective_type"), {"comparison", "prediction", "causal", "exploration", "replication"})
    design = _enum(_text(state, "design"), {"crd", "paired", "rcbd", "factorial", "observational", "prediction", "custom"})
    if _text(state, "objective_type"): add("objective_type", "objective_classified", bool(objective), "需要明确比较、预测、因果、探索或复现目的。")
    if _text(state, "design"): add("design", "design_classified", bool(design), "选择一个设计家族；自定义设计需由人类进一步复核。")
    if design == "custom": add("design", "custom_external_review", True, "自定义设计仅形成计划，当前工具不能保证自动复核或执行。", needs_review=True)
    unit = _text(state, "experimental_unit")
    if unit and _has(unit, r"seed|种子") and not _has(unit, r"独立|independen|分配|allocation|对象|单位"):
        add("experimental_unit", "seed_is_not_unit_evidence", False, "种子本身不能证明独立性；请说明一次分配/观察及共享数据关系。")
    if design == "crd" and _has(unit, r"同一单位.{0,8}重复|重复测量|paired units|repeated measurements"):
        add("design", "unit_design_mismatch", False, "声明的重复测量关系与独立设计不一致，应考虑配对、区组或另行建模。")
    if design == "paired" and unit:
        add("experimental_unit", "paired_matching_basis", _has(unit, r"同一|配对|匹配|重复测量|within|paired|matched"), "配对分析需要声明单位内重复或匹配关系，不能仅因样本量相同就配对。")
    if design == "rcbd":
        block_basis = " ".join(_text(state, f) for f in ("experimental_unit", "randomization", "analysis"))
        add("design", "blocking_basis", _has(block_basis, r"区组|block|匹配"), "说明区组依据及区组内分配/分析，不能只选择区组设计名称。")
    outcome = _text(state, "outcomes")
    if outcome:
        add("outcomes", "outcome_direction", _has(outcome, r"lower|higher|smaller|larger|越低|越高|更低|更高|方向|降低|提高|减少|增加|双侧|无方向|探索"), "明确主要响应及方向，或明确无预设方向的探索性分析。")
        add("outcomes", "unit_aggregation", _has(outcome, r"均值|中位|比例|分位|每次|每个|单位|汇总|mean|median|proportion|aggregate|per.unit"), "说明怎样按实验/推断单位汇总测量，不能用大量技术重复扩大样本量。")
    analysis = _text(state, "analysis")
    if analysis and objective in {"comparison", "causal", "replication"}:
        add("analysis", "estimand_declared", _has(analysis, r"效应|对比|差|contrast|effect|estimand|估计"), "写清估计对象或主要对比，不能只写运行统计检验。")
        add("analysis", "uncertainty_declared", _has(analysis, r"区间|置信|不确定|标准误|bootstrap|credible|posterior|\bci\b|interval|后验"), "声明置信区间或其他不确定性表达，避免只报告显著性。")
    if objective == "prediction":
        split = " ".join(_text(state, f) for f in ("data_source", "sampling", "analysis"))
        add("data_source", "prediction_holdout", _has(split, r"测试|test|留出|holdout") and _has(split, r"验证|validation|嵌套|nested"), "声明训练、验证与最终测试的职责，不能用测试结果反复选模型。")
        add("data_source", "prediction_leakage", _has(split, r"泄漏|leak|隔离|不重叠|group.{0,8}split|按对象|按时间|按区组"), "说明按对象、区组或时间隔离数据及防泄漏办法。")
        add("analysis", "prediction_uncertainty", _has(analysis, r"区间|不确定|bootstrap|重复|误差|interval|uncertainty"), "预测比较也要说明误差或不确定性，单个最佳分数不够。")
    if objective == "causal" and design in {"observational", "custom"}:
        identification = " ".join(_text(state, f) for f in ("analysis", "randomization", "risks"))
        add("analysis", "causal_identification", _has(identification, r"混杂|识别|工具变量|断点|倾向|交换性|可忽略|confound|identif|instrument|propensity"), "观察性因果结论需要明确识别假设、混杂与替代解释；相关或预测不能替代。")
        add("analysis", "causal_assumptions_external", True, "识别假设仍需领域专家复核，当前声明不是因果识别证明。", needs_review=True)
    allocation = _text(state, "randomization")
    if allocation and design in {"crd", "paired", "rcbd", "factorial"}:
        add("randomization", "allocation_process", _has(allocation, r"分配|顺序|排列|抽签|allocation|order|assign|shuffle|区组|配对"), "声明实际分配或顺序过程，不能只提供随机种子。")
        if design in {"crd", "rcbd"} and _has(allocation, r"不随机|未随机|没有随机|无法随机|non.random|not random|no random"):
            add("randomization", "randomized_design_conflict", False, "随机设计与明确未随机分配相冲突；应修订设计或说明实际随机过程。")
    sampling = _text(state, "sampling")
    if sampling and _has(sampling, r"功效|power"):
        has_basis = (_has(sampling,r'方差|sigma|标准差|variance') and _has(sampling,r'效应|effect|差值')
            and _has(sampling,r'每组|区组|布局|重复数|replicate|per.group|layout')
            and _has(sampling,r'来源|先导|pilot|依据|source'))
        planned_pilot = _has(sampling, r"先做|先进行|待先导|先导后|pilot first|after.*pilot|探索|不保证|不宣称")
        add("sampling", "power_basis", has_basis or planned_pilot, "功效需要效应、方差和布局依据；缺少时先安排先导，不能默认保证功效。")
        add("sampling", "power_external_review", True, "本计划不自动计算或证明功效；参数来源和计算须单独复核。", needs_review=True)
    acceptance = _text(state, "acceptance")
    if acceptance:
        measurable = _has(acceptance, r"\d|每项|逐项|全部|覆盖|完整记录|可复现|coverage|complete|reproduc")
        add("acceptance", "measurable_acceptance", measurable, "验收应有可测阈值或可逐项核对的产物，不只写结果更好。")
        add("acceptance", "negative_outcomes", _has(acceptance, r"阴性|不显著|未显著|不支持|未支持|未达到|不达标|零结果|负结果|不确定|无效|negative|null|inconclusive"), "明确阴性、不确定或反向结果也应如实报告，不能继续试到显著。")
        add("acceptance", "stopping_rule", _has(" ".join(_text(state, f) for f in ("acceptance", "resources", "risks")), r"停止|中止|停机|终止|耗尽|上限|stop|abort|limit"), "预先声明预算、信息不足或失败时的停止/升级条件。")
        if objective in {"comparison", "causal", "replication"} and _has(acceptance, r"p\s*[<≤=]|显著"):
            add("acceptance", "practical_vs_statistical", _has(acceptance, r"实际|效应|幅度|最小|margin|effect|practical"), "统计显著与实际重要性分开，不能只用 p 值定义科学成功。")
    resources = _text(state, "resources")
    if resources:
        add("resources", "resource_bound", _has(resources, r"\d|一|二|三|四|五|六|七|八|九|十|本周|本月|截止|免费|不超过|limit|deadline"), "声明可核对的资源数量、期限或硬上限。")
    roles = _text(state, "human_roles")
    if roles:
        add("human_roles", "human_accountability", _has(roles, r"研究者|学生|导师|实验员|我|团队|人工|人类|用户|负责人|课题组|human|researcher|operator") and _has(roles, r"确认|负责|复核|审批|决定|签署|review|approve|responsib"), "明确由谁确认边界、复核方法和批准结论，不把责任隐含交给模型。")
    reproducibility = _text(state, "reproducibility")
    if reproducibility:
        groups = [r"版本|git|hash|commit", r"种子|seed|随机", r"数据|data|来源|source", r"配置|日志|记录|config|log"]
        add("reproducibility", "reproducibility_records", sum(_has(reproducibility, p) for p in groups) >= 2, "至少明确数据/代码版本、种子、配置或日志中的两类复现记录。")
    for field,row in state.get('pending_revisions',{}).items():
        add(field,'unapplied_revision',False,row['reason'])
    from .synthesis import projection
    if projection(state)['status']=='stale':
        add('design','synthesized_plan_stale',False,'实验初稿依据已变更，请用 /plan synthesize 更新后再确认。')
    declarations_complete = not any(row['status']=='blocked' for row in checks)
    from .method_review import risks
    method_risks=risks(state)
    checks.extend(method_risks)
    blockers = [deepcopy(row) for row in checks if row["status"] == "blocked"]
    return {"ready": not blockers, "checks": checks, "blockers": blockers, "required_fields": required,
            "declarations_complete":declarations_complete,"method_risks":method_risks,
            "method_review_status":"risks_detected" if method_risks else "pending_human_review",
            "scope": "planning_only", "execution_authorized": False, "scientific_claim_verified": False,
            "readiness_meaning": "用户声明已足够形成待人类复核的计划；不表示假设、数据、功效或结论已被验证。"}


def build_blueprint(state):
    """Return a dependency DAG, evidence obligations and capability boundaries."""
    assessment = review(state)
    facts = {key: _text(state, key) for key in FIELDS if _text(state, key)}
    nodes = []
    def node(identity, purpose, dependencies, inputs, outputs, acceptance, owner, capability, tools=()):
        nodes.append({"id": identity, "purpose": purpose, "dependencies": list(dependencies), "inputs": list(inputs),
            "outputs": list(outputs), "acceptance": acceptance, "owner": owner,
            "capability": capability, "suggested_tools": list(tools), "executed": False})
    node("boundaries", "明确要回答的问题和不能外推的边界", (), ("research_question", "objective_type", "scope", "exclusions"),
         ("问题与边界契约",), "研究者用自己的话确认问题、范围和排除项；模型建议保持待确认身份。", "研究者与Agent协作", "implemented")
    node("evidence_inventory", "区分已知声明、实际证据和未决信息", ("boundaries",), ("data_source", "experimental_unit", "risks"),
         ("证据来源清单", "未决问题清单"), "每项关键事实有来源或明确未知；真实单位独立性与测量质量需外部核实。", "研究者提供与核实，Agent整理", "manual")
    node("design", "选择能检验命题的设计并说明合理替代方案", ("evidence_inventory",), ("hypothesis", "factors", "design", "baseline", "sampling", "randomization"),
         ("实验分配与分析单位说明", "样本/先导依据", "方案候选与取舍"), "对比可估计；单位、重复、区组和随机化关系明确；未知功效条件不能被默认值替代。", "研究者选择，方法专家复核", "manual")
    node("acceptance", "预先锁定分析、验收和停止规则", ("design",), ("outcomes", "analysis", "acceptance", "resources"),
         ("主要指标与对比", "分析及不确定性规则", "验收/停止检查表"), "区分能否检验命题与证据是否支持；预设阴性和不确定结果处理，禁止按结果改阈值。", "研究者确认，Agent检查声明完整性", "implemented")
    node("human_review", "在执行前复核假设、可行性与责任", ("acceptance",), ("human_roles", "risks", "reproducibility"),
         ("人工复核记录", "批准版本或修订理由"), "逐项检查来源、统计/领域假设、资源及工具能力；修订关键事实后原确认失效。", "指定的人类复核者", "manual")
    node("preregister", "冻结当前计划及其验收规则", ("human_review",), ("完整计划", "人工确认记录"),
         ("带版本和来源的计划快照",), "确认绑定当前版本，计划变更重新复核；计划确认不等于真实工具执行授权。", "研究者确认，宿主保存", "implemented")
    node("mock_rehearsal", "可选：演练受支持工具闭环，不制造实测证据", ("preregister",), ("明确受支持的设计映射",),
         ("模拟工具轨迹", "能力缺口清单"), "仅显式进入详细工具库后运行；模拟输出明确标记，不能当作真实实验结论。", "Agent在宿主约束内", "mock", ("plan_review", "claim_check_plan", "workflow_verify", "job_run_mock"))
    node("execute", "按锁定计划采集数据或执行研究步骤", ("preregister",), ("人工授权", "真实环境与数据", "冻结计划"),
         ("原始观测", "实际分配与偏离记录", "失败和资源记录"), "真实任务由人类或另行接入的受限执行器完成；不能因已有工具契约而宣称已经执行。", "人类研究者/单独授权的执行器", "manual")
    node("analyze", "依据预先声明的方法分析结果并检查偏离", ("execute",), ("真实观测与版本", "冻结分析规则"),
         ("估计量与不确定性", "诊断和偏离说明"), "不把技术重复当独立样本；不反复选方法直到显著；自动分析须先核对具体工具支持范围。", "研究者负责，Agent可辅助解释", "manual")
    node("claim_review", "判断证据支持什么，以及仍不能判断什么", ("analyze",), ("命题", "分析输出", "假设与外推限制"),
         ("支持/不支持/不确定的结论", "限制与替代解释"), "设计可检验不等于结果支持；阴性、反向及不确定结果同样记录，因果与泛化不超出证据。", "人类研究者作最终判断", "manual")
    node("report", "交付可追踪报告并选择下一步", ("claim_review",), ("deliverable", "reproducibility", "全程决策与偏离记录"),
         ("研究报告与复现清单", "下一步或停止理由"), "交付包含边界、设计选择、关键证据、局限、负结果和人类职责；新问题另开版本，不事后重写原验收。", "研究者签署，Agent整理", "manual")
    from .synthesis import projection
    synthesis=projection(state)
    result={"version": VERSION, "plan_id": state.get("id"), "revision": state.get("revision", 0),
        "evidence": deepcopy(state.get("evidence", [])), "evidence_actions": deepcopy(state.get("evidence_actions", {})),
        "status": "reviewable_plan" if assessment["ready"] else "draft_with_open_questions", "facts": facts,
        "fact_sources": deepcopy(state.get("facts", {})), "nodes": nodes, "review": assessment,
        "risks": [_text(state, "risks")] if _text(state, "risks") else ["风险尚未声明"],
        "out_of_scope": [_text(state, "exclusions")] if _text(state, "exclusions") else ["外推边界尚未声明"],
        "scientific_claim_verified": False, "execution_authorized": False,
        "capability_legend": {"implemented": "当前Harness可保存、检查或展示的规划操作，不代表步骤已执行", "mock": "受支持详细工具库的显式模拟演练", "manual": "需人类或另行授权/接入工具完成"}}
    if state.get('plan_synthesis'):
        result.update(plan_synthesis=synthesis,experiment_steps=deepcopy(synthesis['content']['steps']) if synthesis['status']=='current' else [])
    return result


def render_map(state):
    """A compact awareness view: purpose, boundaries, evidence gaps, choices, next step."""
    assessment = review(state)
    from .method_review import notice
    lines = [f"研究地图 · 第 {state.get('revision', 0)} 版", notice(assessment), ""]
    for key in ("research_question", "objective_type", "scope", "exclusions", "experimental_unit", "design", "outcomes", "acceptance"):
        value = _text(state, key)
        fact = state.get("facts", {}).get(key, {})
        tag = "（待确认建议）" if fact.get("status") == "proposed" else ""
        lines.append(f"- {FIELDS[key]['label']}：{value or '尚未明确'}{tag}")
    lines += ["", "我们现在能做：继续澄清并形成待人类复核的计划；真实实验尚未执行。"]
    if state.get('unknown'):
        lines.append('明确未知：'+'、'.join(FIELDS[f]['label'] for f in state['unknown']))
    for field,row in state.get('evidence_actions',{}).items():
        lines.append('拟议获取步骤（未执行）：'+FIELDS[field]['label']+' · '+row['text'])
    if state.get('evidence'):
        from .evidence import citation
        lines += ['已选论文片段（未经事实验证）：']+[citation(row) for row in state['evidence']]
    if assessment["blockers"]:
        unique = []
        for row in assessment["blockers"]:
            if row["field"] not in [r["field"] for r in unique]: unique.append(row)
        lines.append("下一步优先核实："+"；".join(FIELDS[r["field"]]["label"]+"："+r["detail"] for r in unique[:3]))
    else:
        lines.append("下一步：研究者核对这份计划、依据和能力缺口，决定是否确认当前版本。")
    if state.get("decisions"):
        lines.append("已有决策记录："+str(len(state["decisions"]))+" 条；修订事实后需重新复核。")
    return "\n".join(lines)


def export_markdown(state):
    plan = build_blueprint(state)
    from .method_review import notice
    lines = ["# 科研任务计划", "", f"版本：{state.get('revision', 0)}；状态：{plan['status']}。", "",
        "本文件是待复核的规划契约，不是实验完成证明，也不授权真实工具执行。", "",notice(plan['review']),""]
    if state.get('plan_synthesis'):
        from .delivery import render_design
        lines+=['## 实验设计初稿','',render_design(state),'']
    lines += ['## 已声明的边界与设计','']
    for key, spec in FIELDS.items():
        fact = state.get("facts", {}).get(key, {})
        value = _text(state, key) or "尚未明确"
        status = fact.get("status", "missing")
        lines += [f"### {spec['label']}", "", value, "", f"来源状态：{status}；原文：{fact.get('quote') or '未提供'}", ""]
    lines += ['## 显式选择的论文证据', '']
    if state.get('evidence'):
        from .evidence import citation
        for row in state['evidence']:
            lines += [citation(row), '', '选定时的原文快照，未经科学事实验证；workspace_id='+row['workspace_id'], '',
                      '\n'.join('> '+line for line in row['text'].splitlines()), '']
            if row.get('interpretation'):
                from .paper_reading import render as render_reading
                lines += [render_reading(row),'']
    else:lines += ['尚未选择；不从论文名字或IDE标签推断内容。', '']
    for field,row in state.get('evidence_actions',{}).items():
        lines += ['拟议获取步骤（尚未执行）：'+FIELDS[field]['label']+' · '+row['text'], '']
    lines += ["## 步骤、依赖与验收", ""]
    for node in plan["nodes"]:
        lines += [f"### {node['id']}：{node['purpose']}", "", "依赖："+("、".join(node["dependencies"]) or "无"),
            "", "输入："+"、".join(node["inputs"]), "", "输出："+"、".join(node["outputs"]),
            "", "验收："+node["acceptance"], "", "责任："+node["owner"], "", "能力："+node["capability"]+"；尚未执行。", ""]
    lines += ["## 未决问题与复核提醒", ""]
    issues = [r for r in plan["review"]["checks"] if r["status"] != "passed"]
    lines += [f"- [{r['status']}] {FIELDS[r['field']]['label']}：{r['detail']}" for r in issues] or ["- 当前声明可供人类复核；外部事实与科学假设仍未被本计划自动验证。"]
    lines += ["", "## 决策与修订记录", ""]
    for decision in state.get("decisions", []):
        if isinstance(decision, dict):
            lines.append("- "+str(decision.get("reason") or decision.get("summary") or decision))
        else: lines.append("- "+str(decision))
    if not state.get("decisions"): lines.append("- 尚无决策记录。")
    lines += ["", "## 人类认知检查", "", "- 我们要回答什么，不准备声称什么？", "- 为什么选择当前设计，合理替代方案是什么？",
        "- 什么结果会改变判断，哪些未知仍未解决？", "- 谁负责执行、核实证据及批准最终结论？", "- 何时停止、修订或交还人工判断？", ""]
    return "\n".join(lines)
