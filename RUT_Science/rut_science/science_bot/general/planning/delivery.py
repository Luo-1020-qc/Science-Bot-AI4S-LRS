"""Pure, shared research-design readout. No new claims, tools or model calls."""
from .blueprint import FIELDS, review
from .ledger import contract_hash


SECTIONS = (
    ('问题与结论边界', ('research_question', 'objective_type', 'hypothesis', 'scope', 'exclusions')),
    ('实验设计与主要对比', ('design', 'experimental_unit', 'factors', 'baseline')),
    ('数据、样本与分配', ('data_source', 'sampling', 'randomization')),
    ('指标与分析', ('outcomes', 'analysis')),
    ('验收、阴性结果与停止', ('acceptance', 'resources', 'risks')),
    ('复现、交付与责任', ('reproducibility', 'deliverable', 'human_roles')),
)
OBJECTIVES = {'comparison': '比较', 'prediction': '预测', 'causal': '因果', 'exploration': '探索', 'replication': '复现'}
DESIGNS = {'crd': '独立随机分配', 'paired': '配对', 'rcbd': '区组', 'factorial': '多因素',
           'observational': '观察性', 'prediction': '预测评估', 'custom': '另行说明的设计'}


def design_readout(state):
    assessment = review(state)
    sections = []
    for title, fields in SECTIONS:
        items = []
        for field in fields:
            fact = state['facts'].get(field)
            status = 'missing'
            value = '尚待明确'
            if fact:
                status, value = fact['status'], fact['value']
                names = OBJECTIVES if field == 'objective_type' else DESIGNS if field == 'design' else {}
                value = names.get(value, value)
            if field in state['unknown']:
                status, value = 'unknown', '明确未知，尚无依据'
            elif field in state['conflicts']:
                status, value = 'conflict', '声明冲突，待选择或更正'
            elif field in state['stale']:
                status = 'stale'
            if not fact and field not in assessment['required_fields'] and status == 'missing':
                continue
            items.append({'field': field, 'label': FIELDS[field]['label'], 'value': value, 'status': status})
        sections.append({'title': title, 'items': items})
    issues = []
    for row in assessment['checks']:
        if row['status'] != 'passed' and not any(r['field'] == row['field'] for r in issues):
            issues.append({'field': row['field'], 'label': FIELDS[row['field']]['label'],
                           'detail': row['detail'], 'blocking': row['status'] == 'blocked'})
    actions = [{'field': f, 'label': FIELDS[f]['label'], 'text': row['text'], 'executed': False}
               for f, row in state.get('evidence_actions', {}).items()]
    return {'title': '实验设计草案', 'hash': contract_hash(state), 'ready': assessment['ready'],
            'approved': bool(state['approval']), 'sections': sections, 'issues': issues,
            'evidence_actions': actions, 'selected_evidence_count': len(state.get('evidence', [])),
            'execution_authorized': False,
            'next_step': ('当前版本已确认，可导出交付并另行核实执行条件。' if state['approval'] else
                          '核对下列设计、方法假设与责任，再决定是否确认当前版本。' if assessment['ready'] else
                          '先处理阻断项；取得依据前可以导出带未决项的草案。')}


def render_design(state):
    readout = design_readout(state)
    labels = {'proposed': '待确认提议', 'unknown': '未知', 'conflict': '冲突', 'stale': '需重新核对', 'missing': '待明确'}
    lines = [readout['title']+'（规划，尚未执行）']
    for section in readout['sections']:
        lines += ['', section['title']]
        for item in section['items']:
            flag = ' ['+labels[item['status']]+']' if item['status'] in labels else ''
            lines.append('- '+item['label']+flag+'：'+item['value'])
    if readout['issues']:
        lines += ['', '待核对事项']
        lines += ['- '+r['label']+'：'+r['detail'] for r in readout['issues']]
    if readout['evidence_actions']:
        lines += ['', '获取依据的拟议步骤（未执行）']
        lines += ['- '+r['label']+'：'+r['text'] for r in readout['evidence_actions']]
    lines += ['', '已显式选择 '+str(readout['selected_evidence_count'])+' 个来源片段；声明和出处仍需核实。', readout['next_step']]
    return '\n'.join(lines)
