"""Bounded synthetic model checks; generated plans are not expert quality scores."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'RUT_Science'));sys.dont_write_bytecode=True
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.ledger import load
from rut_science.science_bot.general.planning.synthesis import projection
from rut_science.science_bot.presentation import export_bundle

CASES=[
    {'id':'model_comparison','inputs':[
        '/plan 我想比较模型甲和模型乙在同一份合成二维物理场数据上的预测误差，决定下一步是否继续研究。只有2小时计算预算，模型是否已经训练好还没核实。本轮只规划，不执行。',
        '/plan revise resources: 最多1小时，先核算耗时；超限停止，不追加运行。']},
    {'id':'minimal_replication','inputs':[
        '/plan 我想为合成论文中的模型A与B比较制定最小复现方案，先核对论文命题和条件再决定实验。最多2小时，不执行，不宣称已经复现。',
        '/plan evidence add {"path":"examples/papers/synthetic_paper.pdf","start_page":1,"end_page":2,"share_with_model":true}']}
]


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepared',action='store_true',help='Prepare explicit synthetic facts offline, then generate with remaining real-call budget')
    p.add_argument('--previous',type=Path,help='Previous smoke results count toward the same six-request/token cap');args=p.parse_args()
    previous=json.loads(args.previous.read_text(encoding='utf-8')) if args.previous else {'requests':0,'accounted_tokens':0}
    cases=CASES if not args.prepared else [
        {'id':'model_comparison','inputs':['/plan synthesize','/plan revise resources: 最多1小时，先核算耗时；超限停止，不追加运行。']},
        {'id':'minimal_replication','inputs':['/plan synthesize']}]
    args.output.mkdir(parents=True,exist_ok=False)
    source={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT/'RUT_Science/rut_science/science_bot').rglob('*') if p.is_file() and p.suffix in {'.py','.js','.html','.css','.json'} and '__pycache__' not in p.parts}
    write(args.output/'cases.json',{'request_cap':6,'token_cap':32000,'automatic_retries':0,
                                  'provenance':'Implementer-authored synthetic development probes, not independent expert evaluation',
                                  'cases':cases,'source_sha256':source,'prepared_offline':args.prepared,
                                  'previous_requests':previous['requests'],'previous_tokens':previous['accounted_tokens']})
    results=[]
    for case in cases:
        folder=args.output/case['id'];folder.mkdir()
        remaining_requests=6-previous['requests']-sum(r['resources']['llm_requests'] for r in results)
        remaining_tokens=32000-previous['accounted_tokens']-sum(r['resources']['llm_tokens'] for r in results)
        session=GeneralSession.create(folder/'sessions',backend='offline' if args.prepared else 'api',workspace=ROOT,
            limits={'llm_requests':min(2 if args.prepared else 3,remaining_requests),
                    'llm_tokens':remaining_tokens if args.prepared else min(16000,remaining_tokens),'read_bytes':24000,'tool_calls':40})
        if args.prepared:
            goal=('比较模型甲乙在合成二维场上的误差与成本，以决定是否继续研究，模型是否已训练待核实。' if case['id']=='model_comparison' else
                  '复现用户选定合成论文中模型A与B的配对比较，先核对原文命题和条件，不宣称已复现。')
            session.message('/plan '+json.dumps({'research_question':goal,'objective_type':'comparison' if case['id']=='model_comparison' else 'replication',
                'scope':'只限所选合成场景；本轮交付规划，不执行。','resources':'最多2小时，资源到上限停止'},ensure_ascii=False))
            if case['id']=='minimal_replication':session.message(CASES[1]['inputs'][1])
            session.meta['backend']='api';session.save()
        trajectory=[]
        for text in case['inputs']:
            started=time.monotonic();result=session.message(text);state=load(session)
            trajectory.append({'input':text,'seconds':round(time.monotonic()-started,3),
                               'result':result,'state':state,'resources':session.resources()})
            write(folder/'trajectory.json',trajectory)
            print(json.dumps({'case':case['id'],'turn':len(trajectory),'synthesis':projection(state)['status'],
                              'reason':projection(state).get('reason'),'resources':session.resources()},ensure_ascii=False),flush=True)
        view=projection(load(session));content=view.get('content') or {}
        export_bundle(session)
        row={'id':case['id'],'status':view['status'],'reason':view.get('reason'),
             'concrete_steps':len(content.get('steps',[])),
             'all_steps_have_actions_inputs_outputs_acceptance':bool(content.get('steps')) and all(
                 all(s.get(k) for k in ('action','inputs','output','acceptance')) for s in content['steps']),
             'has_comparison_matrix':bool(content.get('matrix')),'has_alternative':bool(content.get('alternatives')),
             'has_uncertainty_and_stop_rule':bool(content.get('analysis')) and bool(content.get('stop_rule')),
             'references':content.get('references',[]),'resources':session.resources(),
             'no_experiment_session_created':not session.numeric and not session.tabular,
             'all_steps_unexecuted':True,'human_quality_rated':False}
        write(folder/'result.json',row)
        if content:
            (folder/'draft.txt').write_text(session.message('/plan draft')['answer'],encoding='utf-8')
        results.append(row)
    summary={'checked_utc':datetime.now(timezone.utc).isoformat(),'cases':results,
             'requests':sum(r['resources']['llm_requests'] for r in results),
             'accounted_tokens':sum(r['resources']['llm_tokens'] for r in results),
             'automatic_retries':0,'real_experiments':0,'training_runs':0,'human_quality_rated':False}
    summary['cumulative_requests']=summary['requests']+previous['requests']
    summary['cumulative_accounted_tokens']=summary['accounted_tokens']+previous['accounted_tokens']
    assert summary['cumulative_requests']<=6 and summary['cumulative_accounted_tokens']<=32000
    write(args.output/'results.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
