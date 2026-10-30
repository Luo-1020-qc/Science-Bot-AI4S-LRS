"""Frozen synthetic task evaluation. Offline by default; --live opts into 6 calls.

Offline results assess fallback, plan checks and formative discussion coverage.
They do not assess LLM question quality. Live results include actual questions and
mechanical indicators for review, never an automatic scientific/human-validity score.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'RUT_Science'))
sys.dont_write_bytecode = True

from rut_science.util import write_json, digest
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.blueprint import review, build_blueprint
from rut_science.science_bot.general.planning.clarification import propose
from rut_science.science_bot.general.planning.evidence import select
from rut_science.science_bot.general.planning.ledger import new_state, apply, contract_hash
from rut_science.science_bot.general.planning.runtime import _questions
from rut_science.science_bot.general.planning.understanding import review_reflection

DATA = ROOT/'docs/evaluation/dynamic_clarification_2026-10-29'


def populate(values):
    state = new_state()
    apply(state, {'updates': {f: {'value': v, 'quote': v, 'status': 'declared'}
                             for f, v in values.items()}, 'unknown': []}, 1)
    return state


def evaluate(live=False, output=None, tasks=DATA/'tasks.json'):
    path = tasks.resolve()
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = json.loads(path.with_name(path.stem+'_manifest.json').read_text(encoding='utf-8'))
    if checksum != manifest['sha256']:
        raise ValueError('Evaluation tasks changed after freezing')
    data = json.loads(path.read_text(encoding='utf-8'))
    output = (output or ROOT/'.local'/'dynamic_evaluation'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')).resolve()
    output.mkdir(parents=True, exist_ok=False)
    workspace = output/'workspace'; workspace.mkdir()
    session = GeneralSession.create(output/'sessions', backend='api' if live else 'offline', workspace=workspace,
        limits={'llm_requests': 6, 'llm_tokens': 60000, 'tool_calls': 1, 'read_bytes': 18000})
    results = []
    for case in data['cases']:
        state = populate(case['facts'])
        apply(state, {'updates': {}, 'unknown': case['unknown']}, 2)
        if case.get('conflict'):
            field = case['conflict']['field']
            state['conflicts'][field] = [{'value': v, 'quote': v, 'status': 'declared', 'turn': 2}
                                         for v in case['conflict']['values']]
        selected_path = case['id']+'.md'
        (workspace/selected_path).write_text(case['evidence']+'\n', encoding='utf-8')
        state['evidence'] = [select(session, {'path': selected_path, 'start_line': 1,
                                            'end_line': 1, 'share_with_model': True}, 2)]
        before = deepcopy(state); assessment = review(state)
        baseline = _questions(state, assessment)
        result = propose(session, state, case['answer'], assessment, baseline)
        if state != before:
            raise ValueError('Question generation mutated planning state')
        questions = result['questions']
        codes = {r['code'] for r in assessment['blockers']}
        expected_checks = {code: code in codes for code in case['expected_blocker_codes']}
        wording = '\n'.join(q['question']+' '+q['rationale'] for q in questions)
        topic_terms = [term for term in case['relevance_terms'] if term.casefold() in wording.casefold()]
        reflection = review_reflection(state, case['reflection'])
        plan = build_blueprint(state)
        results.append({'id': case['id'], 'answer': case['answer'], 'clarification': result,
            'template_baseline': baseline, 'plan_review': assessment,
            'plan_expected_risk_checks': expected_checks,
            'question_indicators': {'within_two': 1 <= len(questions) <= 2,
                'priority_field_covered': bool(set(q['field'] for q in questions)&set(case['expected_fields'])),
                'topic_terms_seen': topic_terms, 'topic_keyword_indicator': bool(topic_terms),
                'grounded_dynamic_questions': result['mode'] == 'dynamic',
                'semantic_quality_human_rated': False},
            'plan_indicators': {'node_count': len(plan['nodes']),
                'every_node_has_acceptance': all(n['acceptance'] and n['owner'] for n in plan['nodes']),
                'all_steps_unexecuted': all(not n['executed'] for n in plan['nodes']),
                'incomplete_plan_remains_blocked': not assessment['ready'],
                'execution_authorized': plan['execution_authorized']},
            'reflection': {'text': case['reflection'], 'discussion_cues': reflection,
                'source': 'scripted_synthetic_text_not_a_person'},
            'state_unchanged': state == before, 'contract_hash': contract_hash(state)})
    ready_state = populate(data['ready_plan']); ready = review(ready_state)
    summary = {'schema_version': 'clarification_evaluation_results_v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'mode': 'live' if live else 'offline', 'task_sha256': checksum, 'case_count': len(results),
        'provenance': data['provenance'],
        'model_resources': session.resources(), 'dynamic_cases': sum(r['clarification']['mode'] == 'dynamic' for r in results),
        'fallback_cases': sum(r['clarification']['mode'] == 'template' for r in results),
        'risk_checks_passed': sum(sum(r['plan_expected_risk_checks'].values()) for r in results),
        'risk_checks_total': sum(len(r['plan_expected_risk_checks']) for r in results),
        'priority_field_cases': sum(r['question_indicators']['priority_field_covered'] for r in results),
        'topic_keyword_cases': sum(r['question_indicators']['topic_keyword_indicator'] for r in results),
        'state_unchanged_cases': sum(r['state_unchanged'] for r in results),
        'ready_positive_control': {'ready': ready['ready'], 'review': ready},
        'real_scientific_executions': 0, 'human_participants': 0, 'understanding_improvement_measured': False,
        'limitations': ['Six public implementer-authored synthetic cases, no blinded independent expert labels.',
            'Question indicators check grounding, topic keywords and priority fields, not semantic correctness or scientific validity.',
            'Supplied ledger states isolate clarification; this is not an end-to-end semantic extraction accuracy benchmark.',
            'Reflection cues only detect discussion coverage in scripted text; no human understanding score or improvement estimate.',
            'Single live sample per case if enabled; no retries, checkpoint selection or prompt tuning on these results.'],
        'cases': results}
    summary['reflection_controls'] = {
        'empty': review_reflection(new_state(), ''),
        'keyword_stuffed_incorrect': review_reflection(new_state(), '目标范围已确定，因为模拟等于实测，所以证明因果；不确定也要一直试到显著，我负责停止。'),
        'meaning': 'Both controls remain unscored. Mentioning rubric words is not evidence of correct understanding.'}
    runtime_paths = ['ledger.py', 'blueprint.py', 'runtime.py', 'clarification.py', 'evidence.py', 'understanding.py']
    summary['runtime_sha256'] = {p: hashlib.sha256((ROOT/'RUT_Science/rut_science/science_bot/general/planning'/p).read_bytes()).hexdigest()
                                 for p in runtime_paths}
    write_json(output/'results.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in {'cases', 'ready_positive_control', 'runtime_sha256', 'limitations', 'reflection_controls'}}, ensure_ascii=False))
    print(str(output/'results.json'))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--tasks', type=Path, default=DATA/'tasks.json')
    args = parser.parse_args()
    evaluate(args.live, args.output, args.tasks)
