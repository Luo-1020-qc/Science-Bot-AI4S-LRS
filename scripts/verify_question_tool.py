"""Current question-tool integrity, saved regression and recomputed synthetic training."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import sys
import time
import unittest

from integrity import ROOT, QUESTION_RECORD, sha, check_project
from verify_interfaces import receipt_inputs as interface_inputs, check_examples

sys.path.insert(0, str(ROOT/'RUT_Science'))
sys.dont_write_bytecode = True
RECORD = ROOT/QUESTION_RECORD


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def receipt_inputs():
    return {**interface_inputs(), 'scripts/verify_question_tool.py': sha(ROOT/'scripts/verify_question_tool.py'),
            QUESTION_RECORD+'/training_manifest.json': sha(RECORD/'training_manifest.json')}


def run_tests():
    check_project()
    before = receipt_inputs()
    groups = {}
    for name, folder, pattern in (('application', 'RUT_Science/tests', 'test*.py'),
                                  ('integrity', 'scripts', 'test_integrity.py')):
        started = time.monotonic()
        result = unittest.TextTestRunner(verbosity=1).run(unittest.TestLoader().discover(str(ROOT/folder), pattern=pattern))
        groups[name] = {'run': result.testsRun, 'passed': result.wasSuccessful(),
            'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
            'seconds': round(time.monotonic()-started, 3)}
    if before != receipt_inputs():
        raise ValueError('Sources or tests changed during regression')
    value = {'passed': all(g['passed'] for g in groups.values()), 'groups': groups,
        'checked_utc': datetime.now(timezone.utc).isoformat(), 'source_sha256': before,
        'mode': 'offline_unittest_with_mocked_providers'}
    (RECORD/'full_tests.json').write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    if not value['passed']:
        raise ValueError('Current question-tool regression failed')


def training_audit():
    import numpy as np
    from rut_science.science_bot.general.planning.question_tool import execute
    from rut_science.science_bot.general.planning.question_ranker import load_policy
    folder = ROOT/'RUT_Science/research/question_tool_v1'
    spec = importlib.util.spec_from_file_location('question_training_audit', folder/'train.py')
    training = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(training)
    manifest = read(folder/'run_001/manifest.json')
    if manifest['training_source_sha256'] != sha(folder/'train.py'):
        raise ValueError('Training code changed after experiment')
    for name, checksum in manifest['sha256'].items():
        if sha(folder/'run_001'/name) != checksum:
            raise ValueError('Training artifact changed: '+name)
    cases = training.data()
    weights, details = training.fit(cases)
    model = load_policy()
    if sha(folder/'run_001/policy.json') != sha(ROOT/'RUT_Science/rut_science/science_bot/general/planning/question_policy.json'):
        raise ValueError('Packaged candidate is not the trained artifact')
    if not np.allclose(weights, model['weights'], rtol=0, atol=1e-12) or details['parameter_l2_change'] <= 0:
        raise ValueError('Candidate weights could not be independently recomputed')
    evaluated, trajectories = training.evaluate(cases, weights)
    original = read(folder/'run_001/results.json')
    if evaluated != original['evaluation'] or trajectories != read(folder/'run_001/trajectories.json'):
        raise ValueError('Saved synthetic evaluation does not reproduce')
    checked = 0
    for case in cases:
        if case['split'] != 'test':
            continue
        before = training.contract_hash(case['state'])
        selected = execute({'policy': 'trained'}, {'planning_state': case['state']})
        if selected['plan_hash'] != before or selected['execution_authorized'] or selected['ledger_updated']:
            raise ValueError('Actual question tool crossed its read-only boundary')
        checked += 1
    return {'evaluation': evaluated, 'actual_tool_test_cases_checked': checked,
        'weights_and_rollouts_recomputed': True, 'human_expert_labels': 0,
        'language_model_weights_changed': False, 'default_candidate_enabled': False,
        'question_count_improvement_observed': False, 'understanding_improvement_measured': False}


def main():
    if (ROOT/'docs/integration/branding_2026-10-29/authorized_source_changes.json').exists():
        from verify_branding import main as verify_current_branding
        return verify_current_branding()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-tests', action='store_true')
    args = parser.parse_args()
    if args.run_tests:
        run_tests()
    protected = check_project()
    tests = read(RECORD/'full_tests.json')
    if not tests['passed'] or tests['source_sha256'] != receipt_inputs():
        raise ValueError('Current test receipt stale; use --run-tests')
    retained = 0
    training = ROOT/'Training_Data_Darcy_CViT/v2/synthetic_batch_050'
    for manifest in (training/'release_manifest.json', training/'formal_2026_10_29/experiment_manifest.json'):
        for name, checksum in read(manifest)['sha256'].items():
            if sha(training/name) != checksum:
                raise ValueError('Retained original training artifact changed: '+name)
            retained += 1
    result = {'passed': True, 'integrity': protected, 'full_regression': tests['groups'],
        'training': training_audit(), 'example_sha256': check_examples(),
        'previous_receipts_unchanged': len(read(RECORD/'before_snapshot.json')['unchanged_history']),
        'retained_original_training_artifacts_checked': retained,
        'model_requests': 0, 'real_scientific_executions': 0, 'committed_or_pushed': False,
        'browser_visual_qa_repeated': False, 'frontend_assets_changed': False}
    (RECORD/'verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
