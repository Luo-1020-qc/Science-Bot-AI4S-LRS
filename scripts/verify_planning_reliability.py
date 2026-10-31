"""Verify the three planning deliveries and byte-identical interface style/layout."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
from integrity import (ROOT,RELIABILITY_RECORD,RELIABILITY_HOST_FILES,RELIABILITY_NEW_FILES,
                       RELIABILITY_STYLE_FILES,sha,check_project)

RECORD=ROOT/RELIABILITY_RECORD
SUPPORT={'scripts/integrity.py','scripts/verify_pdf_reading.py','scripts/test_integrity.py','scripts/test_session_history_ui.cjs'}


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def inline_style_hash(text):
    return hashlib.sha256('\n'.join(re.findall(r'<style[^>]*>(.*?)</style>',text,re.S)).encode('utf-8')).hexdigest()


def audit():
    before=read(RECORD/'before_snapshot.json');changed=[]
    for name,value in before['files'].items():
        if not (ROOT/name).is_file():raise ValueError('Prior source missing: '+name)
        if sha(ROOT/name)!=value:
            if name not in RELIABILITY_HOST_FILES|SUPPORT:raise ValueError('Unrelated source changed: '+name)
            changed.append(name)
    if set(before['style_files'])!=RELIABILITY_STYLE_FILES:raise ValueError('Style scope mismatch')
    for name,value in before['style_files'].items():
        if sha(ROOT/name)!=value:raise ValueError('Page layout/style changed: '+name)
    if inline_style_hash((ROOT/'RUT_Science/rut_science/science_bot/presentation.py').read_text(encoding='utf-8'))!=before['delivery_inline_style_sha256']:
        raise ValueError('Delivery inline style changed')
    return before,changed


def finalize():
    before,_=audit()
    write(RECORD/'authorized_source_changes.json',{'files':{n:{'before_sha256':before['protected_sha256'][n],
        'sha256':sha(ROOT/n),'reason':'User requested reliable planning entry, explicit update feedback and trustworthy review; preserve all page styles and layout.'}
        for n in sorted(RELIABILITY_HOST_FILES)}})
    write(RECORD/'runtime_manifest.json',{'sha256':{n:sha(ROOT/n) for n in sorted(RELIABILITY_HOST_FILES|RELIABILITY_NEW_FILES)}})
    check_project()


def inputs():
    paths=[]
    for base in ('RUT_Science/rut_science/science_bot','RUT_Science/tests','scripts'):
        paths += [p for p in (ROOT/base).rglob('*') if p.is_file() and p.suffix in {'.py','.json','.js','.cjs','.html','.css'} and '__pycache__' not in p.parts]
    paths += [RECORD/n for n in ('before_snapshot.json','authorized_source_changes.json','runtime_manifest.json')]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(paths))}


def run_tests():
    before=inputs();base=ROOT/'.local/planning_reliability_20261030'/('full_'+uuid.uuid4().hex[:8]);groups={}
    worker=ROOT/'RUT_Science/research/harness_evaluation_v1/test_worker.py'
    for name,folder in [('application','RUT_Science/tests'),('integrity_and_scoring','scripts')]:
        result=subprocess.run([sys.executable,'-B',str(worker),'--root',str(ROOT),'--folder',folder,'--output',str(base/name)],
                              cwd=ROOT,text=True,capture_output=True,encoding='utf-8',timeout=600)
        groups[name]=read(base/name/'results.json')
        print(json.dumps({'suite':name,'run':groups[name]['run'],'passed':groups[name]['passed'],
                          'skipped':len(groups[name]['skipped'])}),flush=True)
    ui=subprocess.run(['node',str(ROOT/'scripts/test_session_history_ui.cjs')],cwd=ROOT,text=True,capture_output=True,timeout=30)
    groups['ui']={'passed':ui.returncode==0,'result':json.loads(ui.stdout) if ui.returncode==0 else ui.stderr[-2000:]}
    if before!=inputs():raise ValueError('Sources changed during full verification')
    receipt={'passed':all(r['passed'] for r in groups.values()),'groups':groups,'source_sha256':before,
             'log_directory':str(base.relative_to(ROOT)),'checked_utc':datetime.now(timezone.utc).isoformat(),
             'model_requests':0,'real_scientific_executions':0,'training_runs':0}
    write(RECORD/'tests.json',receipt)
    if not receipt['passed']:raise ValueError('Regression failure; inspect '+str(base))


def verify():
    before,changed=audit();protection=check_project();tests=read(RECORD/'tests.json')
    if not tests['passed'] or tests['source_sha256']!=inputs():raise ValueError('Current tests stale; use --run-tests')
    return {'passed':True,'checked_utc':datetime.now(timezone.utc).isoformat(),'integrity':protection,
            'tests':{k:{n:v for n,v in row.items() if n not in {'failures','errors','skipped'}} for k,row in tests['groups'].items()},
            'authorized_changed_files':changed,'html_and_css_files_unchanged':len(before['style_files']),
            'delivery_inline_style_unchanged':True,'prior_integration_evidence_unchanged':True,
            'provider_configuration_and_weights_unchanged':True,'this_verification_model_requests':0,
            'real_scientific_executions':0,'training_runs':0,'browser_visual_qa':False,
            'limitations':['Method checks flag bounded declaration contradictions; no scientific-validity certification.',
                           'New phrasing tests are implementer-authored regressions, not independent human evaluation.']}


def main():
    if (ROOT/'docs/integration/plan_synthesis_2026-10-31/authorized_source_changes.json').exists():
        from verify_plan_synthesis import main as current_main
        return current_main()
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--finalize',action='store_true');p.add_argument('--run-tests',action='store_true')
    p.add_argument('--run-checks',dest='run_tests',action='store_true',help=argparse.SUPPRESS);args=p.parse_args()
    if args.finalize:finalize()
    if args.run_tests:run_tests()
    result=verify();write(RECORD/'verification.json',result);print(json.dumps(result,ensure_ascii=False));return result


if __name__=='__main__':main()
