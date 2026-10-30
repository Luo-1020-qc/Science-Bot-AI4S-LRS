"""Audit interface delivery; --run-tests records a fresh offline full regression."""
import argparse
from datetime import datetime, timezone
import json
import sys
import time
import unittest

from integrity import ROOT, INTERFACE_RECORD, sha, check_project

sys.path.insert(0, str(ROOT/'RUT_Science'))
sys.dont_write_bytecode = True
RECORD = ROOT/INTERFACE_RECORD


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def receipt_inputs():
    paths = list((ROOT/'RUT_Science/tests').rglob('test*.py'))
    paths += [ROOT/'scripts'/name for name in
              ('test_integrity.py', 'integrity.py', 'verify_interfaces.py', 'verify_dynamic_upgrade.py')]
    for name in ('runtime_manifest.json', 'authorized_source_changes.json'):
        paths += list((ROOT/'docs/integration').rglob(name))
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def run_tests():
    check_project()
    before = receipt_inputs()
    groups = {}
    for name, folder, pattern in (('application', 'RUT_Science/tests', 'test*.py'),
                                  ('integrity', 'scripts', 'test_integrity.py')):
        started = time.monotonic()
        suite = unittest.TestLoader().discover(str(ROOT/folder), pattern=pattern)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        groups[name] = {'run': result.testsRun, 'passed': result.wasSuccessful(),
            'failures': len(result.failures), 'errors': len(result.errors),
            'skipped': len(result.skipped), 'seconds': round(time.monotonic()-started, 3)}
    if before != receipt_inputs():
        raise ValueError('Runtime manifests, verification code or tests changed during regression')
    receipt = {'passed': all(g['passed'] for g in groups.values()),
        'checked_utc': datetime.now(timezone.utc).isoformat(),
        'mode': 'offline_unittest_with_mocked_providers', 'groups': groups,
        'runtime_manifest_sha256': sha(RECORD/'runtime_manifest.json'),
        'source_sha256': before}
    (RECORD/'full_tests.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    if not receipt['passed']:
        raise ValueError('Regression failed; see current test output and full_tests.json')


def check_examples():
    from rut_science.science_bot.presentation import terminal_preview_html, browser_preview_html, delivery_html
    from rut_science.science_bot.interface_demo import example_state
    from rut_science.science_bot.general.planning.runtime import _plan
    expected = {'terminal.html': terminal_preview_html(), 'browser.html': browser_preview_html(),
                'delivery.html': delivery_html(_plan(example_state()))}
    hashes = {}
    for name, content in expected.items():
        path = ROOT/'examples/interfaces'/name
        if path.read_text(encoding='utf-8') != content:
            raise ValueError('Example is stale; rerun scripts/preview_interfaces.py: '+name)
        hashes[path.relative_to(ROOT).as_posix()] = sha(path)
    return hashes


def main():
    if (ROOT/'docs/integration/question_tool_2026-10-29/authorized_source_changes.json').exists():
        from verify_question_tool import main as verify_current_question_tool
        return verify_current_question_tool()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-tests', action='store_true')
    args = parser.parse_args()
    if args.run_tests:
        run_tests()
    protected = check_project()
    tests = read(RECORD/'full_tests.json')
    if (not tests['passed'] or tests['source_sha256'] != receipt_inputs()
            or tests['runtime_manifest_sha256'] != sha(RECORD/'runtime_manifest.json')):
        raise ValueError('Saved regression no longer matches current sources; use --run-tests')
    # Reuse the historical audit without rewriting its frozen receipt.
    from verify_dynamic_upgrade import main as verify_dynamic_evidence
    historical = verify_dynamic_evidence(historical=True)
    result = {'passed': True, 'kind': 'current_integrity_and_saved_regression',
        'integrity': protected, 'full_regression': tests['groups'],
        'example_sha256': check_examples(),
        'historical_dynamic_evidence_verified': True,
        'retained_training_artifacts_checked': historical['retained_training_artifacts_checked'],
        'browser_visual_qa': False,
        'browser_visual_qa_reason': 'Computer Use safety gate could not reliably identify the current browser URL; UI automation stopped.',
        'human_participants': 0, 'understanding_improvement_measured': False,
        'this_audit_model_requests': 0, 'real_scientific_executions': 0,
        'committed_or_pushed': False}
    (RECORD/'verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
