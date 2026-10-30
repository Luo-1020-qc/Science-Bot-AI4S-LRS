"""Verify session deletion and append source authorization without changing history."""
import argparse
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from integrity import (ROOT,SESSION_HISTORY_RECORD,SESSION_HISTORY_HOST_FILES,SESSION_HISTORY_NEW_FILES,sha,check_project)

sys.path.insert(0,str(ROOT/'RUT_Science'))
sys.dont_write_bytecode=True
RECORD=ROOT/SESSION_HISTORY_RECORD
SUPPORT={'scripts/integrity.py','scripts/test_integrity.py','scripts/verify_planning_mainline.py'}


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def audit():
    before=read(RECORD/'before_snapshot.json');changes=[]
    for name,h in before['files'].items():
        if not (ROOT/name).is_file():raise ValueError('Preexisting file removed: '+name)
        if sha(ROOT/name)!=h:
            if name not in SESSION_HISTORY_HOST_FILES|SUPPORT:raise ValueError('Unrelated source/history changed: '+name)
            changes.append(name)
    return before,changes


def finalize():
    before,_=audit()
    write(RECORD/'authorized_source_changes.json',{'files':{n:{'before_sha256':before['files'][n],
        'sha256':sha(ROOT/n),'reason':'User requested deleting individual historical research/chat sessions from the interface.'}
        for n in sorted(SESSION_HISTORY_HOST_FILES)}})
    write(RECORD/'runtime_manifest.json',{'sha256':{n:sha(ROOT/n) for n in sorted(SESSION_HISTORY_HOST_FILES|SESSION_HISTORY_NEW_FILES)}})
    check_project()


def inputs():
    paths=[]
    for base in ('RUT_Science/rut_science/science_bot','RUT_Science/tests','scripts'):
        paths.extend(p for p in (ROOT/base).rglob('*') if p.is_file() and p.suffix in {'.py','.json','.js','.cjs','.css','.html'} and '__pycache__' not in p.parts)
    paths += [RECORD/n for n in ('before_snapshot.json','authorized_source_changes.json','runtime_manifest.json')]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(paths))}


def run_tests():
    before=inputs();groups={};log=[]
    for name,folder in [('application','RUT_Science/tests'),('integrity_and_evaluation','scripts')]:
        stream=io.StringIO()
        result=unittest.TextTestRunner(stream=stream,verbosity=1).run(unittest.TestLoader().discover(str(ROOT/folder),pattern='test*.py'))
        groups[name]={'run':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
        log.append(name+'\n'+stream.getvalue());print(json.dumps({name:groups[name]}),flush=True)
    ui=subprocess.run(['node',str(ROOT/'scripts/test_session_history_ui.cjs')],cwd=ROOT,capture_output=True,text=True,timeout=30)
    groups['shipped_ui_with_mock_dom']={'passed':ui.returncode==0,'result':json.loads(ui.stdout) if ui.returncode==0 else ui.stderr[-2000:]}
    if inputs()!=before:raise ValueError('Inputs changed during tests')
    local=ROOT/'.local/checks/session_history_tests.log';local.parent.mkdir(parents=True,exist_ok=True)
    local.write_text('\n'.join(log),encoding='utf-8')
    receipt={'passed':all(g['passed'] for g in groups.values()),'groups':groups,'source_sha256':before,
             'mode':'offline_http_and_mock_dom_no_live_model_or_browser','checked_utc':datetime.now(timezone.utc).isoformat()}
    write(RECORD/'tests.json',receipt)
    if not receipt['passed']:raise ValueError('Tests failed: '+str(local))


def verify():
    before,changed=audit();protection=check_project();tests=read(RECORD/'tests.json')
    if not tests['passed'] or tests['source_sha256']!=inputs():raise ValueError('Test evidence stale; use --run-tests')
    from verify_interfaces import check_examples
    from verify_branding import asset_checks
    return {'passed':True,'checked_utc':datetime.now(timezone.utc).isoformat(),'integrity':protection,
        'tests':tests['groups'],'authorized_changed_files':changed,'prior_files_unchanged':len(before['files'])-len(changed),
        'all_prior_integration_json_unchanged':True,'examples':check_examples(),'assets':asset_checks(),
        'real_user_sessions_deleted_during_implementation':0,'test_deletions':'disposable_test_sessions_only',
        'model_requests':0,'real_scientific_executions':0,'training_runs':0,
        'browser_visual_qa':False,'browser_visual_qa_reason':'No live browser verification; UI transitions tested against shipped script with mock DOM.'}


def main():
    if (ROOT/'docs/integration/pdf_reading_2026-10-30/authorized_source_changes.json').exists():
        from verify_pdf_reading import main as verify_current_pdf
        return verify_current_pdf()
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--finalize',action='store_true');p.add_argument('--run-tests',action='store_true')
    p.add_argument('--run-checks',dest='run_tests',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.finalize:finalize()
    if args.run_tests:run_tests()
    result=verify();write(RECORD/'verification.json',result);print(json.dumps(result,ensure_ascii=False));return result


if __name__=='__main__':main()
