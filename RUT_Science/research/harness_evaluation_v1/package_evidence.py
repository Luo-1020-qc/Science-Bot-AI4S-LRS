"""Collect portable evaluation evidence, preserving historical receipts and failures."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'RUT_Science')]
sys.dont_write_bytecode = True
from integrity import check_project, sha
from rut_science.science_bot.general.registry import ToolRegistry

LOCAL = ROOT/'.local/comprehensive_20261030'
OUT = ROOT/'docs/evaluation/comprehensive_2026-10-30'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def copy(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)


def assert_no_secret_keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            assert k.casefold() not in {'api_key', 'authorization', 'bearer_token'}, 'Secret field in evidence'
            assert_no_secret_keys(v)
    elif isinstance(value, list):
        for v in value:
            assert_no_secret_keys(v)


def main():
    suites = {}
    for name in ['application', 'integrity', 'scoring', 'tool_library', 'v2_protocol', 'curriculum']:
        suites[name] = read(LOCAL/name/'results.json')
        for filename in ['results.json', 'tests.log']:
            copy(LOCAL/name/filename, OUT/'regression'/name/filename)
    write(OUT/'regression/results.json', {'suites': suites,
        'run': sum(r['run'] for r in suites.values()),
        'passed': sum(r['passed_tests'] for r in suites.values()),
        'skipped': sum(len(r['skipped']) for r in suites.values()),
        'failed': sum(len(r['failures'])+len(r['errors']) for r in suites.values())})
    copy(LOCAL/'curriculum_recompute.json', OUT/'curriculum_recompute.json')
    copy(ROOT/'.local/checks/repository_check.json', OUT/'repository_check.json')
    offline = read(LOCAL/'offline_mainline/results.json')
    copy(LOCAL/'offline_mainline/results.json', OUT/'offline_mainline/results.json')
    for case in offline['cases']:
        for filename in ['trajectory.json', 'final_state.json', 'plan.json']:
            copy(LOCAL/'offline_mainline'/case['id']/filename, OUT/'offline_mainline'/case['id']/filename)
    for filename in ['cases.json', 'results.json']:
        copy(LOCAL/'risk_probes'/filename, OUT/'risk_probes'/filename)
    for folder in (LOCAL/'risk_probes').iterdir():
        if folder.is_dir():
            for filename in ['state.json', 'turn.json']:
                copy(folder/filename, OUT/'risk_probes'/folder.name/filename)

    live = read(LOCAL/'live_dialogues/results.json')
    copy(LOCAL/'live_dialogues/results.json', OUT/'live_dialogues/results.json')
    for filename in ['input_manifest.json', 'input_manifest_v1.json', 'runner_v1.py']:
        copy(LOCAL/'live_dialogues'/filename, OUT/'live_dialogues'/filename)
    roles, statuses, clarification, models, intents = Counter(), Counter(), Counter(), Counter(), Counter()
    details = []
    total_turns = 0
    for case in live['cases']:
        name = case['id']
        src = LOCAL/'live_dialogues'/name
        for filename in ['trajectory.json', 'final_state.json', 'result.json', 'plan.json']:
            if (src/filename).exists():
                copy(src/filename, OUT/'live_dialogues'/name/filename)
        rows = read(src/'trajectory.json')
        total_turns += len(rows)
        fields = Counter()
        for row in rows:
            result = row.get('result', {})
            intents[result.get('intent', 'none')] += 1
            if isinstance(result.get('clarification'), dict):
                clarification[result['clarification']['mode']] += 1
            for q in result.get('questions', []):
                if isinstance(q, dict):
                    fields[q.get('field', 'none')] += 1
        sessions = list((src/'sessions').iterdir())
        assert len(sessions) == 1
        for path in (sessions[0]/'model_calls').glob('*.json'):
            value = read(path)
            assert_no_secret_keys(value)
            copy(path, OUT/'live_dialogues'/name/'model_calls'/path.name)
            if path.name.endswith('_status.json'):
                statuses[value['status']] += 1
                roles[value['role']] += 1
                models[value.get('model', 'unknown')] += 1
        details.append({'id': name, 'has_planning_ledger': read(src/'final_state.json') is not None,
                        'turns': len(rows), 'question_fields': dict(fields),
                        'most_repeated_field_count': max(fields.values(), default=0),
                        'ready': case['ready'], 'resources': case['resources']})
    assert sum(statuses.values()) == live['model_requests']
    write(OUT/'live_dialogues/analysis.json', {'scripted_turns': total_turns,
        'timed_turns': live['turns'], 'missing_latency_turns': total_turns-live['turns'],
        'ledger_cases': sum(c['has_planning_ledger'] for c in details),
        'intents': dict(intents), 'clarification_modes': dict(clarification),
        'model_statuses': dict(statuses), 'model_roles': dict(roles), 'actual_models': dict(models),
        'cases': details,
        'evaluator_amendment': 'v1 assumed all questions were objects. General chat/clarify returns string questions. v2 accepts both shapes and resumes the single persisted turn without another model request; its latency is missing. All original cases, replies and v1 source hash retained. No runtime, prompts, limits or cases changed.'})
    write(OUT/'human_review_queue.json', {
        'status': 'pending_not_rated', 'human_participants': 0,
        'rubric': {'question_quality': 'Does the question resolve an ambiguity that changes the design? Are options distinct, relevant, non-leading, and inclusive of unknown/custom?',
                   'plan_testability': 'Can a reviewer identify independent units, estimand, measurement, baseline, data separation, evidence gaps and bounded stopping rules?',
                   'researcher_understanding': 'Compare actual before/after explanations of scope, unit, uncertainty and what the evidence cannot establish; do not infer understanding from approval.'},
        'cases': [{'id': c['id'], 'trajectory': f'live_dialogues/{c["id"]}/trajectory.json',
                   'reviewer': None, 'question_quality_1_to_5': None,
                   'option_quality_1_to_5': None, 'plan_testability_1_to_5': None,
                   'researcher_understanding': 'not_assessed', 'review_status': 'pending'} for c in live['cases']]})
    tools = ToolRegistry().specs()
    catalog = read(ROOT/'Research_Tool_Library/tool_catalog.json')
    write(OUT/'tool_inventory.json', {'registered_count': len(tools), 'registered': tools,
        'catalog_count': len(catalog['tools']),
        'catalog_implementation_counts': dict(Counter(t['implementation'] for t in catalog['tools'])),
        'catalog_warning': 'The static catalog live_agent_registered field is historical metadata, not authoritative for the current GeneralSession registry.'})
    protocol = read(OUT/'protocol.json')
    code_changed = [name for name, expected in protocol['code_sha256'].items() if sha(ROOT/name) != expected]
    protected_changed = [name for name, expected in protocol['protected_expected_sha256'].items() if sha(ROOT/name) != expected]
    assert not code_changed and not protected_changed
    write(OUT/'source_verification.json', {'checked_utc': datetime.now(timezone.utc).isoformat(),
        'passed': True, 'baseline_code_files': len(protocol['code_sha256']),
        'protected_files': len(protocol['protected_expected_sha256']),
        'code_changed': code_changed, 'protected_changed': protected_changed,
        'integrity_after': check_project(), 'runtime_tuned_after_cases': False,
        'training_requested': False, 'llm_fine_tuned': False, 'real_scientific_executions': 0})
    manifest = {p.relative_to(OUT).as_posix(): sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='manifest.json'}
    write(OUT/'manifest.json', {'checked_utc': datetime.now(timezone.utc).isoformat(), 'files': manifest,
        'evaluation_code': {p.relative_to(ROOT).as_posix(): sha(p) for p in Path(__file__).parent.glob('*.py')}})
    print(json.dumps({'suites': len(suites), 'python_tests': 608, 'evidence_files': len(manifest),
        'live_requests': live['model_requests'], 'live_tokens': live['accounted_tokens'],
        'runtime_unchanged': not code_changed, 'protected_unchanged': not protected_changed}, ensure_ascii=False))


if __name__ == '__main__':
    main()
