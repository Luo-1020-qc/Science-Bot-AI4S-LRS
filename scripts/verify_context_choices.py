"""Audit contextual choices, actual training and current full offline regression."""
import argparse
from datetime import datetime,timezone
import importlib.util
import json
import sys
import time
import unittest

from integrity import (ROOT,CHOICES_RECORD,CHOICES_HOST_FILES,CHOICES_NEW_FILES,CHOICES_TRAINING_FILES,sha,check_project)

sys.path.insert(0,str(ROOT/'RUT_Science'))
sys.dont_write_bytecode=True
RECORD=ROOT/CHOICES_RECORD


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def finalize():
    before=read(RECORD/'before_snapshot.json')
    for name,checksum in before['unchanged_history'].items():
        if sha(ROOT/name)!=checksum:raise ValueError('Earlier receipt changed: '+name)
    changes={n:{'before_sha256':before['files'][n],'sha256':sha(ROOT/n),
        'reason':'User requested contextual choice questions instead of visible rationale/citations, and authorized training the choice matching process'} for n in sorted(CHOICES_HOST_FILES)}
    dump(RECORD/'authorized_source_changes.json',{'files':changes})
    dump(RECORD/'runtime_manifest.json',{'sha256':{n:sha(ROOT/n) for n in sorted(CHOICES_HOST_FILES|CHOICES_NEW_FILES)}})
    dump(RECORD/'training_manifest.json',{'sha256':{n:sha(ROOT/n) for n in sorted(CHOICES_TRAINING_FILES)}})
    check_project()


def inputs():
    files=list((ROOT/'RUT_Science/tests').rglob('test*.py'))+list((ROOT/'scripts').glob('*.py'))
    for name in ('runtime_manifest.json','authorized_source_changes.json','training_manifest.json'):
        files+=list((ROOT/'docs/integration').rglob(name))
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)}


def run_tests():
    before=inputs();groups={}
    for name,folder,pattern in [('application','RUT_Science/tests','test*.py'),('integrity','scripts','test_integrity.py')]:
        started=time.monotonic()
        result=unittest.TextTestRunner(verbosity=1).run(unittest.TestLoader().discover(str(ROOT/folder),pattern=pattern))
        groups[name]={'run':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),
            'errors':len(result.errors),'skipped':len(result.skipped),'seconds':round(time.monotonic()-started,3)}
    if before!=inputs():raise ValueError('Source/test inputs changed during regression')
    receipt={'passed':all(g['passed'] for g in groups.values()),'groups':groups,'source_sha256':before,
        'checked_utc':datetime.now(timezone.utc).isoformat(),'mode':'offline_unittest_with_mocked_providers'}
    dump(RECORD/'full_tests.json',receipt)
    if not receipt['passed']:raise ValueError('Current contextual-choice regression failed')


def training_audit():
    import numpy as np
    from rut_science.science_bot.general.planning import choices
    from rut_science.science_bot.general.planning.ledger import new_state,contract_hash
    folder=ROOT/'RUT_Science/research/context_choices_v1'
    spec=importlib.util.spec_from_file_location('context_choice_training_audit',folder/'train.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    manifest=read(folder/'run_001/manifest.json')
    if sha(folder/'train.py')!=manifest['training_source_sha256']:raise ValueError('Choice training source changed')
    for name,checksum in manifest['sha256'].items():
        if sha(folder/'run_001'/name)!=checksum:raise ValueError('Choice training artifact changed: '+name)
    rows=module.data();weights,details=module.fit(rows);model=choices.load_policy()
    if not np.allclose(weights,model['weights'],rtol=0,atol=1e-12) or details['parameter_l2_change']<=0:
        raise ValueError('Context choice weights do not recompute')
    if choices.POLICY.read_bytes()!=(folder/'run_001/policy.json').read_bytes():raise ValueError('Packaged choice policy differs from training')
    result,samples=module.evaluate(rows,weights)
    if result!=read(folder/'run_001/results.json')['evaluation'] or samples!=read(folder/'run_001/examples.json'):
        raise ValueError('Context choice evaluation does not reproduce')
    checked=0
    for row in rows:
        if row['split']!='test':continue
        state=new_state();state['facts']['research_question']={'value':row['request'],'quote':row['request'],'status':'declared','turn':1}
        identity=contract_hash(state)
        q=choices.decorate(state,[{'field':'scope','kind':'missing','question':'选择研究范围','rationale':'内部检查','options':[]}])[0]
        if q['choice_policy']['intent']!=module.predict(row['request'],weights) or identity!=contract_hash(state):
            raise ValueError('Actual contextual choices differ from trained matcher or mutate state')
        if [o['action'] for o in q['options'][-2:]]!=['unknown','custom']:raise ValueError('Human uncertainty/free response missing')
        checked+=1
    return {'evaluation':result,'actual_context_choice_cases_checked':checked,'weights_recomputed':True,
        'human_preference_labels':0,'language_model_weights_changed':False,'human_option_usefulness_measured':False,
        'understanding_improvement_measured':False}


def main():
    if (ROOT/'docs/integration/mainline_2026-10-30/authorized_source_changes.json').exists():
        from verify_planning_mainline import main as verify_current_mainline
        return verify_current_mainline()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finalize',action='store_true')
    parser.add_argument('--run-tests',action='store_true')
    parser.add_argument('--run-checks',dest='run_tests',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.finalize:finalize()
    protected=check_project()
    if args.run_tests:run_tests()
    tests=read(RECORD/'full_tests.json')
    if not tests['passed'] or tests['source_sha256']!=inputs():raise ValueError('Current test receipt stale; use --run-tests')
    from verify_interfaces import check_examples
    from verify_branding import asset_checks
    result={'passed':True,'integrity':protected,'full_regression':tests['groups'],'training':training_audit(),
        'assets':asset_checks(),'example_sha256':check_examples(),
        'previous_integration_json_unchanged':len(read(RECORD/'before_snapshot.json')['unchanged_history']),
        'browser_visual_qa':False,'browser_visual_qa_reason':'No new browser UI automation; earlier Windows URL safety gate prevented visual QA.',
        'model_requests':0,'real_scientific_executions':0,'committed_or_pushed':False}
    dump(RECORD/'verification.json',result);print(json.dumps(result))


if __name__=='__main__':main()
