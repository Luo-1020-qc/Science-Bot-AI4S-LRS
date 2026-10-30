"""Immutable, user-grounded research planning snapshots and approval invalidation."""
from copy import deepcopy
from pathlib import Path
import json
import re
import uuid

from ....util import digest,write_json

VERSION='research_planning_v1'
EXTENSIONS={'evidence','question_history','clarification','evidence_actions'}
IMPACTS={
    'research_question':('hypothesis','scope','outcomes','analysis','acceptance'),
    'objective_type':('hypothesis','experimental_unit','factors','design','baseline','sampling','outcomes','randomization','analysis','acceptance'),
    'experimental_unit':('design','sampling','randomization','analysis','acceptance'),
    'factors':('design','sampling','analysis','acceptance'),
    'outcomes':('hypothesis','analysis','acceptance'),
    'data_source':('scope','sampling','analysis','reproducibility'),
    'design':('experimental_unit','sampling','randomization','analysis','acceptance'),
    'resources':('sampling','design'),
}


def new_state():
    return {'schema_version':VERSION,'id':uuid.uuid4().hex,'revision':0,'active':True,
        'facts':{},'unknown':[],'conflicts':{},'decisions':[],'approval':None,'pending':None,
        'reflections':[],'changes':[],'stale':{},'turns':0,'audience':'researcher_student',
        'last_notes':[],'last_export':None}


def contract_hash(state):
    content={'version':VERSION,'id':state['id'],'facts':state['facts'],'unknown':state['unknown'],
        'conflicts':state['conflicts'],'stale':state['stale']}
    # Empty extensions preserve every old v1 approval hash without migration.
    for key in ('evidence','evidence_actions'):
        if state.get(key):content[key]=state[key]
    return digest(content)


def validate(state):
    from .blueprint import FIELDS
    template=new_state()
    if (type(state) is not dict or set(state)-EXTENSIONS!=set(template)
            or state.get('schema_version')!=VERSION):
        raise ValueError('不支持的研究计划状态')
    if not re.fullmatch(r'[a-f0-9]{32}',state['id']) or type(state['revision']) is not int or state['revision']<0:
        raise ValueError('研究计划身份或版本无效')
    if type(state['facts']) is not dict or set(state['facts'])-set(FIELDS):raise ValueError('未知研究计划字段')
    for field,record in state['facts'].items():
        if type(record) is not dict or set(record)!={'value','quote','status','turn'}:raise ValueError('研究声明结构无效')
        if record['status'] not in {'declared','proposed'} or type(record['value']) is not str or not record['value'].strip() or len(record['value'])>3000:
            raise ValueError('研究声明必须为有限长度的用户声明或待确认推断')
        if type(record['quote']) is not str or not record['quote'] or len(record['quote'])>12000 or type(record['turn']) is not int:
            raise ValueError('研究声明必须保存原文与轮次')
    if not set(state['unknown'])<=set(FIELDS) or not set(state['conflicts'])<=set(FIELDS) or not set(state['stale'])<=set(FIELDS):
        raise ValueError('未知研究计划依赖字段')
    if type(state['active']) is not bool or type(state['turns']) is not int or state['turns']>200:
        raise ValueError('研究计划对话状态无效')
    if len(state['decisions'])>1000 or len(state['reflections'])>100 or len(state['changes'])>200:
        raise ValueError('研究计划记录超过会话限制')
    from .evidence import validate_sources
    validate_sources(state.get('evidence',[]))
    history=state.get('question_history',[])
    if type(history) is not list or len(history)>40:
        raise ValueError('澄清历史超出限制')
    for row in history:
        if (type(row) is not dict or set(row)!={'turn','field','kind','question','origin','basis_hash'}
                or row['field'] not in FIELDS or type(row['turn']) is not int
                or type(row['question']) is not str or not 1<=len(row['question'])<=1200
                or row['kind'] not in {'missing','refine','proposal','conflict','stale','evidence_plan'}
                or row['origin'] not in {'model','template'} or not re.fullmatch(r'[a-f0-9]{64}',row['basis_hash'])):
            raise ValueError('澄清历史结构无效')
    actions=state.get('evidence_actions',{})
    if type(actions) is not dict or set(actions)-set(FIELDS):raise ValueError('证据获取步骤字段无效')
    for row in actions.values():
        if (type(row) is not dict or set(row)!={'text','turn','status'} or type(row['turn']) is not int
                or type(row['text']) is not str or not 1<=len(row['text'])<=3000
                or row['status']!='user_proposed_step_not_evidence'):
            raise ValueError('证据获取步骤不能替代事实或真实执行')
    if 'clarification' in state and (type(state['clarification']) is not dict
            or state['clarification'].get('mode') not in {'dynamic','template'}):
        raise ValueError('澄清状态无效')
    if state['approval'] and state['approval'].get('contract_hash')!=contract_hash(state):
        raise ValueError('研究计划确认版本不匹配')
    return state


