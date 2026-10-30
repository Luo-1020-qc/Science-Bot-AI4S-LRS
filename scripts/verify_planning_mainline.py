"""Current offline verification; append an authorized layer, preserve old evidence."""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

from integrity import ROOT, MAINLINE_RECORD, MAINLINE_HOST_FILES, MAINLINE_NEW_FILES, sha, check_project

sys.path.insert(0,str(ROOT/'RUT_Science'))
sys.dont_write_bytecode=True
RECORD=ROOT/MAINLINE_RECORD
SUPPORT_CHANGES=frozenset({'scripts/integrity.py','scripts/check_repository.py','scripts/test_integrity.py',
    'scripts/verify_context_choices.py','RUT_Science/tests/test_workbench_http.py','README.md','CONTRIBUTING.md','CHANGELOG.md',
    'docs/HARNESS_PLANNING.md','docs/USAGE.md','docs/REPRODUCIBILITY.md','docs/ARCHITECTURE.md'})


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def audit_before():
    before=read(RECORD/'before_snapshot.json')
    allowed=MAINLINE_HOST_FILES|SUPPORT_CHANGES
    changed=[]
    for name,h in before['files'].items():
        path=ROOT/name
        if not path.is_file():raise ValueError('Prior source or evidence missing: '+name)
        if sha(path)!=h:
            if name not in allowed:raise ValueError('Change outside current authorized work: '+name)
            changed.append(name)
    return before,changed


def finalize():
    before,changed=audit_before()
    reason='User authorized the agreed mainline package: full conversation acceptance cases, rule baseline, direct experimental-design delivery and targeted directory migration.'
    write(RECORD/'authorized_source_changes.json',{'files':{n:{'before_sha256':before['files'][n],
        'sha256':sha(ROOT/n),'reason':reason} for n in sorted(MAINLINE_HOST_FILES)}})
    write(RECORD/'runtime_manifest.json',{'sha256':{n:sha(ROOT/n) for n in sorted(MAINLINE_HOST_FILES|MAINLINE_NEW_FILES)}})
    write(RECORD/'support_source_changes.json',{'files':{n:{'before_sha256':before['files'][n],
        'sha256':sha(ROOT/n),'reason':reason} for n in changed if n in SUPPORT_CHANGES}})
    check_project()


def inputs():
    paths=[]
    for folder,patterns in [('RUT_Science/rut_science/science_bot',('*.py','*.json','*.html','*.css','*.js')),
                            ('RUT_Science/tests',('test*.py',)),('scripts',('*.py',))]:
        for pattern in patterns:paths.extend(p for p in (ROOT/folder).rglob(pattern) if '__pycache__' not in p.parts)
    paths.extend((ROOT/'docs/evaluation/mainline_2026-10-30').glob('tasks*.json'))
    paths += [RECORD/n for n in ('before_snapshot.json','authorized_source_changes.json','runtime_manifest.json','support_source_changes.json')]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(paths))}


def run_tests():
    before=inputs();groups={};logs=[]
    for name,folder in [('application','RUT_Science/tests'),('integrity_and_evaluation','scripts')]:
        stream=io.StringIO();started=time.monotonic()
        suite=unittest.TestLoader().discover(str(ROOT/folder),pattern='test*.py')
        result=unittest.TextTestRunner(stream=stream,verbosity=1).run(suite)
        groups[name]={'run':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),
            'errors':len(result.errors),'skipped':len(result.skipped),'seconds':round(time.monotonic()-started,3)}
        logs.append(name+'\n'+stream.getvalue());print(json.dumps({name:groups[name]}),flush=True)
    if before!=inputs():raise ValueError('Source changed during regression')
    write(RECORD/'full_tests.json',{'passed':all(g['passed'] for g in groups.values()),'groups':groups,
        'source_sha256':before,'checked_utc':datetime.now(timezone.utc).isoformat(),
        'mode':'offline_unittest_mocked_providers_no_real_api'})
    local=ROOT/'.local/checks/mainline_full_tests.log';local.parent.mkdir(parents=True,exist_ok=True)
    local.write_text('\n'.join(logs),encoding='utf-8')
    if not all(g['passed'] for g in groups.values()):raise ValueError('Regression failed: '+str(local))


def verify():
    before,changed=audit_before();protected=check_project()
    tests=read(RECORD/'full_tests.json')
    if not tests['passed'] or tests['source_sha256']!=inputs():
        raise ValueError('Current test evidence stale; run --run-tests')
    from verify_interfaces import check_examples
    from verify_branding import asset_checks
    from evaluate_planning_mainline import load_cases
    load_cases()
    evaluation=read(ROOT/'docs/evaluation/mainline_2026-10-30/baseline/results.json')
    for name,h in evaluation['source_sha256'].items():
        if sha(ROOT/name)!=h:raise ValueError('Baseline source changed: '+name)
    if (evaluation['expected_outcomes_met']!=10 or evaluation['host_violations']!=0
            or evaluation['model_requests']!=0 or evaluation['human_participants']!=0):
        raise ValueError('Offline baseline acceptance or scope mismatch')
    baseline=ROOT/'docs/evaluation/mainline_2026-10-30/baseline'
    for case in evaluation['cases']:
        if read(baseline/case['id']/'result.json')!=case:raise ValueError('Case summary changed: '+case['id'])
        for name,h in case['artifacts'].items():
            if sha(baseline/case['id']/name)!=h:raise ValueError('Baseline artifact changed: '+case['id']+'/'+name)
    checked_js=subprocess.run(['node','--check',str(ROOT/'RUT_Science/rut_science/science_bot/workbench_assets/dist/app.js')],
                              capture_output=True,text=True,timeout=30)
    if checked_js.returncode:raise ValueError('Workbench JavaScript syntax check failed')
    return {'passed':True,'checked_utc':datetime.now(timezone.utc).isoformat(),'integrity':protected,
        'regression':tests['groups'],'prior_files_checked':len(before['files']),
        'prior_files_unchanged':len(before['files'])-len(changed),'authorized_changed_files':changed,
        'migrated_protected_files':len(before['directory_migration']),
        'all_prior_integration_json_unchanged':True,'retained_weights_changed':False,
        'examples':check_examples(),'assets':asset_checks(),'javascript_syntax':True,
        'offline_baseline':{k:evaluation[k] for k in ('case_count','expected_outcomes_met','reviewable_designs',
            'justified_blocked_drafts','automatic_design_readouts','unnecessary_questions','host_violations')},
        'browser_visual_qa':False,'browser_visual_qa_reason':'Computer Use native pipe and browser access host were unavailable; no UI action performed.',
        'human_participants':0,'human_quality_ratings':None,'understanding_improvement_measured':False,
        'model_requests':0,'real_scientific_executions':0,'new_training_runs':0,'committed_or_pushed':False}


def main():
    if (ROOT/'docs/integration/session_history_2026-10-30/authorized_source_changes.json').exists():
        from verify_session_history import main as verify_current_history
        return verify_current_history()
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--finalize',action='store_true')
    p.add_argument('--run-tests',action='store_true')
    p.add_argument('--run-checks',dest='run_tests',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.finalize:finalize()
    if args.run_tests:run_tests()
    result=verify();write(RECORD/'verification.json',result);print(json.dumps(result,ensure_ascii=False))
    return result


if __name__=='__main__':main()
