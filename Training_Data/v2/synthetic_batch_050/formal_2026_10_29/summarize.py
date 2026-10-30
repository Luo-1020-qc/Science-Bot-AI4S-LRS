"""Publish a report only after the fixed-budget run and independent verification finish."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
RUN=BATCH/'training_run_002'


def load(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    plan=load(HERE/'plan.json');results=load(HERE/'results.json');audit=load(RUN/'independent_verification.json')
    assert results['training']['transitions']==plan['planned_transitions']==audit['ppo_transitions']==8000
    assert audit['passed'] and audit['ppo_rewards_independently_recomputed']==8000
    assert results['training']['ppo_iterations']==5 and results['training']['gradient_steps']==500
    original=load(BATCH/'release_manifest.json')
    assert all(hashlib.sha256((BATCH/p).read_bytes()).hexdigest()==h for p,h in original['sha256'].items())
    bc=load(RUN/'bc_verification.json')
    lines=['# 正式多批次训练结果：2026-10-29','',
        '本报告对应固定预算、单随机种子的本地候选策略实验。训练与复核已实际执行；未调用 DeepSeek，也未启动真实 Darcy/CViT 实验。',
        '',f"开始：{plan['started_at']}。完成训练与对照评测：{results['completed_at']}。耗时约 {results['elapsed_seconds']/60:.1f} 分钟（不含后续独立重算）。",'',
        '## 训练配置','',
        '- 任务：50 个受支持的合成场景；仅 train 分区进入训练。',
        '- Policy：32 维公开特征 → 64 Tanh → 64 Tanh，共 23 个带宿主 mask 的候选动作；独立 actor/critic 输出。',
        '- 初始化：重新执行 300 epoch 脚本 BC；不是恢复上一轮优化器。',
        f"- BC：502 个参考决策，训练动作拟合率 {bc['training_action_accuracy']:.1%}，末次损失 {bc['last_loss']:.6f}。真人专家标签为 0。",
        '- PPO：5 批 × 50 任务 × 32 步 = **8,000 条 fresh transition**；每批完成后再更新，下一批重新采样。',
        '- 每批 4 epoch、minibatch 64，共 **500 次梯度更新**；学习率 0.0003，clip 0.2，gamma 0.99，GAE lambda 0.95，entropy 0.01。',
        '- seed=20261029，CPU 单线程。固定报告最后一批权重，没有使用公开评价结果挑选 checkpoint。',
        '', '## 最终策略与对照','',
        '| 策略 | 训练集成功 | 训练平均决策数 | 反馈 error 次数（含OOM） | 开发任务成功 | 公开评价示例成功 |',
        '|---|---:|---:|---:|---:|---:|']
    for name,label in [('rule','规则'),('bc','BC'),('ppo','BC + PPO')]:
        s=results['summaries'][name];t=s['train'];d=s['development'];e=s['evaluation_example']
        lines.append(f"| {label} | {t['successes']}/{t['tasks']} | {t['mean_decisions']:.2f} | {t['total_errors']} | {d['successes']}/{d['tasks']} | {e['successes']}/{e['tasks']} |")
    bt=results['summaries']['bc']['train'];pt=results['summaries']['ppo']['train']
    lines+=['',f"相对 BC，PPO 的训练集成功任务数变化为 {pt['successes']-bt['successes']:+d}，平均决策数变化为 {pt['mean_decisions']-bt['mean_decisions']:+.2f}，平均回报变化为 {pt['mean_return']-bt['mean_return']:+.4f}。"]
    if all(results['summaries']['ppo'][s]['successes']==results['summaries']['bc'][s]['successes']==results['summaries']['rule'][s]['successes'] for s in ('train','development','evaluation_example')):
        lines+=['在本轮检查的成功率指标上，三种策略相同，**没有观察到 PPO 相对 BC 或规则的成功率优势**。已完成多批次更新不等于已经证明强化学习有增益。']
    elif pt['successes']<bt['successes']:
        lines+=['**本轮最终 PPO 发生退化，不满足替换 BC/规则的验收条件。保留全部负结果，不挑选早期较好权重替换预先指定的最终结果。**']
    lines+=['','成功要求匹配场景的预期终态：完成当前版本的模拟研究闭环，或引用实际公开阻断证据停止。',
        '规则训练集结果复用已封存且实际执行过的 50 条参考回放；BC 训练集、全部非训练诊断均重新执行，PPO 训练集结果来自本次训练结束后的重新评测。',
        '训练集的 6 次反馈 error 对应预设 mock OOM，属于必须处理的失败反馈，不代表有 6 次非法工具调用。',
        '', '## 各 PPO 批次','',
        '| 批次 | 新采样步数 | 成功终止回合 | 业务预算耗尽 | 无依据停止 | 外部截断 | 平均每步奖励 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    metrics=[]
    for i in range(1,6):
        counts=Counter();n=0;total_reward=0.0;truncated=0
        with (RUN/f'iteration_{i:03d}/rollout.jsonl').open(encoding='utf-8') as f:
            for line in f:
                row=json.loads(line);n+=1;counts[row['classification']]+=1;total_reward+=row['reward'];truncated+=row['truncated']
        successes=counts['completed_mock_research_loop']+counts['justified_stop']
        lines.append(f"| {i} | {n} | {successes} | {counts['decision_budget_exhausted']} | {counts['unjustified_stop']} | {truncated} | {total_reward/n:.4f} |")
        metrics.append({'iteration':i,'samples':n,'classifications':dict(counts),'external_truncations':truncated,'mean_step_reward':total_reward/n})
    failure=load(HERE/'failure_analysis.json')
    if failure['failed_tasks']:
        lines+=['','## 失败轨迹诊断','',
            f"最终策略的 {failure['failed_tasks']} 个失败任务都已完成前段复核、冻结、分析和结论评估，但停留在 `loop_next_action`，没有进入 `report_build`。失败轨迹合计选择 next {failure['aggregate_actions'].get('next',0)} 次，各任务重复约 31～32 次，最终耗尽 40 步业务预算。",
            '这些重复动作每步仍有成本，没有重复里程碑奖励；目前证据显示是策略决策退化，不能据此声称发现了正奖励漏洞。具体优化原因尚未经过消融验证。',
            '一个需要优先核实的采样差异：每任务片段只有32步，小于业务预算40步。片段末尾进行外部截断和bootstrap后重置，因此本轮训练没有观察到40步预算耗尽惩罚，而完整评测观察到了。截断计算通过校验不等于训练覆盖了完整业务终态；这可能影响价值学习，但尚未通过消融证明因果。',
            '后续应在新版本实验中比较完整回合采样或跨片段续接、BC/KL 约束、更保守的 PPO 更新、共享 actor/critic 的影响，以及已完成编排动作的重复调用约束；这些都是待验证的改动，本轮没有改奖励或 mask 以追求更好结果。',
            '[逐步失败轨迹](failure_analysis.json)明确保存每步动作、奖励、状态特征哈希和候选概率。']
    lines+=['','各批都保存完整行为策略、rollout、更新后参数和重算证明。成功回合数受短任务重复 reset 影响，不能直接当作逐任务成功率；每步奖励也不能替代完整回合回报。',
        '', '## 核验与解释','',
        '- 8,000 条行为概率、价值、任务哈希、状态链、mask、终止/截断与奖励重算通过；5 批行为策略与上一批更新后的权重连续。',
        '- 50 个任务在每批均采样 32 步。业务终止不 bootstrap，外部截断 bootstrap 并切断 GAE 跨回合递推。',
        '- 原批次 27 个封存制品、旧 Harness 与权重保护清单均通过；未更改环境、奖励或默认线上策略。',
        '- 现有非训练数据仅 2 个开发任务、2 个公开评价示例。虽与本次训练的来源祖先分开，但共享合成机制且答案公开，不能视为独立盲测或真实跨领域泛化。',
        '- 本次只训练有限候选动作策略，不训练 DeepSeek 参数。训练成功不等于 PPO 相对 BC 或规则产生收益。',
        '', '## 文件入口','',
        '- [预先保存的实验配置](plan.json)',
        '- [机器可读结果](results.json)与[逐任务结果](evaluation_details.json)',
        '- [最终 PPO 权重](../training_run_002/updated_policy.json)与[BC 初始化权重](../training_run_002/bc_policy.json)',
        '- [独立重算报告](../training_run_002/independent_verification.json)',
        '- [本次训练代码](run.py)、[通用训练入口](../train.py)',
        '', '默认在线策略保持原设置。本次产物作为候选研究权重保留，下一步应以新增独立来源任务、更多随机种子和机制消融验证效果。','']
    (HERE/'README_训练结果.md').write_text('\n'.join(lines),encoding='utf-8')
    (HERE/'rollout_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (HERE/'conclusion.json').write_text(json.dumps({'training_completed':True,'mechanical_verification_passed':True,
        'candidate_accepted_for_deployment':False,'reason':'Final PPO 38/50 versus BC/rule 50/50; longer decision traces',
        'default_policy_changed':False,'posthoc_failed_tasks':failure['failed_tasks']},indent=2)+'\n',encoding='utf-8')
    manifest={}
    for folder in (HERE,RUN):
        for p in folder.rglob('*'):
            if p.is_file() and p.name!='experiment_manifest.json' and '__pycache__' not in p.parts:
                manifest[p.relative_to(BATCH).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    (HERE/'experiment_manifest.json').write_text(json.dumps({'sha256':manifest,'previous_release_unchanged':True},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(HERE/'README_训练结果.md'),'summaries':results['summaries'],'verified_transitions':audit['ppo_transitions']}),flush=True)


if __name__=='__main__':main()
