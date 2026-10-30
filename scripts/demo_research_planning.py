"""Reproducible synthetic planning dialogue; optional ONE real provider request."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'RUT_Science'))
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.ledger import load,contract_hash
from rut_science.science_bot.general.planning.runtime import review

GOAL='我想比较CViT和FNO，看看是否值得继续投入。我目前只有一个小数据集，还没有决定评估方式，希望结果可复现。'
VALUES={
    'research_question':'在声明的合成数据范围内比较CViT与FNO误差，决定是否值得追加验证。',
    'objective_type':'comparison','hypothesis':'候选减基线的relative_l2均值差至少下降0.01。',
    'scope':'只限声明的合成数据版本与固定计算预算，不推广到其他PDE或真实样本。',
    'exclusions':'不宣称广泛泛化或因果机制，也不把本次规划当真实训练结果。',
    'experimental_unit':'一次独立分配的合成训练运行作为实验单位，共享数据与独立性需研究者复核；不把网格点当重复。',
    'factors':'模型两个水平FNO与CViT，主要对比候选减基线；其余训练配置预先固定。',
    'design':'crd','outcomes':'主要指标relative_l2，越低越好，按每个独立运行汇总误差。',
    'baseline':'FNO与候选使用同一数据版本、固定预算和评价协议。',
    'data_source':'仅为合成示例mock://planning-demo，不读取真实数据。正式执行另核实训练/验证/测试版本和泄漏。',
    'sampling':'先做先导再确定训练重复数和方差依据；当前不宣称正式功效保证。',
    'randomization':'独立运行分配顺序抽签随机化，记录seed与实际顺序，执行前复核独立性。',
    'analysis':'估计候选减基线均值差并报告95%置信区间；先导后核对模型与误差假设。',
    'acceptance':'检查所有预定交付；实际意义阈值0.01，报告效应与区间；阴性和不确定结果也交付，预算耗尽或关键依据缺失时停止。',
    'resources':'先导最多8次运行、4小时上限；正式预算由研究者另定，不由Agent增加。',
    'risks':'共享数据、独立性与模型假设未验证，先导失败时人工复核停止。',
    'reproducibility':'记录数据hash、代码git版本、seed、配置、日志与方案偏离。',
    'human_roles':'研究者确认边界和方法，学生负责执行，导师复核并批准结论。',
    'deliverable':'完整可复现的先导方案、区间表模板、决策记录与局限说明。'}


class SyntheticProvider:
    def complete(self,messages,tools=None,role=None):
        return {'content':None,'tool_calls':[{'id':'demo-scope','name':'propose_research_scope','arguments':{
            'updates':[{'field':'research_question','value':GOAL,'quote':GOAL,'status':'declared'},
                       {'field':'scope','value':'先限定在现有小数据集内','quote':'一个小数据集','status':'proposed'}],
            'unknown':[]}}]}
    def mark_validation(self,*args):pass


def main(live=False,output=None):
    session=GeneralSession.create(ROOT/'.local/planning_demo',backend='api',limits={'llm_requests':2,'llm_tokens':12000})
    if not live:session._provider=SyntheticProvider()
    transcript=[]
    def say(text):
        result=session.message(text)
        transcript.append({'user':text,'answer':result['answer'],'planning_error':result.get('planning_error',False),
                           'contract_hash':(result.get('planning') or {}).get('contract_hash')})
        if result.get('planning_error'):raise ValueError(result['answer'])
        return result
    first=say(GOAL)
    smoke={'live_provider_requested':live,'initial_fields':list(load(session)['facts']),
           'model_requests':session.resources()['llm_requests'],'notes':load(session)['last_notes']}
    say('/plan accept')
    for subset in [list(VALUES.items())[i:i+5] for i in range(0,len(VALUES),5)]:
        say('/plan revise '+json.dumps(dict(subset),ensure_ascii=False))
    if load(session)['stale']:
        say('/plan map')
        say('/plan accept '+','.join(load(session)['stale']))
    assert review(load(session))['ready'],review(load(session))['blockers']
    say('/plan draft');say('/plan review')
    say('/plan reflect 我们先验证声明边界内的误差差异；独立性和方差仍需先导，不从单个最佳结果推断广泛泛化。')
    say('/plan approve '+contract_hash(load(session)))
    say('/plan handoff');exported=say('/plan export')['export']
    assert load(session)['approval']
    say('/plan revise resources: 先导最多6次运行、3小时上限；预算不可自行增加。')
    assert not load(session)['approval'] and load(session)['stale']
    say('/plan review')
    output=(output if output is not None else ROOT/'.local/planning_demo/latest_demo').absolute()
    if not output.is_relative_to(ROOT) or output.resolve()!=output:raise ValueError('Demo output must remain in this repository without redirects')
    output.mkdir(parents=True,exist_ok=True)
    (output/'example_plan.md').write_text((session.folder/exported['markdown_ref']).read_text(encoding='utf-8'),encoding='utf-8')
    (output/'example_plan.json').write_text((session.folder/exported['json_ref']).read_text(encoding='utf-8'),encoding='utf-8')
    (output/'example_dialogue.json').write_text(json.dumps({'source':'synthetic_scripted_dialogue_not_human_expert_approval',
        'provider_mode':'one_live_request' if live else 'synthetic_provider_response','turns':transcript},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'demo_verification.json').write_text(json.dumps({'passed':True,'turns':len(transcript),'initial_semantic_smoke':smoke,
        'approval_invalidated_after_budget_change':True,'planning_only':True,'real_scientific_executions':0,
        'actual_tool_attempts':session.meta['tool_attempts'],'session_ref':str(session.folder.relative_to(ROOT)),
        'scope':'Programmatic synthetic user actions; not independent expert review or task-success benchmark'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'smoke':smoke,'turns':len(transcript),'output':str(output),'actual_tool_attempts':session.meta['tool_attempts']},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--live',action='store_true',help='Allow one real request using existing provider/key; remaining dialogue is local structured input')
    p.add_argument('--output',type=Path,help='Optional explicit demo output directory; default is ignored .local storage')
    a=p.parse_args();main(a.live,a.output)
