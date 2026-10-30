"""One explicitly synthetic planning example shared by both interfaces."""
from pathlib import Path

from .general.planning.ledger import new_state, apply, save
from .general.planning.runtime import _questions, review

VALUES = {
    'research_question': '在同一合成场数据与固定预算下，比较线性候选与非线性基线的误差，决定是否继续投入复现研究。',
    'objective_type': 'comparison',
    'hypothesis': '线性候选能否在当前数据条件下保持接近基线的误差，同时降低运行成本？',
    'scope': '仅限本示例声明的合成二维场、数据版本与预算。',
    'exclusions': '不宣称已复现任何真实论文，不外推到其他方程或数据分布。',
    'experimental_unit': '每个独立合成数据实现为分配和推断单位；同一实现上的网格点不作为独立重复。',
    'factors': '线性候选与非线性基线两个水平，主要比较候选减基线。',
    'design': 'crd',
    'outcomes': '每个独立实现的相对误差均值，越低越好；运行成本作为辅助指标。',
    'baseline': '演示用非线性基线，保持相同数据版本、训练预算与评价规则。',
    'data_source': '合成界面示例 interface_demo_v1；没有真实观测或论文实验结果。',
    'randomization': '正式先导前对独立实现随机分配，记录实际顺序与种子。',
    'analysis': '估计候选减基线的单位均值差及不确定区间，报告成本与诊断。',
    'acceptance': '逐项交付误差差异、区间与成本记录；阴性、不确定结果同样交付，预算耗尽停止。',
    'resources': '演示约束：最多6次运行、2小时上限；界面示例不会执行这些运行。',
    'risks': '独立性、指标口径或工具适配未核实时，由研究者停止并复核。',
    'reproducibility': '保存数据版本、代码版本、配置、分配种子及偏离日志。',
    'human_roles': '研究者确认目标与设计，方法负责人复核分析，执行者另行获得授权。',
    'deliverable': '可复核计划、步骤与责任清单、来源及未知、执行交接说明。',
}
PILOT_ANSWER = '固定预算先导；先核实独立性与测量流程，不宣称功效保证。'


def example_state():
    state = new_state()
    state['id'] = 'd'*32
    apply(state, {'updates': {field: {'value': value, 'quote': value,
        'status': 'proposed' if field == 'hypothesis' else 'declared'} for field, value in VALUES.items()},
        'unknown': ['sampling']}, 1)
    state['revision'] = 1
    state['pending'] = _questions(state, review(state))[0]
    return state


def create_example(base, *, workspace=None):
    from .general.conversation import GeneralSession
    from .general.planning.ledger import new_state
    session = GeneralSession.create(Path(base), backend='offline', workspace=workspace)
    state = example_state()
    # Each persisted example owns a fresh ledger identity, never overwrites a
    # previous example's snapshots, and never calls a provider or scientific tool.
    state['id'] = new_state()['id']; state['revision'] = 0
    session.meta.update(interface_example=True, active_task='research_planning',
                        phase='needs_input', last_report_kind='research_planning')
    save(session, state)
    return session
