"""Contextual choice suggestions and version-bound human selections."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from ....util import digest
from .blueprint import FIELDS, non_actionable
from .ledger import contract_hash, apply, accept

INTENTS = ('comparison', 'prediction', 'replication', 'causal', 'exploration', 'general')
DIM = 512
VERSION = 'context_choice_intent_v1'
POLICY = Path(__file__).with_name('choice_policy.json')

# Prospective choices describe possible boundaries, not measured findings.
BASE = {
 'research_question': [('先判断方案是否值得继续', '限定研究场景，比较候选与基线的表现，以决定是否继续投入。'), ('先明确实际应用问题', '先明确目标对象、应用条件与需要支持的实际决定，再选择实验方案。'), ('先整理可验证的研究问题', '从可获得的数据和证据出发，形成能被结果支持或否定的研究问题。')],
 'hypothesis': [('比较候选与基线的差异', '检验限定条件下候选与基线的主要响应差异，允许没有差异或反向结果。'), ('先探索，不预设谁更好', '本轮作为探索性先导，不预设优胜方向，后续根据独立证据提出待检验命题。'), ('先核对论文里的具体命题', '先由研究者明确选择论文中的命题及适用条件，再制定复现假设。')],
 'scope': [('先限定一个应用场景', '结论限于本轮明确选择的对象、数据和应用条件，不外推到未测试场景。'), ('先做可行性先导', '本轮仅评估受限场景内的可行性，依据先导结果决定是否继续，不给出普遍有效结论。'), ('分别检查不同条件', '分别报告用户选择的不同条件下的结果，结论只覆盖实际测试的条件。')],
 'exclusions': [('不做未测试条件下的外推', '本轮不声称未测试对象、数据分布或条件下仍有效。'), ('不把预测差异解释为因果', '本轮不把相关性或预测性能差异解释为因果效应。'), ('先不开展真实训练或实验', '本轮交付研究方案与证据清单，实际执行另行确认数据、参数和权限。')],
 'experimental_unit': [('按独立对象汇总', '每个独立研究对象作为推断单位，同一对象的多次测量先在对象内汇总。'), ('按同一对象配对比较', '同一研究对象在候选条件间配对，技术重复不作为额外独立单位。'), ('按来源或批次分组处理', '明确来源或批次的共享关系，按对象或区组处理相关测量，不把数据行直接当作独立重复。')],
 'factors': [('先固定候选与基线', '主要对比为用户选择的候选与基线，其余数据和评估条件保持一致。'), ('重点比较数据条件变化', '明确数据条件为主要变化因素，各条件分别比较候选与基线。'), ('先探索多个可能因素', '先列出可控因素与可能交互作用，再由研究者决定主要对比。')],
 'outcomes': [('以预测误差为主', '按独立单位汇总预测误差均值，越低越好；成本作为辅助指标。'), ('以任务成功比例为主', '按独立单位汇总任务成功比例，越高越好，失败和不确定结果同样记录。'), ('以资源成本为主', '按独立单位汇总运行时间或资源成本，越低越好，同时报告质量变化。')],
 'baseline': [('使用同数据、同预算的基线', '选择研究者确认的基线，使用相同数据划分、预算和评估流程，保留所有结果。'), ('先采用简单且可复现的基线', '先用可复现的简单方法作参照，再评估复杂候选带来的额外收益和成本。'), ('按选定论文核对基线', '由研究者选择原论文中的基线与对应配置，核对后再制定公平比较。')],
 'data_source': [('使用已有数据并登记版本', '由研究者明确选择已有数据，登记来源与版本；训练、验证和最终测试分别使用，按对象隔离以防泄漏。'), ('使用明确选择的公开数据', '由研究者明确选择公开数据及版本，记录获取方式，按对象划分训练、验证和最终测试以防泄漏。'), ('先用合成数据验证流程', '本轮使用显式标记的合成数据检查流程，不能据此代替真实应用结论。')],
 'sampling': [('先做先导获取依据', '先做先导核实方差、独立性与测量流程，不宣称功效保证，后续再确定样本与重复。'), ('先整理已有依据', '先收集并核对已有的方差、效应和设计布局来源，再由研究者确定样本与重复。'), ('先采用固定预算的探索', '作为固定预算探索性先导，重复与预算由研究者明确声明，报告不确定性，不宣称功效保证。')],
 'randomization': [('记录实际分配过程', '按独立单位实施并记录随机分配和运行顺序，保留种子与分配日志。'), ('在配对或区组内安排顺序', '按已确认的配对或区组结构安排分配与运行顺序，记录过程和偏离。'), ('无法随机时明确偏差', '明确未随机的原因和混杂风险，限制结论范围，由研究者复核识别假设。')],
 'analysis': [('比较单位层面的差异与区间', '估计独立单位层面的候选与基线差异，报告区间或其他不确定性，并保留阴性结果。'), ('按配对或分组结构估计', '按照已确认的配对或分组结构估计主要对比及不确定性，方法由研究者复核。'), ('先做探索性描述', '先描述各单位的分布、差异和不确定性，明确探索性质，后续独立验证。')],
 'acceptance': [('按产物完整性验收', '逐项核对数据、配置、全部结果与可复现记录；不支持或不确定结果也交付，预算达到上限即停止。'), ('按误差与成本的取舍判断', '由研究者进一步确认可测的实际收益阈值，完整记录误差、成本及阴性结果，达到资源上限停止。'), ('先验收先导是否可继续', '逐项核对先导的数据可用性、独立性和测量流程，不确定时停止并补证据，不把阴性结果视为失败。')],
 'resources': [('先由我确认硬上限', '资源硬上限尚未确定，待研究者明确时间、运行次数或经费后继续，不自动扩充预算。'), ('沿用已声明的预算', '沿用研究者此前明确声明的硬预算，达到上限停止，不为追求正结果增加运行。'), ('先缩小目标再核算', '先把研究收缩到可行的先导目标，核算资源后由研究者确认硬上限。')],
 'risks': [('重点检查数据与独立性', '优先核查数据泄漏、共享对象与独立性假设；证据不足时停止并交还研究者判断。'), ('重点检查比较是否公平', '优先核查基线、预算和评估口径；条件无法对齐时停止并修订方案。'), ('重点检查外推和复现条件', '优先核查来源、实现差异和适用范围；结论不确定时保留限制并交还人类复核。')],
 'reproducibility': [('保存版本、配置与全部结果', '保存代码和数据版本、配置、种子、运行日志、失败及阴性结果。'), ('优先建立最小复现记录', '逐项记录数据来源、代码版本、最小配置和操作日志，核对能否复现。'), ('记录每次偏离与修改', '保存数据和代码版本、种子及配置日志，单独记录方案偏离、修改理由和前后结果。')],
 'human_roles': [('由我确认边界和结论', '研究者负责确认边界、复核方案和结论；执行人员及授权在实际作业前明确。'), ('由导师或领域专家复核', '研究者整理方案，由导师或领域专家复核方法、证据和结论，执行另行授权。'), ('由团队分工并明确责任', '团队明确边界确认、方法复核、实际执行和结论负责人的分工，研究者负责最终确认。')],
 'deliverable': [('交付可复核研究方案', '交付研究问题、边界、设计、未知、证据来源及逐项验收清单。'), ('交付最小复现包', '交付数据版本、代码配置、操作日志及完整结果，保留失败和不确定性。'), ('交付比较报告与后续建议', '交付候选与基线的完整比较、成本、限制，以及是否继续研究的依据。')],
}
SCOPES = {
 'comparison': [('同一数据条件下公平比较', '只在本轮明确选择的数据条件内比较候选与基线，统一数据划分、预算和评估流程，不外推到未测试条件。'), ('先判断是否值得继续', '先在限定场景内做可行性比较，结合质量与成本决定是否继续投入，不宣称普遍优越。'), ('比较跨条件的稳定性', '在用户明确选择的不同数据条件中分别比较候选与基线，评估稳定性，结论限于实际测试条件。')],
 'prediction': [('先看独立留出数据的预测', '只评估明确选择的最终留出数据上的预测表现，训练与验证用于拟合和选择，最终测试不用于反复调参。'), ('关注新对象上的预测', '仅评估新对象上的预测，按对象隔离训练、验证和最终测试，结论限于所选对象范围。'), ('关注未来时间段的预测', '仅评估后续时间段的预测，按时间隔离训练、验证和最终测试，避免未来信息泄漏。')],
 'replication': [('先复现论文的核心命题', '由研究者明确选择论文中的核心命题和原始适用条件，先做对应复现，不外推到新条件。'), ('先建立最小可复现流程', '先核对选定论文的数据、实现和评估流程，形成最小复现记录，保留无法复现之处。'), ('检查变化条件下是否仍成立', '在明确选择的原论文命题基础上，逐项记录变化条件，单独报告变化后的结果与限制。')],
 'causal': [('明确目标干预和适用对象', '先限定目标对象与干预，核对识别假设后估计其对主要结局的因果效应，不用预测性能代替因果证据。'), ('先核查能否实施随机分配', '本轮先评估目标对象上的随机分配可行性，实际分配过程和方法须由研究者确认。'), ('先审查观察数据的识别条件', '本轮先核查观察数据中的混杂、识别条件及限制，证据不足时不作因果结论。')],
 'exploration': [('先探索关联或现象', '只描述限定数据范围内的现象与关联，不预设优胜方向，不作确认性或因果结论。'), ('先筛选值得验证的因素', '先在明确范围内筛选候选因素和机制，后续使用独立数据验证，不把筛选结果当作已证实规律。'), ('先评估数据和方法可行性', '先核查数据、测量和分析方法是否可行，形成后续研究问题，不宣称方法已有效。')],
}


def vector(text):
    text = text.casefold()[:5000]
    tokens = re.findall(r'[a-z][a-z0-9_+-]*', text)
    for word in re.findall(r'[\u4e00-\u9fff]+', text):
        tokens.extend(word[i:i+2] for i in range(len(word)-1))
    x = [0.0]*DIM
    for token in tokens:
        index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], 'big') % DIM
        x[index] += 1
    norm = math.sqrt(sum(v*v for v in x)) or 1
    return [v/norm for v in x]


def load_policy():
    model = json.loads(POLICY.read_text(encoding='utf-8'))
    w = model.get('weights')
    if (model.get('version') != VERSION or model.get('intents') != list(INTENTS) or model.get('dimensions') != DIM
            or not isinstance(w, list) or len(w) != len(INTENTS)
            or any(not isinstance(row, list) or len(row) != DIM or any(type(v) not in (float,int)
                   or not math.isfinite(v) or abs(v) > 100 for v in row) for row in w)):
        raise ValueError('Invalid contextual choice policy')
    return model


def keyword_intent(text):
    for intent, pattern in [('replication',r'复现|复刻|replicat|reproduc'), ('causal',r'因果|干预|causal'),
                            ('prediction',r'预测|留出|predict|forecast'), ('comparison',r'比较|对比|compare|comparison'),
                            ('exploration',r'探索|筛选|explor')]:
        if re.search(pattern, text, re.I): return intent
    return 'general'


def context_text(state, text=''):
    # Local context is user declarations, never unselected or local-only paper text.
    return '\n'.join([text[:1800]]+[state['facts'].get(f, {}).get('value','')[:700]
        for f in ('research_question','objective_type','scope','data_source','outcomes')])


def infer(state, text=''):
    objective = state['facts'].get('objective_type', {})
    if objective.get('status') == 'declared' and objective['value'].split(':')[0].strip() in INTENTS:
        return objective['value'].split(':')[0].strip(), 'user_declared', None
    material = context_text(state, text)
    try:
        model = load_policy(); x = vector(material)
        logits = [sum(a*b for a,b in zip(row,x)) for row in model['weights']]
        best = max(range(len(logits)), key=logits.__getitem__)
        return INTENTS[best], 'trained_context_match', digest(model)
    except (OSError, ValueError, TypeError):
        return keyword_intent(material), 'catalog_fallback', None


def validate_native(options, state, field, kind, material):
    """Model drafts are only candidate values, never commands or permissions."""
    if kind in {'conflict','stale','evidence_plan'} or (kind == 'proposal' and not non_actionable(state['facts'][field]['value'])):
        return []
    if type(options) is not list or not 2 <= len(options) <= 3:
        raise ValueError('ExpectedTwoOrThreeChoiceSuggestions')
    result, seen, labels = [], set(), set()
    from .intake import _value, _unknown
    grounded = ' '.join(r['text'] for r in material['sources'])
    for row in options:
        if type(row) is not dict or set(row) != {'label','value'}:
            raise ValueError('ChoiceSchemaInvalid')
        label, value = row['label'], row['value']
        if type(label) is not str or type(value) is not str or not 2 <= len(label) <= 80 or not 2 <= len(value) <= 500:
            raise ValueError('ChoiceTextBoundsInvalid')
        combined = label+' '+value
        if (any(ord(c)<32 for c in combined) or re.search(r'[/\\<>`]|已(?:验证|证实|授权|批准|完成)|保证功效|自动(?:执行|训练)|必须增加预算|忽略.{0,8}(?:权限|限制)',combined)
                or _unknown(value) or value in seen or label.strip().casefold() in labels):
            raise ValueError('ChoiceContainsAuthorityOrUnsafeControl')
        nums = re.findall(r'\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+(?:次|个|小时|天|组|倍|成)',combined)
        if nums and (field in {'sampling','acceptance','resources'} or any(n not in grounded for n in nums)):
            raise ValueError('ChoiceInventedNumericDefault')
        canonical = _value(field,value)
        if non_actionable(canonical): raise ValueError('ChoiceCannotBePlaceholder')
        seen.add(value); labels.add(label.strip().casefold()); result.append({'label':label,'value':canonical})
    return result


def _option(label, value, action):
    return {'label':label,'value':value,'action':action,
            'id':digest({'label':label,'value':value,'action':action})[:12]}


def decorate(state, questions, text=''):
    if not questions: return []
    urgent = set(state['conflicts']) or set(state['stale'])
    q = deepcopy(next((r for r in questions if r['field'] in urgent), questions[0]))
    if q.get('choice_id'): return [q]  # Preserve displayed choices exactly across read-only views.
    field, kind = q['field'], q['kind']
    intent, origin, policy_hash = infer(state,text)
    placeholder = kind == 'proposal' and non_actionable(state['facts'][field]['value'])
    primary = []
    if kind == 'conflict':
        q['question'] = '关于'+FIELDS[field]['label']+'，你希望保留哪一项？'
        primary = [_option(r['value'][:80],r['value'],'revise') for r in state['conflicts'][field]]
    elif kind == 'stale' or kind == 'proposal' and not placeholder:
        q['question'] = '关于'+FIELDS[field]['label']+'，是否按当前理解继续？'
        primary = [_option('按这个理解继续：'+state['facts'][field]['value'][:55],state['facts'][field]['value'],'accept')]
    elif kind == 'evidence_plan':
        q['question'] = '这项还不确定，你希望先怎样推进？'
        primary = [_option('先查已有资料','先查找并核对已有资料，再由研究者确认适用性。','evidence'),
                   _option('先安排先导获取依据','先规划先导以核查独立性与测量流程，不填入未知数值。','evidence'),
                   _option('先缩小研究目标','先与研究者讨论缩小本轮目标，取得依据后再更新边界。','evidence')]
    else:
        if q.get('origin') != 'model' or placeholder or re.search(r'fact:|answer:|\bscope\b|占位|待澄清',q['question']):
            q['question'] = {'scope':'这次研究先覆盖哪种范围？','experimental_unit':'你希望按什么单位比较或汇总？',
                'acceptance':'这轮研究怎样算完成？','hypothesis':'这次最想验证哪件事？',
                'objective_type':'这次研究主要想达到什么目的？'}.get(field,FIELDS[field]['prompt'])
        native = q.get('suggested_options')
        if native:
            pairs = [(r['label'],r['value']) for r in native]; origin = 'validated_model_suggestions'
        elif FIELDS[field]['options']:
            pairs = [(r['label'],r['value']) for r in FIELDS[field]['options']]
            pairs.sort(key=lambda r: r[1] != intent)
        else:
            pairs = SCOPES.get(intent,BASE['scope']) if field == 'scope' else BASE[field]
        action = 'revise' if field in state['facts'] else 'declare'
        primary = [_option(label,'未知' if non_actionable(value) else value,
                           'unknown' if non_actionable(value) else action) for label,value in pairs]
    primary += [_option('暂不确定','未知','unknown'),_option('其他，我来补充','','custom')]
    q.update(options=primary, allow_accept=False, choice_policy={'intent':intent,'origin':origin,'policy_hash':policy_hash})
    q['choice_id'] = digest({'plan_hash':contract_hash(state),'field':field,'kind':kind,'options':primary})[:16]
    q['choice_plan_hash'] = contract_hash(state)
    return [q]


def selection(state, text, *, explicit=False):
    q = state.get('pending') or {}
    if explicit and q.get('field') and not q.get('choice_id'):
        q = decorate(state,[q])[0]
    if (explicit or re.fullmatch(r'(?:选|选择)?\s*[1-9][0-9]?\s*[.。]?',text.strip())) and q.get('choice_id') and q.get('choice_plan_hash') != contract_hash(state):
        raise ValueError('选项对应的计划内容已改变，请重新获取问题。')
    if explicit:
        parts = text.split()
        if len(parts) != 2 or parts[0] != q.get('choice_id'):
            raise ValueError('选项已更新，请刷新当前问题后重新选择。')
        row = next((r for r in q.get('options',[]) if r.get('id') == parts[1]),None)
        if row is None: raise ValueError('该选项不属于当前问题。')
        return q,row
    if not q.get('choice_id'): return None
    number = re.fullmatch(r'(?:选|选择)?\s*([1-9][0-9]?)\s*[.。]?',text.strip())
    if number:
        index = int(number[1])-1
        if index >= len(q['options']): raise ValueError('选项编号超出当前问题范围。')
        return q,q['options'][index]
    row = next((r for r in q['options'] if text.strip() == r['label'] or r['value'] and text.strip() == r['value']),None)
    if row and q.get('choice_plan_hash') != contract_hash(state):
        raise ValueError('选项对应的计划内容已改变，请重新获取问题。')
    return (q,row) if row else None


def apply_selection(state, selected, turn):
    q,row = selected; field = q['field']; action = row['action']
    if action == 'custom': return [],'直接输入你的想法即可，也可以一次补充多个边界。'
    if action == 'accept':
        accept(state,[field],turn); changes = [{'field':field,'kind':'accepted'}]
    elif action == 'evidence':
        if field not in state['unknown']: raise ValueError('此获取依据选项已过期。')
        state.setdefault('evidence_actions',{})[field] = {'text':row['value'],'turn':turn,'status':'user_proposed_step_not_evidence'}
        state['approval'] = None; changes = [{'field':field,'kind':'evidence_acquisition'}]
    elif action in {'declare','revise','unknown'}:
        from .intake import _value
        extraction = {'updates':{},'unknown':[field] if action == 'unknown' else []}
        if action != 'unknown': extraction['updates'][field] = {'value':_value(field,row['value']),'quote':'用户选择：'+row['label'],'status':'declared'}
        changes = apply(state,extraction,turn,revise=action == 'revise')
    else: raise ValueError('选项动作无效。')
    state['decisions'].append({'turn':turn,'type':'human_choice','field':field,'choice_id':q['choice_id'],
        'option_id':row['id'],'action':action,'meaning':'用户选择的规划声明或拟议步骤，未验证外部事实'})
    return changes,None
