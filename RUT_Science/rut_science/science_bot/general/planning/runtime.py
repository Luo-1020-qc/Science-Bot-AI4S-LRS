"""A persistent research planning conversation that preserves researcher awareness."""
from copy import deepcopy
import json
import re
from functools import lru_cache
from typing import TypedDict
from langgraph.graph import StateGraph,START,END

from ....util import digest,write_json
from .blueprint import FIELDS,review as blueprint_review,build_blueprint,render_map,export_markdown
from .ledger import new_state,load,save,apply,accept,contract_hash
from .intake import extract, _unknown
from .clarification import propose as propose_questions, remember
from .evidence import command as evidence_command, citation, metadata as evidence_metadata
from .understanding import render as render_understanding
from . import question_tool
from . import choices
from .delivery import render_design

COMMANDS={'/plan'}
HELP=('直接描述想研究的问题即可开始。每轮只优先澄清少数边界；可回答选项或使用“字段：内容”。\n'
      '/plan question [rule|trained] 启用边界问答工具；history/export 查看或导出训练观察；off 关闭；\n'
      '/plan map 查看研究地图；/plan draft 查看步骤与验收；/plan review 检查漏洞；\n'
      '/plan accept [字段] 确认模型理解；/plan revise 字段: 内容 明确更正；\n'
      '/plan explain 字段 了解为什么要问；/plan reflect 我的理解是… 记录自己的理解；\n'
      '/plan export 导出计划；/plan approve <版本哈希> 确认规划；/plan handoff 获取工作交接；\n'
      '/plan evidence add {"path":"paper.md","start_line":1,"end_line":40,"share_with_model":true} 选择论文片段；\n'
      '/plan evidence list/show <id>/remove <id> 管理证据；/plan understanding 查看复述讨论提示；\n'
      '/plan pause 暂停规划；/plan resume 继续；/plan new <新目标> 开始另一计划。')
CONCEPTS={
    'experimental_unit':('实验单位|推断单位|独立单位|experimental unit','实验单位是接受一次处理分配的对象；推断单位是你希望结论描述的对象。二者和测量次数可能不同。例如一个样本上的上千网格点不能自动算上千次独立实验；同一对象前后测量通常还存在配对关系。'),
    'design':('区组|配对|选择设计|怎么选设计','先看单位关系再选设计。独立对象可考虑两组比较；同一对象前后测量需考虑配对；存在数据来源或批次差异时可考虑区组；多个可控因素要考虑交互作用。设计名称不能替代实际分配和独立性依据。'),
    'sampling':('样本量|方差|功效|重复数','重复数应对应独立实验单位，并结合最小关心效应、误差/方差、设计布局、功效目标和资源约束讨论。没有依据时可以先规划先导，不用模板默认数值保证功效。'),
    'acceptance':('验收|显著|停止规则','交付完成、统计证据和实际重要性是不同判断。预先写清主要指标、效应或可检查的产物、阴性及不确定结果如何报告，以及什么时候停止或交还人类。不能以一直试到显著作为完成条件。'),
    'outcomes':('响应|主要指标|评价指标','先确定一个主要回答问题的响应，说明方向、量纲和按哪个单位汇总。其他指标可辅助解释，但不能看到结果后把最有利的指标改成主要指标。'),
    'randomization':('随机化|随机种子','随机种子用于复现分配过程，并不能证明实际执行了随机化或单位独立。还要说明分配对象、顺序、区组、实现过程和记录；不能随机时应声明可能的偏差与结论限制。'),
    'data_source':('数据划分|数据泄漏|训练集|测试集','训练数据用于拟合，验证数据用于选择方法或超参数，最终测试用于冻结后评估。划分要考虑同一对象、区组、来源或时间之间的信息关联，不能仅把行随机打乱就宣称没有泄漏。'),
    'objective_type':('因果|研究目的|比较与预测','比较回答声明条件下的差异，预测回答未见样本上的表现，因果还需要处理分配或明确识别假设。预测准确或相关性不能自动解释为因果。探索研究也可以先明确不做确认性结论。'),
}


def _explanation(field):
    spec=FIELDS[field]
    return spec['label']+'\n'+CONCEPTS.get(field,('',spec['rationale']))[1]+'\n你需要决定：'+spec['prompt']


