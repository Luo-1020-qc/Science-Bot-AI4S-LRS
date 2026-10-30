"""Scientific-plan contract tests, independent of API or real experiment tools."""
from copy import deepcopy
import unittest

from rut_science.science_bot.general.planning.blueprint import FIELDS, build_blueprint, review, render_map, export_markdown


def complete_state():
    values = {
        "research_question": "在声明的数据实现上比较 ridge 与均值预测器的误差，决定是否值得后续验证。",
        "objective_type": "comparison", "hypothesis": "候选减基线的 relative_l2 均值差至少下降0.01。",
        "scope": "仅限合成 source_A 的独立数据实现和预先指定预算。", "exclusions": "不宣称真实PDE泛化或因果机制。",
        "experimental_unit": "每个独立数据实现作为一个处理分配和推断单位，不以网格点作为重复。",
        "factors": "predictor 两个水平 mean_field 与 ridge_field；主要比较候选减基线。", "design": "crd",
        "outcomes": "主要指标 relative_l2，lower 越低越好，按每个独立单位的均值汇总。",
        "baseline": "mean_field，使用相同数据版本、预算和评价规则。", "data_source": "合成数据 mock://source_A；没有真实先导观测。",
        "sampling": "每组24个独立实验单位，固定样本探索，不宣称功效保证。",
        "randomization": "对独立单位抽签分配，记录实际分配顺序与 seed=42。",
        "analysis": "估计候选减基线的均值差，使用 Welch 方法和95%置信区间。",
        "acceptance": "实际下降阈值0.01；报告效应和区间；阴性及不确定结果也交付；资源耗尽停止。",
        "resources": "最多48次处理应用，4小时上限。", "risks": "独立性和模型假设仍需研究者核实，异常时人工停止复核。",
        "reproducibility": "保存数据hash、代码git版本、seed、配置日志与偏离记录。",
        "human_roles": "学生负责执行；研究者确认边界和设计；导师复核并批准结论。", "deliverable": "可复现报告、估计量区间表和局限说明。",
    }
    return {"id": "fixture", "revision": 2, "facts": {key: {"value": value, "quote": value, "status": "declared", "turn": 1} for key, value in values.items()},
            "unknown": [], "conflicts": {}, "decisions": [], "approval": None}


