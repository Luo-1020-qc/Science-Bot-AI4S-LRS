"""Formative teach-back prompts, never a claim to measure human understanding."""
import re

DIMENSIONS = {
    'question_boundary': ('问题与边界', r'问题|目标|范围|仅限|不推广|不声称|不宣称|question|scope|limited', ('research_question', 'scope', 'exclusions')),
    'design_tradeoff': ('设计与取舍', r'因为|所以|配对|区组|混杂|替代|取舍|泄漏|独立|because|paired|confound|leak', ('experimental_unit', 'design', 'analysis')),
    'uncertainty': ('未知与可能改变判断的结果', r'未知|不确定|先导|不支持|阴性|反向|局限|尚未|未核实|uncertain|pilot|negative', ('risks', 'acceptance')),
    'responsibility_stop': ('责任与停止条件', r'负责|复核|审批|停止|上限|交还|导师|人工|review|stop|responsib', ('human_roles', 'resources', 'acceptance')),
}


def review_reflection(state, text):
    rows = []
    for key, (label, pattern, fields) in DIMENSIONS.items():
        mentions = [m.group(0) for m in re.finditer(pattern, text, re.I)][:6]
        rows.append({'dimension': key, 'label': label, 'mentioned_cues': mentions,
                     'needs_discussion': not bool(mentions),
                     'compare_with': {f: state['facts'][f]['value'] for f in fields if f in state['facts']}})
    flags = []
    for phrase in ('证明因果', '保证功效', '一直试到显著', '确认就能执行', '模拟等于实测'):
        if phrase in text:
            flags.append('请共同核对这句话的完整含义（含否定语境），不能仅凭关键词判断对错：'+phrase)
    return {'kind': 'formative_discussion_cues', 'dimensions': rows, 'discussion_flags': flags,
            'human_understanding_measured': False, 'correctness_scored': False,
            'limitation': '关键词只提示讨论覆盖，不能判断复述是否正确、是否理解因果关系或是否提高理解；须由研究者/评审对照计划核实。'}


def render(state, text=None):
    if text is None:
        text = state.get('reflections', [{}])[-1].get('text', '') if state.get('reflections') else ''
    result = review_reflection(state, text)
    lines = ['请用自己的话说明以下取舍；也可明确不同意当前方案：']
    for row in result['dimensions']:
        lines.append('- '+row['label']+'：'+('；'.join(row['compare_with'].values()) or '尚待明确，请指出缺口'))
    if text:
        lines += ['', '最近复述的讨论提示：']
        for row in result['dimensions']:
            lines.append('- '+row['label']+'：'+('检测到相关词，仍需核对含义' if row['mentioned_cues'] else '可补充说明'))
        lines.extend(result['discussion_flags'])
    lines += ['', result['limitation'], '用 /plan reflect <你的理解与疑问> 保存复述，不会代替计划确认。']
    return '\n'.join(lines), result