def natural_start(text):
    if not isinstance(text,str) or text.startswith('/'):return False
    if re.search(r'^(?:什么是|解释|介绍|为什么|what\s+is|explain\b|介绍一下)',text,re.I):return False
    if re.search(r'(?:我|我们|帮我|帮我们).{0,12}(?:想|希望|需要|打算|准备).{0,18}(?:改进|提高|复现|搞清楚|试试|判断|评估).{0,50}(?:模型|论文|方法|实验|研究|数据|项目|课题|LinearNO|CViT|FNO)|(?:我的|我们的).{0,15}(?:模型|实验|研究|数据).{0,25}(?:效果不好|不太好|没思路|不知道|不清楚)|\b(?:I|we)\s+need\b.{0,40}\b(?:plan|design|replicate|reproduce|evaluate)\b',text,re.I):return True
    return bool(re.search(r'(?:帮我|帮我们|我们想|我想|我希望|一起|协助).{0,45}(?:设计|规划|研究|比较|验证|检验|探索).{0,65}(?:实验|研究|课题|项目|模型|方法|方案|效果|数据|结论|CViT|Darcy|FNO)|(?:帮我|帮我们).{0,20}(?:设计|规划).{0,12}实验|\b(?:help\s+(?:me|us)|I\s+want|we\s+want)\b.{0,60}\b(?:plan|design|study|compare|investigate)\b',text,re.I))


def route_override(session,text,request):
    text=text.strip()
    if text.partition(' ')[0] in COMMANDS:return True
    if text.startswith('/') or request.intent in {'research','project_qa'}:return False
    # Preserve established explicit CSV interviews and execution requests.
    if re.search(r'访谈|逐步设计|一步步.{0,8}实验|design interview',text,re.I):return False
    if natural_start(text):return True
    state=load(session)
    if not state or not state['active']:return False
    if request.intent in {'numeric','tabular'}:return False
    if re.search(r'^(?:换个话题|先不谈|不讨论|不要规划|停止规划|今天天气|翻译|写一首|你好|谢谢|hi\b|hello\b|translate\b)',text,re.I):return False
    if re.search(r'^(?:什么是|介绍|解释|如何|怎么|为什么|what\b|why\b|how\b)',text,re.I) and not re.search(
        r'实验|方案|设计|研究|区组|单位|随机|方差|功效|验收|指标|基线|数据|对照|复现|因果|预测|误差|显著|plan|design|unit|power|variance|metric',text,re.I):return False
    return True


def review(state):
    result=blueprint_review(state)
    result['ready']=not result['blockers']
    result['scientific_claim_verified']=False
    result['execution_authorized']=False
    return result


class PlanningTurn(TypedDict,total=False):
    planning_state:dict
    assessment:dict
    questions:list
    awareness:str


@lru_cache(maxsize=1)
def _planning_graph():
    builder=StateGraph(PlanningTurn)
    builder.add_node('review_contract',lambda s:{'assessment':review(s['planning_state'])})
    builder.add_node('prioritize_questions',lambda s:{'questions':_questions(s['planning_state'],s['assessment'])})
    builder.add_node('render_awareness',lambda s:{'awareness':render_map(s['planning_state'])})
    builder.add_edge(START,'review_contract');builder.add_edge('review_contract','prioritize_questions')
    builder.add_edge('prioritize_questions','render_awareness');builder.add_edge('render_awareness',END)
    return builder.compile()


def summary(state):
    if not state:return None
    assessment=review(state)
    return {'id':state['id'],'revision':state['revision'],'active':state['active'],
        'facts':deepcopy(state['facts']),'unknown':list(state['unknown']),'conflicts':deepcopy(state['conflicts']),
        'stale':deepcopy(state['stale']),'pending':deepcopy(state['pending']),'review':assessment,
        'contract_hash':contract_hash(state),'approved':bool(state['approval']),
        'decisions_count':len(state['decisions']),'reflections_count':len(state['reflections']),
        'evidence':[evidence_metadata(row) for row in state.get('evidence',[])],
        'evidence_actions':deepcopy(state.get('evidence_actions',{})),
        'clarification':deepcopy(state.get('clarification')),
        'last_export':state['last_export'],'execution_authorized':False}