class PlanningBlueprintTests(unittest.TestCase):
    def test_complete_declared_plan_ready_but_never_execution_authorized(self):
        state = complete_state(); result = review(state)
        self.assertTrue(result["ready"], result["blockers"])
        self.assertEqual(result["scope"], "planning_only")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["scientific_claim_verified"])

    def test_missing_and_generic_facts_block_with_field_specific_questions(self):
        state = complete_state(); del state["facts"]["scope"]
        state["facts"]["research_question"]["value"] = "做个实验"
        result = review(state)
        self.assertFalse(result["ready"])
        self.assertTrue(any(r["field"] == "scope" and r["code"] == "missing_declaration" for r in result["blockers"]))
        self.assertTrue(any(r["code"] == "non_actionable_declaration" for r in result["blockers"]))

    def test_proposed_fact_is_not_promoted_by_reviewer(self):
        state = complete_state(); state["facts"]["sampling"]["status"] = "proposed"
        before = deepcopy(state)
        self.assertTrue(any(r["code"] == "unconfirmed_proposal" for r in review(state)["blockers"]))
        self.assertEqual(state, before)

    def test_conflicts_and_unknown_block_even_if_value_still_present(self):
        state = complete_state(); state["unknown"] = ["experimental_unit"]
        state["conflicts"]["resources"] = ["48 runs", "100 runs"]
        codes = {r["code"] for r in review(state)["blockers"]}
        self.assertIn("explicit_unknown", codes); self.assertIn("unresolved_conflict", codes)

    def test_exploration_does_not_invent_interventions_or_hypotheses(self):
        state = complete_state(); state["facts"]["objective_type"]["value"] = "exploration"
        state["facts"]["design"]["value"] = "observational"
        for key in ("hypothesis", "factors", "baseline", "randomization"): del state["facts"][key]
        state["unknown"] = ["hypothesis"]
        result = review(state)
        self.assertTrue(result["ready"], result["blockers"])
        self.assertTrue(any(r["field"] == "hypothesis" and r["status"] == "needs_review" for r in result["checks"]))

    def test_prediction_requires_holdout_and_leakage_controls(self):
        state = complete_state(); state["facts"]["objective_type"]["value"] = "prediction"
        state["facts"]["design"]["value"] = "prediction"
        result = review(state)
        self.assertTrue({"prediction_holdout", "prediction_leakage"} <= {r["code"] for r in result["blockers"]})
        state["facts"]["data_source"]["value"] = "按独立对象隔离 train/validation/test；测试只用一次，防止泄漏。"
        self.assertTrue(review(state)["ready"], review(state)["blockers"])

    def test_observational_causal_plan_needs_identification(self):
        state = complete_state(); state["facts"]["objective_type"]["value"] = "causal"
        state["facts"]["design"]["value"] = "observational"
        self.assertTrue(any(r["code"] == "causal_identification" for r in review(state)["blockers"]))
        state["facts"]["analysis"]["value"] += "；识别假设为条件可交换性，控制预先声明混杂，专家核实。"
        self.assertTrue(review(state)["ready"], review(state)["blockers"])

    def test_power_without_basis_does_not_pass(self):
        state = complete_state(); state["facts"]["sampling"]["value"] = "每组30，保证80%功效。"
        self.assertTrue(any(r["code"] == "power_basis" for r in review(state)["blockers"]))
        state["facts"]["sampling"]["value"] = "先做先导，先导后估计方差再决定重复数；当前不宣称功效。"
        self.assertFalse(any(r["code"] == "power_basis" for r in review(state)["blockers"]))

    def test_merely_saying_pilot_or_effect_does_not_establish_power_basis(self):
        state=complete_state();state['facts']['sampling']['value']='每组30，根据先导效应保证功效80%'
        self.assertTrue(any(r['code']=='power_basis' for r in review(state)['blockers']))

    def test_seed_alone_is_not_unit_or_allocation(self):
        state = complete_state(); state["facts"]["experimental_unit"]["value"] = "seed=42"
        state["facts"]["randomization"]["value"] = "seed=42"
        codes = {r["code"] for r in review(state)["blockers"]}
        self.assertIn("seed_is_not_unit_evidence", codes); self.assertIn("allocation_process", codes)

    def test_paired_units_cannot_be_declared_independent(self):
        state = complete_state(); state["facts"]["experimental_unit"]["value"] = "同一单位重复测量两个条件。"
        self.assertTrue(any(r["code"] == "unit_design_mismatch" for r in review(state)["blockers"]))

    def test_explicit_nonrandom_assignment_conflicts_with_randomized_design(self):
        state = complete_state(); state["facts"]["randomization"]["value"] = "没有随机分配，按方便顺序安排。"
        self.assertTrue(any(r["code"] == "randomized_design_conflict" for r in review(state)["blockers"]))

    def test_pairing_and_blocks_need_relationship_evidence(self):
        state = complete_state(); state["facts"]["design"]["value"] = "paired"
        self.assertTrue(any(r["code"] == "paired_matching_basis" for r in review(state)["blockers"]))
        state["facts"]["design"]["value"] = "rcbd"
        self.assertTrue(any(r["code"] == "blocking_basis" for r in review(state)["blockers"]))

    def test_significance_without_practical_or_negative_rules_is_insufficient(self):
        state = complete_state(); state["facts"]["acceptance"]["value"] = "p<0.05则成功。"
        codes = {r["code"] for r in review(state)["blockers"]}
        self.assertIn("practical_vs_statistical", codes); self.assertIn("negative_outcomes", codes)

    def test_plan_is_acyclic_and_every_step_has_owner_output_acceptance(self):
        plan = build_blueprint(complete_state()); seen = set()
        for node in plan["nodes"]:
            self.assertTrue(set(node["dependencies"]) <= seen)
            self.assertTrue(node["owner"] and node["outputs"] and node["acceptance"])
            self.assertIn(node["capability"], {"implemented", "mock", "manual"})
            self.assertFalse(node["executed"])
            seen.add(node["id"])
        self.assertEqual(next(n for n in plan["nodes"] if n["id"] == "execute")["capability"], "manual")

    def test_partial_plan_remains_visible_and_export_has_human_awareness(self):
        state = {"id": "partial", "revision": 1, "facts": {}, "unknown": [], "conflicts": {}, "decisions": []}
        plan = build_blueprint(state)
        self.assertEqual(plan["status"], "draft_with_open_questions")
        self.assertIn("尚未明确", render_map(state))
        output = export_markdown(state)
        self.assertIn("人类认知检查", output)
        self.assertIn("不能", output)

    def test_field_metadata_allows_client_questions_with_rationale(self):
        self.assertEqual(len(FIELDS), 20)
        self.assertTrue(all(f["prompt"] and f["rationale"] and f["label"] for f in FIELDS.values()))
        self.assertEqual({r["value"] for r in FIELDS["objective_type"]["options"]}, {"comparison", "prediction", "causal", "exploration", "replication"})


if __name__ == "__main__": unittest.main()
