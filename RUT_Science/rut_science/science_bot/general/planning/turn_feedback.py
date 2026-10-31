"""Trace accepted/rejected updates and block unresolved corrections, without UI layout."""
import re
import json
from .blueprint import FIELDS


def revision_targets(text):
    from .intake import _labels
    from .routing import revision_content
    text=revision_content(text)
    labels = _labels()
    explicit=[labels[m[1].strip()] for m in re.finditer(r'(?:^|[;；\n])\s*([^:：;；\n]+)\s*[:：]',text) if m[1].strip() in labels]
    if explicit:return list(dict.fromkeys(explicit))
    if text.lstrip().startswith('{'):
        try:
            value=json.loads(text)
            if isinstance(value,dict):
                explicit=[labels[k] for k in value if k in labels]
                if explicit:return list(dict.fromkeys(explicit))
        except ValueError:pass
    targets = []
    if re.search(r'预算|经费|小时|分钟|最多|上限|budget|limit', text, re.I):
        targets.append('resources')
    if re.search(r'(?:目标|目的|研究问题).{0,8}(?:改|换)|改为预测|改成预测|不再.{0,12}差异', text):
        targets.append('objective_type')
    return targets or ['research_question']


def literal_resource_correction(text):
    """Only a clear literal new limit; never convert or invent numerical values."""
    from .routing import revision_content
    content=revision_content(text)
    # Structured answers already have an exact local parser; retain qualifiers
    # such as "demo budget" instead of extracting a shorter numerical suffix.
    if content.lstrip().startswith(('{','[')) or re.match(r'\s*(?:resources|资源|资源边界|预算)\s*[:：=]',content,re.I):
        return None
    match = re.search(r'(?:(?:后续|现在|今后|本轮)\s*)?(?:最多|不超过|预算(?:改为|调整为|缩减为|为)|(?:运行|拟合|时间|经费)上限(?:改为|为))[^。；;\n]{1,180}', text)
    if not match:
        return None
    value = re.split(r'[，,]\s*(?:之前|原来|原先|此前|原定|旧的)', match[0], maxsplit=1)[0].strip()
    if re.search(r'不是|并非|而是|是否|能否|要不要|考虑|可能|不确定|不知道',text[:match.start()]+value):
        return None
    if re.search(r'是否|不知道|不确定|考虑|原来|原先|此前|之前', value) or not re.search(r'\d|[一二三四五六七八九十两]', value):
        return None
    return {'value': value, 'quote': value, 'status': 'declared'}


def update_receipt(state, before, extraction, changes, text, turn, *, revision=False):
    rows = []
    for change in changes:
        field = change['field']
        status = ('conflict' if change['kind']=='conflict' else 'unknown' if change['kind'] in {'unknown','evidence_acquisition'}
                  else state['facts'][field]['status'])
        preview=lambda value: value[:240]+'…' if isinstance(value,str) and len(value)>240 else value
        rows.append({'field': field, 'status': status, 'before': preview(change.get('before')),
                     'after': preview(change.get('after',state['facts'].get(field,{}).get('value')))})
    for note in extraction.get('rejected_fields', []):
        rows.append({'field': note['field'], 'status': 'rejected', 'reason': note['reason']})
    targets = revision_targets(text) if revision else []
    covered = set(extraction.get('updates', {})) | set(extraction.get('unknown', []))
    guards = state.get('pending_revisions', {})
    for field in covered:
        guards.pop(field, None)
    for field in targets:
        if field not in covered:
            guards[field] = {'turn': turn, 'reason': '更正尚未写入，请明确提供该字段的新值；当前旧值不能继续用于确认。'}
            rows.append({'field': field, 'status': 'rejected', 'reason': guards[field]['reason']})
    if guards:
        state['pending_revisions'] = guards
        state['approval'] = None
    elif 'pending_revisions' in state:
        state.pop('pending_revisions')
    lines = []
    for row in rows:
        label = FIELDS[row['field']]['label']
        if row['status']=='rejected':
            lines.append('未采纳 · '+label+'：'+row['reason'])
        elif row['status']=='conflict':
            lines.append('待选择 · '+label+'：'+str(row['before'])+' → '+str(row['after'])+'（当前未覆盖旧值）')
        elif row['status']=='unknown':
            lines.append('已保留未知 · '+label)
        else:
            tag = '待确认提议' if row['status']=='proposed' else '已采纳'
            value = str(row['after'])
            if row.get('before') is not None:
                value = str(row['before'])+' → '+value
            lines.append(tag+' · '+label+'：'+value)
    if not rows:
        lines.append('本轮未新增或修改研究声明。'+(' '.join(extraction.get('notes', [])) or '可选择当前选项，或用“字段: 内容”补充。'))
    if extraction.get('notes') and rows:
        lines.extend(extraction['notes'])
    receipt = {'turn': turn, 'entries': rows, 'text': '\n'.join(lines)}
    # Store no new raw answer: accepted values already have ledger provenance.
    state['last_update']=receipt
    state['decisions'].append({'turn': turn, 'type': 'update_receipt',
                              'fields':{r['field']:r['status'] for r in rows}})
    return receipt


def last_receipt(state):
    return state.get('last_update')