def load(session):
    ref=session.meta.get('planning_ref')
    if not ref:return None
    if type(ref) is not str or not re.fullmatch(r'planning/[a-f0-9]{32}/snapshots/[0-9]{5}\.json',ref):
        raise ValueError('研究计划引用无效')
    path=session.folder/ref
    if path.resolve()!=path.absolute() or not path.is_file() or path.stat().st_size>2_000_000:
        raise ValueError('研究计划文件不可用')
    state=json.loads(path.read_text(encoding='utf-8'))
    validate(state)
    if digest(state)!=session.meta.get('planning_hash') or state['id']!=ref.split('/')[1] or state['revision']!=int(path.stem):
        raise ValueError('研究计划快照已改变或版本不匹配')
    return state


def save(session,state):
    state['revision']+=1
    validate(state)
    ref=f"planning/{state['id']}/snapshots/{state['revision']:05d}.json"
    path=session.folder/ref
    if path.exists():raise ValueError('不能覆盖已有研究计划快照')
    if path.resolve()!=path.absolute():raise ValueError('研究计划目录不能重定向')
    write_json(path,state)
    session.meta.update(planning_ref=ref,planning_hash=digest(state))
    session.save()


def apply(state,extraction,turn,*,revise=False):
    """Validate before mutating; declarations are not independent scientific evidence."""
    from .blueprint import FIELDS
    updates=extraction.get('updates',{})
    unknown=extraction.get('unknown',[])
    if type(updates) is not dict or set(updates)-set(FIELDS) or set(unknown)-set(FIELDS):
        raise ValueError('研究计划字段不在登记范围内')
    before=deepcopy(state);changed=[]
    try:
        for field,record in updates.items():
            value=record['value'].strip()
            fact={'value':value,'quote':record['quote'],'status':record['status'],'turn':turn}
            old=state['facts'].get(field)
            if old and old['value']!=value and not revise:
                state['conflicts'][field]=[deepcopy(old),fact]
                changed.append({'field':field,'kind':'conflict','before':old['value'],'after':value})
                continue
            if old and old['value']==value and old['status']==fact['status'] and field not in state['stale'] and field not in state['conflicts'] and field not in state['unknown']:continue
            state['facts'][field]=fact
            state.get('evidence_actions',{}).pop(field,None)
            state['unknown']=[f for f in state['unknown'] if f!=field]
            state['conflicts'].pop(field,None);state['stale'].pop(field,None)
            changed.append({'field':field,'kind':'revised' if old else 'added','before':old['value'] if old else None,'after':value})
            if old and old['value']!=value:
                for dependent in IMPACTS.get(field,()):
                    if dependent in state['facts'] and dependent not in updates:
                        state['stale'][dependent]=f'{field} 已改变，需要重新检查该声明是否仍适用'
        for field in unknown:
            if field not in state['unknown']:state['unknown'].append(field)
            state['facts'].pop(field,None)
            state['conflicts'].pop(field,None)
            state['stale'].pop(field,None)
            for dependent in IMPACTS.get(field,()):
                if dependent in state['facts'] and dependent not in updates:
                    state['stale'][dependent]=f'{field} 已改为未知，需要重新检查依赖'
            changed.append({'field':field,'kind':'unknown','before':None,'after':None})
        if changed:
            state['approval']=None
            state['changes']=(state['changes']+changed)[-200:]
            state['decisions'].append({'turn':turn,'type':'revise' if revise else 'intake','changes':changed})
        validate(state)
    except Exception:
        state.clear();state.update(before);raise
    return changed


def accept(state,fields,turn):
    selected=list(fields) if fields else [f for f,r in state['facts'].items() if r['status']=='proposed']+list(state['stale'])
    if set(selected)-set(state['facts']):raise ValueError('只能确认已展示的研究声明')
    for field in selected:
        state['facts'][field]['status']='declared'
        state['stale'].pop(field,None)
        state['unknown']=[f for f in state['unknown'] if f!=field]
    if selected:
        state['approval']=None
        state['decisions'].append({'turn':turn,'type':'human_restatement','fields':selected,
            'meaning':'用户确认自己计划中的声明；未验证科学事实'})
    return selected