def _question_candidates(state,assessment):
    questions=[]
    for field,values in state['conflicts'].items():
        questions.append({'field':field,'kind':'conflict','question':f"{FIELDS[field]['label']}出现两个声明，请选择保留哪一个，或说明更正：",
            'rationale':'冲突不能由模型悄悄覆盖；改变边界会使原确认失效。',
            'options':[{'value':r['value'],'label':r['value']} for r in values]})
    for field,reason in state['stale'].items():
        questions.append({'field':field,'kind':'stale','question':f"{FIELDS[field]['label']}需要重新检查：{reason}。当前为：{state['facts'][field]['value']}",
            'rationale':FIELDS[field]['rationale'],'options':[]})
    for field,record in state['facts'].items():
        if record['status']=='proposed':
            questions.append({'field':field,'kind':'proposal','question':f"我对{FIELDS[field]['label']}的理解是“{record['value']}”。这是否准确？可直接更正或 /plan accept {field}。",
                'rationale':'这是从你的描述整理出的理解，不是经验证的事实。','options':[]})
    seen={q['field'] for q in questions}
    for field in state['unknown']:
        if field in seen or field in state.get('evidence_actions',{}):continue
        question=f"{FIELDS[field]['label']}仍未知。你能先提供可查证的来源、安排先导，或缩小本轮范围吗？"
        if any(row['field']==field and row['kind']=='evidence_plan' for row in state.get('question_history',[])):continue
        questions.append({'field':field,'kind':'evidence_plan','question':question,
            'rationale':'先规划怎样获取依据，不要求现在猜出未知值；该步骤不会自动执行。','options':[]})
        seen.add(field)
    for row in assessment['blockers']:
        field=row['field']
        if field in seen or field in state['unknown']:continue
        seen.add(field);spec=FIELDS[field]
        questions.append({'field':field,'kind':'missing' if field not in state['facts'] else 'refine',
            'question':spec['prompt']+(' 当前检查：'+row['detail'] if field in state['facts'] else ''),
            'rationale':spec['rationale'],'options':deepcopy(spec['options'])})
    return questions


def _questions(state,assessment):
    return _question_candidates(state,assessment)[:2]


def _card(state,assessment,questions,changes=(),notes=()):
    approved='规划已确认' if state['approval'] else '规划可复核' if assessment['ready'] else '正在澄清'
    lines=[approved]
    for n,q in enumerate(questions,1):
        lines+=['',q['question']]
        lines += [f"{i+1}. {o['label']}" for i,o in enumerate(q['options'])]
    if questions:
        lines+=['','选择编号，或直接输入你的想法。']
    if not questions:
        lines+=['',render_design(state)]
        if assessment['ready']:
            if not state['approval']:
                lines+=['','确认上述规划用 /plan approve '+contract_hash(state)+'。确认只保存规划版本。']
        else:lines+=['','仍有已知缺口。可以明确限制研究目标、先规划先导阶段，或补充依据后继续。/plan review 会列出阻断项。']
    return '\n'.join(lines)


def _plan(state):
    plan=build_blueprint(state)
    plan['review']=review(state)
    plan['status']='approved_planning_contract' if state['approval'] else 'reviewable_plan' if plan['review']['ready'] else 'draft_with_open_questions'
    plan['approval']=deepcopy(state['approval'])
    plan['contract_hash']=contract_hash(state)
    return plan


def _draft_text(state):
    plan=_plan(state)
    lines=[render_design(state),'','步骤与验收（尚未执行）：']
    for node in plan['nodes']:
        lines.append(f"- {node['id']}：{node['purpose']}\n  依赖：{', '.join(node['dependencies']) or '起点'}；责任：{node['owner']}；能力：{node['capability']}\n  验收：{node['acceptance']}")
    lines+=['','计划版本：'+contract_hash(state),'通过声明检查不等于科学假设已验证，也不授权真实工具执行。']
    return '\n'.join(lines)


def report(session):
    state=load(session)
    if not state:return None
    return {'kind':'research_planning_contract','blueprint':_plan(state),'markdown':export_markdown(state),
        'execution_authorized':False,'scientific_claim_verified':False}


