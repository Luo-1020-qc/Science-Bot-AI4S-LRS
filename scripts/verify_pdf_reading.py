"""Current PDF integration, frozen history, full offline checks and real-call receipt."""
import argparse
from datetime import datetime,timezone
import io
import json
import sys
import subprocess
import unittest
from integrity import ROOT,PDF_RECORD,PDF_HOST_FILES,PDF_NEW_FILES,sha,check_project

sys.path.insert(0,str(ROOT/'RUT_Science'));sys.dont_write_bytecode=True
RECORD=ROOT/PDF_RECORD
SUPPORT={'scripts/integrity.py','scripts/test_integrity.py','scripts/verify_session_history.py','scripts/test_session_history_ui.cjs'}


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def audit():
    before=read(RECORD/'before_snapshot.json');changed=[]
    for name,h in before['files'].items():
        if not (ROOT/name).is_file():raise ValueError('Previous source or evidence missing: '+name)
        if sha(ROOT/name)!=h:
            if name not in PDF_HOST_FILES|SUPPORT:raise ValueError('Unrelated source/evidence changed: '+name)
            changed.append(name)
    return before,changed


def finalize():
    before,_=audit()
    write(RECORD/'authorized_source_changes.json',{'files':{n:{'before_sha256':before['files'][n],
        'sha256':sha(ROOT/n),'reason':'User requested explicit PDF reading and LLM meaning extraction through the existing Harness.'} for n in sorted(PDF_HOST_FILES)}})
    write(RECORD/'runtime_manifest.json',{'sha256':{n:sha(ROOT/n) for n in sorted(PDF_HOST_FILES|PDF_NEW_FILES)}})
    check_project()


def inputs():
    paths=[]
    for folder in ('RUT_Science/rut_science/science_bot','RUT_Science/tests','scripts'):
        paths += [p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in {'.py','.json','.js','.cjs','.html','.css'} and '__pycache__' not in p.parts]
    paths += [ROOT/n for n in PDF_HOST_FILES|PDF_NEW_FILES]
    paths += [RECORD/n for n in ('before_snapshot.json','authorized_source_changes.json','runtime_manifest.json','initial_live.json','second_live.json','live.json')]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(paths))}


def run_tests():
    before=inputs();groups={};log=[]
    for name,folder in [('application','RUT_Science/tests'),('integrity_and_evaluation','scripts')]:
        stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=1).run(unittest.TestLoader().discover(str(ROOT/folder),pattern='test*.py'))
        groups[name]={'run':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
        log.append(name+'\n'+stream.getvalue());print(json.dumps({name:groups[name]}),flush=True)
    ui=subprocess.run(['node',str(ROOT/'scripts/test_session_history_ui.cjs')],capture_output=True,text=True,timeout=30)
    groups['mock_dom']={'passed':ui.returncode==0,'result':json.loads(ui.stdout) if ui.returncode==0 else ui.stderr[-1500:]}
    if before!=inputs():raise ValueError('Inputs changed during tests')
    local=ROOT/'.local/checks/pdf_reading_tests.log';local.parent.mkdir(parents=True,exist_ok=True)
    local.write_text('\n'.join(log),encoding='utf-8')
    receipt={'passed':all(g['passed'] for g in groups.values()),'groups':groups,'source_sha256':before,
        'checked_utc':datetime.now(timezone.utc).isoformat(),'mode':'offline_unittest_mocked_providers_real_local_pdf_parser'}
    write(RECORD/'tests.json',receipt)
    if not receipt['passed']:raise ValueError('Tests failed: '+str(local))


def verify():
    before,changed=audit();protection=check_project();tests=read(RECORD/'tests.json')
    if not tests['passed'] or tests['source_sha256']!=inputs():raise ValueError('Current PDF test evidence stale; use --run-tests')
    import pypdf
    from rut_science.science_bot.general.planning.paper_reading import validate_reading
    from verify_interfaces import check_examples
    from verify_branding import asset_checks
    live=read(RECORD/'live.json');fixture=ROOT/'examples/papers/synthetic_paper.pdf'
    reader=pypdf.PdfReader(fixture)
    source={'sha256':sha(fixture),'pages':[{'page':i+1,'text':p.extract_text().strip()} for i,p in enumerate(reader.pages)]}
    if not live['passed'] or live['fixture_sha256']!=source['sha256'] or live['plan_facts']:
        raise ValueError('Live PDF scope or provenance mismatch')
    validate_reading(live['interpretation'],source)
    requests=sum(read(RECORD/n)['resources']['llm_requests'] for n in ('initial_live.json','second_live.json','live.json'))
    return {'passed':True,'checked_utc':datetime.now(timezone.utc).isoformat(),'integrity':protection,'tests':tests['groups'],
        'authorized_changed_files':changed,'prior_files_unchanged':len(before['files'])-len(changed),
        'all_prior_integration_json_unchanged':True,'examples':check_examples(),'assets':asset_checks(),
        'pdf_parser_version':pypdf.__version__,'live_synthetic_diagnostic':{'requests_including_failed_trials':requests,
            'final_trial_requests':live['resources']['llm_requests'],'accepted_points':len(live['interpretation']['items']),
            'rejected_points':len(live['interpretation'].get('rejected_items',[])),'physical_pages':[1,2],
            'quotes_revalidated':True,'expert_semantics_reviewed':False},
        'this_verification_model_requests':0,'real_scientific_executions':0,'training_runs':0,
        'pdf_fixture_pages_visually_inspected':2,'browser_visual_qa':False,
        'limitations':['Text-layer PDF parsing only; scanned/image pages require OCR.',
            'Grounding checks do not prove semantic correctness or scientific validity.',
            'Synthetic fixture was used during development, not an independent benchmark.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--finalize',action='store_true');p.add_argument('--run-tests',action='store_true')
    p.add_argument('--run-checks',dest='run_tests',action='store_true',help=argparse.SUPPRESS);args=p.parse_args()
    if args.finalize:finalize()
    if args.run_tests:run_tests()
    result=verify();write(RECORD/'verification.json',result);print(json.dumps(result,ensure_ascii=False));return result


if __name__=='__main__':main()
