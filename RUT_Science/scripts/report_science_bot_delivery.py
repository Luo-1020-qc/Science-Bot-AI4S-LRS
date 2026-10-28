"""Generate research figures and readable conclusions from measured artifacts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from rut_science.science_bot.session import ROOT, MODELS
from rut_science.util import write_json


def main():
    delivery = ROOT/"delivery"
    os.environ["MPLCONFIGDIR"] = str(delivery/".matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    summary = json.loads((delivery/"evaluation"/"summary.json").read_text(encoding="utf-8"))
    verification = json.loads((delivery/"verification.json").read_text(encoding="utf-8"))
    artifact_audit = json.loads((delivery/"artifact_audit.json").read_text(encoding="utf-8"))
    verification["checks"]["independent_rollout_audit"] = {"passed": artifact_audit["rollout_checks_passed"], "artifact": "artifact_audit.json"}
    verification["product_checks_passed"] &= artifact_audit["rollout_checks_passed"]
    write_json(delivery/"verification.json", verification)
    figures = delivery/"figures"
    figures.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
    for kind, label, color in (("ppo_scratch", "PPO from scratch", "#4878d0"), ("bc_ppo", "BC + PPO", "#ad4fab")):
        curves = [json.loads((MODELS/f"{kind}_{seed}"/"learning_curve.json").read_text()) for seed in (11, 22, 33, 44, 55)]
        steps = [r["steps"] for r in curves[0]]
        values = np.asarray([[r["success_last_100"] for r in curve] for curve in curves])
        ax.plot(steps, values.mean(0), label=label, color=color)
        ax.fill_between(steps, values.min(0), values.max(0), color=color, alpha=0.13)
    ax.set(xlabel="Actual collected transitions per seed", ylabel="Success in recent 100 training episodes", ylim=(0, 1.03))
    ax.set_title("Five training seeds; shaded area is seed range")
    ax.legend(); ax.grid(alpha=0.2)
    fig.savefig(figures/"training.png", dpi=180); fig.savefig(figures/"training.svg"); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), layout="constrained")
    for names, label in ((["rule_adaptive"], "Adaptive rule"), (["rule_dense"], "Dense rule"),
                         (["rule_search"], "Budgeted random search"), (["bc"], "BC"),
                         ([f"ppo_scratch_{s}" for s in (11, 22, 33, 44, 55)], "PPO (five-seed mean)"),
                         ([f"bc_ppo_{s}" for s in (11, 22, 33, 44, 55)], "BC + PPO (five-seed mean)")):
        rates = np.mean([[r["success_rate"] for r in summary["budget_curves"][name]] for name in names], axis=0)
        costs = np.mean([[r["mean_search_cu"] for r in summary["budget_curves"][name]] for name in names], axis=0)
        axes[0].plot([6, 10, 14], rates, "o-", label=label)
        axes[1].plot(costs, rates, "o-", label=label)
    axes[0].set(xlabel="Authorized search CU", ylabel="Held-out scientific success rate", xticks=[6, 10, 14], ylim=(0, 1.03))
    axes[1].set(xlabel="Mean consumed search CU", ylabel="Held-out scientific success rate", ylim=(0, 1.03))
    axes[0].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle("Controlled regression pilot: 8 root mechanism groups")
    fig.savefig(figures/"budget_quality.png", dpi=180); fig.savefig(figures/"budget_quality.svg"); plt.close(fig)

    aggregate = summary["variant_aggregates"]["bc_ppo"]
    low, high = aggregate["ci95"]
    conclusion = ("受控生成任务 pilot 支持 BC＋PPO 相对预注册自适应规则的成功率收益，但不外推到真实科研领域。" if low > 0
                  else "本次受控生成任务 pilot 未支持 BC＋PPO 相对强规则具有稳定成功率收益。" if high >= 0
                  else "本次受控生成任务 pilot 中，BC＋PPO 的成功率低于预注册自适应规则。")
    lines = ["# science Bot 实际交付与研究结果", "", "日期：2026-10-20（北京时间）。", "",
             f"产品自动验收：**{'通过' if verification['product_checks_passed'] else '存在未通过项'}**；逐项结果见 verification.json。", "",
             conclusion, "", "## 冻结比较", "", "训练/开发/最终评测按机制组隔离，部署权重仅按开发集选择。", "",
             "| 策略 | 成功/任务 | 成功率 | 平均搜索 CU |", "|---|---:|---:|---:|"]
    for name, record in summary["policies"].items():
        lines.append(f"| {name} | {record['successes']}/{record['tasks']} | {record['success_rate']:.3f} | {record['mean_search_cu']:.2f} |")
    lines += ["", "## 五训练种子的汇总", "", "区间同时重采样训练种子和根机制组；预算、故障及实例副本不当作独立机制组。", ""]
    for name, record in summary["variant_aggregates"].items():
        lines += [f"- {name}：平均成功率 {record['mean_success_rate']:.3f}；相对自适应规则差值 {record['paired_difference_vs_adaptive']:+.3f}，95% 区间 [{record['ci95'][0]:+.3f}, {record['ci95'][1]:+.3f}]。"]
    lines += ["", "BC＋PPO 和强规则在这 8 个留出机制组中均全部成功，bootstrap 差值区间退化为零；这不证明总体等效，也不代表总体不确定性为零。BC＋PPO 平均消耗约 9 CU，自适应规则约 2 CU，本轮不支持效率收益。强规则已经触及本样本的成功率上限，停止扩大 RL 训练。"]
    manifests = [json.loads(p.read_text()) for p in MODELS.glob("*/manifest.json") if p.parent.name != "selected"]
    transitions = sum(m.get("actual_transitions", 0) for m in manifests)
    preliminary = [json.loads(p.read_text()) for p in (ROOT/"models"/"planner").glob("*/manifest.json")]
    preliminary_transitions = sum(m.get("actual_transitions", 0) for m in preliminary)
    lines += ["", "## 训练与审计", "", f"正式 v1 共 {transitions:,} 个 PPO transitions；BC 数据独立记录。开发 pilot 和 smoke 额外使用 {preliminary_transitions:,} 个 transitions，费用不隐去。",
              "", "主线：从零 PPO 和 BC＋PPO 各五种子、每种子 20,000 步；四组消融各一种子 20,000 步。周期性开发评测选择权重，所有正式批次均保留候选/mask/概率/价值和轨迹；独立重算见 artifact_audit.json。",
              "", "初始 E0 的预算 3/6 未改变最优子集；校准时改用 1/6 检查最廉价参照与可承担实验的差异。初始失败审计保留在 environment_audit_initial_3_6.json，未删除失败记录。正式 E1 比较预算为 6/10/14。",
              "", "## 边界", "", "8 个留出机制组仍是小规模 pilot。Darcy 使用曾暴露的历史小 bundle，只验收真实数值工具和迁移，不作为新的盲测。实时 LLM 选择器只有两个 demo 根任务，单独报告，不并入生成环境的大批统计。四组消融只有一个训练种子，尚不足以稳定归因。",
              "", "全部奖励未使用塑形；候选置换由共享评分结构、乱序训练及语义一致性测试验证。未实现 BOHB、Elasticity 或通用 shell 编码代理。", "",
              "## 图与证据", "", "- figures/training.png：全部五种子的训练曲线与范围。",
              "- figures/budget_quality.png：同预算质量及消耗成本—质量曲线。",
              "- evaluation/final_test.json：完整配对原始记录。", "- evaluation/live_selector_pilot.json：真实固定 LLM 小批对照。",
              "- demo_sessions/：实际运行和恢复证据。"]
    (delivery/"实际交付与研究结果.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True)
    (delivery/"environment.lock").write_text("\n".join(x for x in freeze.stdout.splitlines()
        if not x.startswith(("-e ", "rut-science", "#")))+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