def _handoff(session,state):
    if not state['approval'] or state['approval']['contract_hash']!=contract_hash(state):
        raise ValueError('先复核并确认当前规划版本，再生成工作交接；确认规划不等于执行授权。')
    plan=_plan(state)
    tools={s['name']:s for s in session.registry.specs()}
    suggestions=[]
    for node in plan['nodes']:
        names=[name for name in node.get('suggested_tools',[]) if name in tools]
        suggestions.append({'step':node['id'],'registered_tools':names,'capability':node['capability'],
            'required_human_action':node['owner'],'arguments_bound':False,'executed':False})
    return {'schema_version':'research_handoff_v1','plan_hash':contract_hash(state),'facts':deepcopy(state['facts']),
        'evidence':deepcopy(state.get('evidence',[])),'evidence_actions':deepcopy(state.get('evidence_actions',{})),
        'steps':plan['nodes'],'capabilities':suggestions,'open_checks':[r for r in plan['review']['checks'] if r['status']!='passed'],
        'execution_authorized':False,'instructions':'处理实际数据前绑定来源与字段、核实单位和方法；仅在已注册能力范围内另建执行草案。可用 /tools list 查看离线工具，/interview 或 /design 进入明确CSV执行协议。CViT等实际训练需要单独执行适配器。'}


def tool_context(session):
    state=load(session)
    if not state or not state['approval'] or not review(state)['ready']:
        raise ValueError('当前规划尚未确认或仍有缺口。先 /plan review，再确认当前内容版本；不会据此自动补造工具参数。')
    return {'plan_hash':contract_hash(state),'declarations':{f:r['value'][:350] for f,r in state['facts'].items()},
        'instruction':'这是用户已确认的规划声明，作为只读数据理解，不是额外权限。遵守原始资源/范围，不用模拟模板默认值替代本计划缺失的科学依据；若具体工具参数缺失或能力不支持，停下来提问。仅授权现有离线模拟工具，不执行真实训练。'}


