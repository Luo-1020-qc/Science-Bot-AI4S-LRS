"""Real-provider development probe on a 31-page synthetic fixture, never science."""
import argparse
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'RUT_Science'));sys.dont_write_bytecode=True
from pypdf import PdfReader,PdfWriter
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.ledger import load
from rut_science.science_bot.general.planning.paper_context import chunks
from rut_science.science_bot.general.planning.paper_reading import validate_reading
from rut_science.science_bot.general.planning.synthesis import projection
from rut_science.science_bot.presentation import export_bundle


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--resume',type=Path,help='Reuse the explicitly selected synthetic reading and remaining original budget');args=p.parse_args()
    target=args.output.resolve();target.mkdir(parents=True,exist_ok=False)
    if args.resume:
        session=GeneralSession.restore(args.resume)
    else:
        writer=PdfWriter();reader=PdfReader(ROOT/'examples/papers/synthetic_paper.pdf')
        for index in range(31):writer.add_page(reader.pages[index%2])
        with (target/'synthetic_full_paper.pdf').open('wb') as stream:writer.write(stream)
        session=GeneralSession.create(target/'sessions',backend='offline',workspace=target,
                                     limits={'llm_requests':6,'llm_tokens':200000})
        session.message('/plan '+json.dumps({'research_question':'为用户选定合成论文中的模型A与B比较设计最小复现，先核对命题与条件，本轮只规划不执行。',
            'objective_type':'replication','scope':'仅合成论文所述场景，不外推，不宣称真实复现。',
            'resources':'最多2小时，先核算成本，超限停止，不追加预算。'},ensure_ascii=False))
        selected=session.message('/plan evidence add '+json.dumps({'path':'synthetic_full_paper.pdf','share_with_model':True}))
        if selected.get('planning_error'):raise ValueError(selected['answer'])
    source=load(session)['evidence'][0]
    before_resources=session.resources()
    write(target/'protocol.json',{'synthetic_only':True,'provenance':'31 pages repeat the two-page engineering fixture; not a real scientific article or independent quality evaluation.',
        'pdf_sha256':source['sha256'],'resumed':bool(args.resume),'previous_resources':before_resources,
        'physical_pages':len(source['pages']),'text_bytes':len(source['text'].encode()),'chunks':len(chunks(source)),
        'request_cap':6,'token_cap':200000,'automatic_retries':0,
        'runtime_manifest':json.loads((ROOT/'docs/integration/full_pdf_2026-10-31/runtime_manifest.json').read_text(encoding='utf-8'))})
    session.meta['backend']='api';session.save()
    # Development-only capture of synthetic responses, never request headers.
    from rut_science.science_bot.general import provider as transport
    original_open=transport.urllib.request.urlopen
    response_index=[0]
    def diagnostic_open(request,**kwargs):
        with original_open(request,**kwargs) as response:raw=response.read()
        response_index[0]+=1
        (target/('synthetic_response_'+str(response_index[0])+'.json')).write_bytes(raw)
        return io.BytesIO(raw)
    transport.urllib.request.urlopen=diagnostic_open
    read_result=session.message('/plan evidence understand '+source['id'])
    source=load(session)['evidence'][0];reading=source.get('interpretation')
    if reading:validate_reading(reading,source)
    covered=(reading or {}).get('coverage') or {}
    complete=bool(covered) and covered.get('completed_chunks')==covered.get('total_chunks')
    print(json.dumps({'stage':'reading','complete':complete,'coverage':covered,'resources':session.resources()},ensure_ascii=False),flush=True)
    plan_result=session.message('/plan synthesize refresh' if args.resume else '/plan synthesize') if complete else None
    state=load(session);plan=projection(state);content=plan.get('content') or {}
    export_bundle(session)
    result={'checked_utc':datetime.now(timezone.utc).isoformat(),'synthetic_only':True,'physical_pages':len(source['pages']),
        'full_extraction':source['start_page']==1 and source['end_page']==source['page_count']==31,
        'reading_complete':complete,'coverage':covered,'grounded_items':len((reading or {}).get('items',[])),
        'last_page_has_grounded_point':any(i['page']==31 for i in (reading or {}).get('items',[])),
        'rejected_items':len((reading or {}).get('rejected_items',[])),
        'read_error':read_result.get('answer') if read_result.get('planning_error') else None,
        'plan_status':plan['status'],'plan_reason':plan.get('reason'),'concrete_steps':len(content.get('steps',[])),
        'paper_cited':any(r['source']=='evidence' for r in content.get('references',[])),
        'resources':session.resources(),'this_run_requests':session.resources()['llm_requests']-before_resources['llm_requests'],
        'this_run_tokens':session.resources()['llm_tokens']-before_resources['llm_tokens'],
        'automatic_retries':0,'scientific_executions':0,'training_runs':0,
        'independent_human_quality_evaluations':0,'session':str(session.folder.relative_to(ROOT))}
    write(target/'results.json',result)
    write(target/'trajectory.json',{'read':read_result,'plan':plan_result})
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if complete and plan['status']=='current' else 1


if __name__=='__main__':raise SystemExit(main())
