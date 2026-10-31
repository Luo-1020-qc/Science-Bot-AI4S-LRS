"""Two bounded real-provider checks; synthetic goals only, no retries or experiments."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'RUT_Science'));sys.dont_write_bytecode=True
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.ledger import load
from rut_science.science_bot.general.planning.runtime import review

CASES=[
    {'id':'prediction_continuation','inputs':[
        '请帮我做设备故障预测的实验计划，比较逻辑回归与树模型。本轮只规划，不执行。',
        '只限本校实验台的合成设备日志，不做因果结论，也不外推其他设备。训练与验证按设备来源隔离，最终测试另留设备。']},
    {'id':'material_budget_correction','inputs':[
        '想比较两种吸附材料，请通过选项帮我做实验计划。后续最多六次运行、两小时上限，本轮不执行。',
        '更正：经费缩减了，后续最多两次运行、一小时上限，之前六次运行的说法作废。请重查受影响的样本与验收，不要沿用旧确认。']}
]


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--case',choices=[c['id'] for c in CASES]);p.add_argument('--request-cap',type=int,choices=[3,4],default=4);args=p.parse_args()
    selected=[c for c in CASES if not args.case or c['id']==args.case]
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'cases.json',{'max_requests':8,'max_accounted_tokens':24000,'automatic_retries':0,
                                  'provenance':'Implementer-authored synthetic smoke, not independent quality evaluation','cases':CASES})
    results=[]
    for case in selected:
        folder=args.output/case['id'];folder.mkdir()
        session=GeneralSession.create(folder/'sessions',backend='api',limits={'llm_requests':args.request_cap,'llm_tokens':12000,'read_bytes':24000,'tool_calls':40})
        trajectory=[]
        for text in case['inputs']:
            started=time.monotonic();result=session.message(text)
            state=load(session)
            trajectory.append({'input':text,'seconds':round(time.monotonic()-started,3),
                               'result':result,'state':state,'resources':session.resources()})
            write(folder/'trajectory.json',trajectory)
            print(json.dumps({'case':case['id'],'turn':len(trajectory),'intent':result['intent'],
                              'resources':session.resources()},ensure_ascii=False),flush=True)
        state=load(session)
        resources=session.resources()
        initial=trajectory[0]['state']['facts'].get('research_question',{}).get('value')
        row={'id':case['id'],'planning_turns':sum(t['result']['intent']=='planning' for t in trajectory),
             'research_question_retained':state['facts'].get('research_question',{}).get('value')==initial,
             'research_question_conflict':'research_question' in state['conflicts'],
             'feedback_visible':all(bool(t['result'].get('update_feedback',{}).get('text')) for t in trajectory),
             'budget_after':state['facts'].get('resources',{}).get('value'),
             'scope_present':'scope' in state['facts'],'resources':resources,
             'ready':review(state)['ready'],'scientific_claim_verified':False,'execution_authorized':False,
             'numeric_or_tabular_created':bool(session.numeric or session.tabular)}
        if case['id']=='material_budget_correction':
            row['literal_new_budget_adopted']=row['budget_after']=='后续最多两次运行、一小时上限'
        write(folder/'result.json',row);results.append(row)
    result={'checked_utc':datetime.now(timezone.utc).isoformat(),'cases':results,
            'requests':sum(c['resources']['llm_requests'] for c in results),
            'accounted_tokens':sum(c['resources']['llm_tokens'] for c in results),
            'automatic_retries':0,'human_quality_rated':False,'real_experiments':0}
    assert result['requests']<=8 and result['accounted_tokens']<=24000
    write(args.output/'results.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