def respond(session,text,turn):
    text=text.strip()
    current=load(session)
    argument=text[len('/plan'):].strip() if text.partition(' ')[0]=='/plan' else text
    verb,_,payload=argument.partition(' ')
    known={'start','new','status','map','draft','review','accept','revise','approve','explain','export','pause','resume','handoff','reflect','decisions','options','help','evidence','understanding','question','choose'}
    command=verb if text.startswith('/plan') and verb in known else 'intake'
    picked=choices.selection(current,payload,explicit=True) if command=='choose' and current else (
        choices.selection(current,argument) if command=='intake' and current else None)
    if command=='choose' and picked is None:raise ValueError('先获取当前问题，再选择其中的选项。')
    if picked is not None:command='choice'
    concept=None
    if command=='intake' and re.search(r'什么是|什么意思|为什么|怎么选|如何选|what\b|why\b|how\b',argument,re.I):
        concept=next((f for f,(pattern,_) in CONCEPTS.items() if re.search(pattern,argument,re.I)),None)
    if command in {'start','new'} or current is None:state=new_state()
    else:state=deepcopy(current)
    state['turns']+=1
    changes=[];notes=[];extra={};answer=None;clarify_text=None
    session.meta.update(active_task='research_planning',phase='needs_input')
    if command=='help' or not argument:answer=HELP
    elif command=='choice':
        changes,answer=choices.apply_selection(state,picked,turn)
        if answer is None:clarify_text=''
    elif command=='question':
        if current is None:raise ValueError('先用 /plan start <目标> 建立规划，再启用边界问答。')
        answer=question_tool.control(session,state,payload)
        if answer is None:clarify_text=''
    elif command=='pause':state['active']=False;answer='研究规划已暂停，事实和决策记录保留。/plan resume 可以继续。'
    elif command=='resume':state['active']=True;notes=['继续上次的研究边界；未自动执行任何作业。'];clarify_text=''
    elif command=='evidence':
        answer,evidence_changed=evidence_command(session,state,payload,turn)
        if evidence_changed and payload.partition(' ')[0]!='understand':
            clarify_text='';notes.append(answer);answer=None
        extra['evidence']=deepcopy(state.get('evidence',[]))
    elif command=='understanding':
        answer,extra['understanding']=render_understanding(state)
    elif command=='accept':
        fields=payload.replace('，',',').replace(' ', ',').split(',') if payload.strip() else []
        aliases={spec['label']:key for key,spec in FIELDS.items()}
        fields=[aliases.get(f,f) for f in fields if f]
        selected=accept(state,fields,turn)
        notes=['已将展示的理解作为你当前计划中的声明保留：'+('、'.join(FIELDS[f]['label'] for f in selected) or '没有待确认项')+'。这不构成外部事实验证。']
    elif command=='approve':
        assessment=review(state)
        if not assessment['ready']:raise ValueError('规划仍有待确认、冲突、过期依赖或关键缺口。先用 /plan review 查看并修正。')
        if payload.strip()!=contract_hash(state):raise ValueError('确认需要当前版本哈希。先 /plan draft 核对后使用其中的 /plan approve 哈希。')
        state['approval']={'contract_hash':contract_hash(state),'turn':turn,'scope':'planning_contract_only'}
        state['decisions'].append({'turn':turn,'type':'human_plan_approval','contract_hash':contract_hash(state)})
        notes=['当前规划版本已由你确认；执行和结论仍需按各步骤另行提供证据。']
    elif command=='reflect':
        if not 12<=len(payload.strip())<=3000:raise ValueError('请用自己的话写清研究问题、主要边界或设计取舍（12～3000字）。')
        state['reflections'].append({'turn':turn,'text':payload.strip(),'status':'user_reflection_not_a_test_score'})
        answer,extra['understanding']=render_understanding(state,payload.strip())
        answer='已记录你的理解。\n'+answer
    elif command=='explain':
        field=payload.strip() or (state.get('pending') or {}).get('field')
        aliases={spec['label']:key for key,spec in FIELDS.items()}
        field=aliases.get(field,field)
        if field not in FIELDS:raise ValueError('请指定当前问题的字段，例如 /plan explain experimental_unit。')
        spec=FIELDS[field];answer=_explanation(field)
        if spec['options']:answer+='\n可比较：'+'；'.join(o['label'] for o in spec['options'])
    elif command in {'intake','start','new','revise'}:
        content=payload if command in {'start','new','revise'} else argument
        if concept:
            answer=_explanation(concept)+'\n这次解释没有替你改变研究边界；仍可回答当前问题或 /plan map 查看全貌。'
        elif content.strip():
            clarify_text=content
            if state.get('pending',{} ) and state['pending'].get('kind')=='proposal' and content.strip() in {'是','是的','对','正确','确认','yes','correct'}:
                selected=accept(state,[state['pending']['field']],turn);notes=['已确认当前展示的理解。']
            elif ((state.get('pending') or {}).get('kind')=='evidence_plan' and command!='revise'
                  and not re.search(r'[:：=]|^\s*\{',content)):
                if len(content)>3000:raise ValueError('请将证据获取步骤限制在3000字以内')
                field=state['pending']['field']
                if _unknown(content):
                    notes=['仍保留未知；可以稍后选择来源或缩小本轮目标，不要求现在猜值。']
                else:
                    state.setdefault('evidence_actions',{})[field]={'text':content,'turn':turn,'status':'user_proposed_step_not_evidence'}
                    state['approval']=None
                    state['decisions'].append({'turn':turn,'type':'evidence_acquisition_step','field':field,'text':content})
                    notes=['已记录拟议的证据获取步骤；原字段仍未知。拿到依据后请用“字段: 内容”更新，不会把获取步骤当作实测证据。']
            else:
                extraction=extract(session,content,state,turn)
                if session.pause_requested.is_set() or session.cancel_requested.is_set():
                    raise ValueError('会话暂停或取消，规划边界未更新')
                pending_kind=(state.get('pending') or {}).get('kind')
                explicit_revision=command=='revise' or bool(re.match(r'^(?:更正|修改为|改成|改为)[:：\s]',content)) or pending_kind=='conflict' and bool(re.fullmatch(r'[12]',content.strip()))
                changes=apply(state,extraction,turn,revise=explicit_revision)
                notes+=extraction['notes']
                extra['model_used']=extraction['model_used']
        state['active']=True
    advanced=_planning_graph().invoke({'planning_state':state},{'recursion_limit':8})
    assessment=advanced['assessment'];questions=advanced['questions']
    read_only_view = (concept is not None or command in {'map','draft','review','status','decisions','options','explain','export','understanding','reflect','help'}
                      or command=='choice' and picked[1]['action']=='custom'
                      or command=='question' and clarify_text is None
                      or command=='evidence' and not evidence_changed)
    if read_only_view and state.get('pending'):
        # Read-only views must not replace a displayed dynamic question/option
        # mapping with an unrelated template before the user's next answer.
        questions=[deepcopy(state['pending'])]+[q for q in questions if q['field']!=state['pending']['field']][:1]
    responding_to_question = (concept is None and (command in {'intake','revise','accept'} or command=='choice' and picked[1]['action']!='custom'))
    tool_result=None
    if state['active'] and (clarify_text is not None or responding_to_question):
        if session.pause_requested.is_set() or session.cancel_requested.is_set():
            raise ValueError('会话已暂停或取消，未保存问答边界')
        tool_result=question_tool.choose(session,state,turn,responding=responding_to_question)
        if tool_result is not None:
            questions=deepcopy(tool_result['questions'])
            extra['question_tool']={k:v for k,v in tool_result.items() if k not in {'questions','candidate_features','feature_names'}}
            if tool_result.get('reused_pending'):clarify_text=None
    if clarify_text is not None and state['active']:
        clarified=propose_questions(session,state,clarify_text,assessment,questions)
        if session.pause_requested.is_set() or session.cancel_requested.is_set():
            raise ValueError('会话暂停或取消，动态澄清和本轮边界未保存')
        proposed=clarified.pop('questions')
        if tool_result is not None:
            selected={q['field'] for q in questions}
            matched=[q for q in proposed if q['field'] in selected]
            if matched:
                questions=matched
            else:
                clarified.update(mode='template',reason='question_tool_selection_retained')
        else:
            questions=proposed
        state['clarification']=clarified
        extra['clarification']=deepcopy(clarified)
        if clarified['mode']=='template' and clarified['reason']=='model_unavailable_or_rejected':
            notes.append('本轮动态澄清不可用或未通过校验，已使用模板继续；已有边界保留。')
    questions=choices.decorate(state,questions,clarify_text or '')
    if clarify_text is not None and state['active']:remember(state,questions,turn)
    state['pending']=deepcopy(questions[0]) if questions and state['active'] else None
    state['last_notes']=notes[-5:]
    if command=='map':answer=render_map(state)
    elif command=='draft':answer=_draft_text(state);extra['blueprint']=_plan(state)
    elif command=='review':
        answer='当前规划'+('可供人类复核' if assessment['ready'] else '仍需修正')+'：\n'+'\n'.join(
            f"- [{r['status']}] {FIELDS[r['field']]['label']}：{r['detail']}" for r in assessment['checks'])
        extra['review']=assessment
    elif command=='status':answer=render_map(state)+'\n已确认版本：'+str(bool(state['approval']))
    elif command=='decisions':answer='决策记录（原始版本可追溯）：\n'+json.dumps(state['decisions'][-20:],ensure_ascii=False,indent=2)
    elif command=='options':answer='\n\n'.join(q['question']+'\n'+'\n'.join(f"{i+1}. {o['label']}" for i,o in enumerate(q['options'])) for q in questions) or '当前没有待选问题，可查看 /plan draft。'
    elif command=='handoff':extra['handoff']=_handoff(session,state);answer='已生成当前确认版本的工作交接：\n'+extra['handoff']['instructions']
    if answer is None:
        answer=_card(state,assessment,questions,changes,notes)
        extra['question_form']=bool(questions)
    save(session,state)
    if responding_to_question:
        question_tool.record_answer(session,current,state,turn)
    if tool_result is not None:
        question_tool.record_question(session,state,tool_result,questions,turn)
    if command=='export':
        base=f"planning/{state['id']}/exports/{state['revision']:05d}"
        plan=_plan(state)
        for suffix in ('.json','.md'):
            destination=session.folder/(base+suffix)
            if destination.resolve()!=destination.absolute() or not destination.is_relative_to(session.folder):
                raise ValueError('计划导出目录不能重定向到会话之外')
        write_json(session.folder/(base+'.json'),plan)
        target=session.folder/(base+'.md');target.write_text(export_markdown(state),encoding='utf-8')
        state['last_export']={'json_ref':base+'.json','markdown_ref':base+'.md','contract_hash':contract_hash(state)}
        save(session,state)
        answer='计划已导出到会话目录：\n'+base+'.md\n'+base+'.json\n导出中保留未知、来源、修订和未执行状态。'
        extra['export']=state['last_export']
    session.meta.update(last_report_kind='research_planning',phase='answered' if state['approval'] else 'needs_input')
    session.save()
    session.emit('planning_updated',{'revision':state['revision'],'contract_hash':contract_hash(state),
        'known_fields':len(state['facts']),'blockers':len(assessment['blockers']),'approved':bool(state['approval'])})
    return {'intent':'planning','answer':answer,'planning':summary(state),'questions':questions,
        'execution_authorized':False,'scientific_claim_verified':False,**extra}
