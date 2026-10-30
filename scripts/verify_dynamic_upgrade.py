"""Portable offline audit of current sources and saved test/evaluation receipts.

This verifies historical test evidence, it does not rerun tests or call a model.
"""
import json
import hashlib
from pathlib import Path
from integrity import (ROOT, DYNAMIC_RECORD, DYNAMIC_CHANGED_FILES, DYNAMIC_NEW_FILES,
                       PRIVACY_RECORD, sha, check_project)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def before_display_patch(raw, receipt):
    for patch in receipt['patches']:
        if raw.count(patch['new_block'].encode()) != 1:
            raise ValueError('Evaluation UI patch does not match current source')
        raw = raw.replace(patch['new_block'].encode(), patch['old_block'].encode(), 1)
    return hashlib.sha256(raw).hexdigest()


def main(*, historical=False):
    if not historical and (ROOT/'docs/integration/interfaces_2026-10-29/authorized_source_changes.json').exists():
        from verify_interfaces import main as verify_current_interfaces
        return verify_current_interfaces()
    protected = check_project()
    record = ROOT/DYNAMIC_RECORD
    tests = read(record/'full_tests.json')
    if not tests['passed'] or tests['runtime_manifest_sha256'] != sha(record/'runtime_manifest.json'):
        raise ValueError('Saved test receipt does not match current runtime manifest')
    if tests['history_privacy_overlay_sha256'] != sha(ROOT/PRIVACY_RECORD/'authorized_source_changes.json'):
        raise ValueError('Saved test receipt does not match the conversation history privacy source')
    for name, checksum in tests['test_source_sha256'].items():
        if sha(ROOT/name) != checksum:
            raise ValueError('Test sources changed since saved full regression: '+name)
    training = ROOT/'Training_Data_Darcy_CViT/v2/synthetic_batch_050'
    retained = 0
    for manifest in (training/'release_manifest.json', training/'formal_2026_10_29/experiment_manifest.json'):
        for name, checksum in read(manifest)['sha256'].items():
            if sha(training/name) != checksum:
                raise ValueError('Retained training artifact changed: '+name)
            retained += 1
    evaluation = ROOT/'docs/evaluation/dynamic_clarification_2026-10-29'
    for name in ('tasks', 'followup_tasks'):
        if sha(evaluation/(name+'.json')) != read(evaluation/(name+'_manifest.json'))['sha256']:
            raise ValueError('Frozen evaluation task changed: '+name)
    followup = read(evaluation/'live_followup.json')
    offline = read(evaluation/'offline_followup.json')
    initial = read(evaluation/'live_initial.json')
    task_hash = sha(evaluation/'followup_tasks.json')
    display_patch = read(record/'evaluation_display_patch.json')
    for report in (followup, offline):
        if report['task_sha256'] != task_hash:
            raise ValueError('Follow-up evaluation uses different task inputs')
        for name in DYNAMIC_CHANGED_FILES|DYNAMIC_NEW_FILES:
            if report['runtime_sha256'][Path(name).name] != sha(ROOT/name):
                # Preserve the original online evaluation hashes. The only
                # subsequent runtime edit exposes its question in the terminal
                # evidence-selection success answer; reconstruct the exact
                # evaluated bytes to verify no question logic was changed.
                raw = (ROOT/name).read_bytes()
                if (Path(name).name != 'runtime.py' or sha(ROOT/name) != display_patch['current_sha256']
                        or before_display_patch(raw, display_patch) != report['runtime_sha256']['runtime.py']):
                    raise ValueError('Evaluation runtime does not match current sources: '+name)
        if (report['case_count'] != len(report['cases']) or report['state_unchanged_cases'] != report['case_count']
                or report['human_participants'] != 0 or report['understanding_improvement_measured']
                or report['real_scientific_executions'] != 0):
            raise ValueError('Invalid evaluation scope/counts')
    if initial['task_sha256'] != sha(evaluation/'tasks.json'):
        raise ValueError('Initial diagnostic task provenance changed')
    if followup['model_resources']['llm_requests'] != 6 or offline['model_resources']['llm_requests'] != 0:
        raise ValueError('Evaluation request accounting changed')
    result = {'passed': True, 'kind': 'saved_evidence_and_current_integrity', 'integrity': protected,
        'full_regression': {k:v for k,v in tests.items() if k!='test_source_sha256'},
        'retained_training_artifacts_checked': retained,
        'initial_diagnostic': {'dynamic': initial['dynamic_cases'], 'fallback': initial['fallback_cases']},
        'followup_evaluation': {'dynamic': followup['dynamic_cases'], 'fallback': followup['fallback_cases'],
            'risk_checks_passed': followup['risk_checks_passed'], 'risk_checks_total': followup['risk_checks_total'],
            'priority_field_cases': followup['priority_field_cases'], 'state_unchanged_cases': followup['state_unchanged_cases']},
        'understanding_improvement_measured': False, 'human_participants': 0,
        'this_audit_model_requests': 0, 'real_scientific_executions': 0, 'committed_or_pushed': False}
    if historical:
        return result
    (record/'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__': main()
