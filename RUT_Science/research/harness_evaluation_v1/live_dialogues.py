"""Frozen scripted live diagnostics; no runtime changes, blind labels or auto approval.

Run sequentially. Each case has a native provider admission limit, whose sums
bound the complete run to 48 requests and 180000 accounted tokens. No retries.
"""
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'RUT_Science'))
sys.dont_write_bytecode = True
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.ledger import load, contract_hash
from rut_science.science_bot.general.planning.runtime import review
from rut_science.science_bot.presentation import export_bundle


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def run_case(case, output):
    folder = output / case['id']
    if (folder / 'result.json').exists():
        return json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    folder.mkdir(exist_ok=True)
    workspace = folder / 'workspace'
    workspace.mkdir(exist_ok=True)
    # Only this explicitly selected synthetic paper is made available.
    if '<ADD_PDF>' in case['inputs']:
        shutil.copyfile(ROOT / 'examples/papers/synthetic_paper.pdf', workspace / 'synthetic_paper.pdf')
    existing = list((folder / 'sessions').glob('*/session.json'))
    if existing:
        assert len(existing) == 1
        session = GeneralSession.restore(existing[0].parent, workspace=workspace)
    else:
        session = GeneralSession.create(folder / 'sessions', backend='api', workspace=workspace,
            limits={'llm_requests': case['request_cap'], 'llm_tokens': case['token_cap'],
                    'tool_calls': 40, 'read_bytes': 24000})
    rows = json.loads((folder / 'trajectory.json').read_text(encoding='utf-8')) if (folder / 'trajectory.json').exists() else []
    completed = session.meta['turn']
    assert completed <= len(rows)+1, 'Only one post-response evaluator interruption is recoverable'
    for input_index, text in enumerate(case['inputs']):
        if input_index < len(rows):
            continue
        if text == '<ADD_PDF>':
            text = '/plan evidence add ' + json.dumps({'path': 'synthetic_paper.pdf', 'start_page': 1,
                        'end_page': 2, 'share_with_model': True}, ensure_ascii=False)
        if text == '<READ_PDF>':
            state = load(session)
            items = (state or {}).get('evidence', [])
            if not items:
                rows.append({'input': text, 'exception': 'No selected evidence; reading not attempted'})
                continue
            text = '/plan evidence understand ' + items[0]['id']
        before = deepcopy(load(session))
        recovered = input_index < completed
        if recovered:
            # Recover the already persisted response, NEVER replay the model call.
            result = json.loads((session.folder/'turns'/f'{input_index+1:04d}_result.json').read_text(encoding='utf-8'))
            before = rows[-1]['after'] if rows else None
            error, elapsed = None, None
        else:
            started = time.monotonic()
            try:
                result = session.message(text)
                error = None
            except Exception:
                result = {}
                error = traceback.format_exc()
            elapsed = time.monotonic() - started
        after = deepcopy(load(session))
        assessment = review(after) if after else None
        questions = [q for q in result.get('questions', []) if isinstance(q, dict)]
        blockers = {b['field'] for b in (assessment or {}).get('blockers', [])}
        known_repeats = [q['field'] for q in questions if q.get('kind') == 'missing'
            and (after or {}).get('facts', {}).get(q['field'], {}).get('status') == 'declared'
            and q['field'] not in blockers]
        rows.append({'turn': len(rows)+1, 'input': text, 'seconds': round(elapsed, 3) if elapsed is not None else None,
                     'recovered_persisted_response_without_replay': recovered,
                     'exception': error, 'result': result, 'before': before, 'after': after,
                     'known_field_missing_questions': known_repeats,
                     'state_changed': contract_hash(before) != contract_hash(after) if before and after else before != after,
                     'resources': session.resources()})
        write(folder / 'trajectory.json', rows)
        print(json.dumps({'case': case['id'], 'turn': len(rows), 'seconds': round(elapsed, 2) if elapsed is not None else None,
                          'resources': session.resources(), 'exception': bool(error)}, ensure_ascii=False), flush=True)
    state = deepcopy(load(session))
    assessment = review(state) if state else None
    if state:
        draft = session.message('/plan draft')
        write(folder / 'plan.json', draft.get('blueprint'))
        (folder / 'plan.md').write_text(draft.get('answer', ''), encoding='utf-8')
        bundle = export_bundle(session)
        for filename, key in [('delivery.html', 'html'), ('delivery.md', 'markdown')]:
            (folder / filename).write_bytes(bundle[key].read_bytes())
    write(folder / 'final_state.json', state)
    restored = GeneralSession.restore(session.folder, workspace=workspace)
    restore_ok = load(restored) == load(session) and restored.resources() == session.resources()
    facts = (state or {}).get('facts', {})
    inputs = [r['input'] for r in rows]
    quote_issues = [f for f, v in facts.items() if v.get('quote') and not any(v['quote'] in t for t in inputs)]
    result = {'id': case['id'], 'purpose': case['purpose'], 'scripted_turns': len(rows),
        'ready': bool(assessment and assessment['ready']),
        'declarations': sum(v.get('status') == 'declared' for v in facts.values()),
        'proposals': sum(v.get('status') == 'proposed' for v in facts.values()),
        'unknown_fields': (state or {}).get('unknown', []),
        'conflict_fields': list((state or {}).get('conflicts', {})),
        'stale_fields': list((state or {}).get('stale', {})),
        'blockers': (assessment or {}).get('blockers', []),
        'known_field_missing_questions': sum(len(r.get('known_field_missing_questions', [])) for r in rows),
        'questions': sum(len(r.get('result', {}).get('questions', [])) for r in rows),
        'clarification': [r.get('result', {}).get('clarification') for r in rows],
        'exceptions': [r['exception'] for r in rows if r.get('exception')],
        'fact_quote_not_literal_in_inputs': quote_issues,
        'session_restore_exact': restore_ok, 'resources': session.resources(),
        'turn_seconds': [r['seconds'] for r in rows if isinstance(r.get('seconds'), (int, float))],
        'recovered_turns_without_latency': sum(r.get('recovered_persisted_response_without_replay', False) for r in rows),
        'approval': (state or {}).get('approval'),
        'scientific_claim_verified': (assessment or {}).get('scientific_claim_verified', False),
        'execution_authorized': (assessment or {}).get('execution_authorized', False),
        'human_quality_scores': None, 'researcher_understanding_measured': False}
    write(folder / 'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='Resume persisted turns after evaluator interruption; never replay completed requests')
    parser.add_argument('--cases', type=Path, default=ROOT / 'docs/evaluation/comprehensive_2026-10-30/live_cases.json')
    args = parser.parse_args()
    data = json.loads(args.cases.read_text(encoding='utf-8'))
    assert sum(c['request_cap'] for c in data['cases']) <= 48
    assert sum(c['token_cap'] for c in data['cases']) <= 180000
    assert len(data['cases']) == 8
    args.output.mkdir(parents=True, exist_ok=args.resume)
    pinned = {str(args.cases.relative_to(ROOT)): sha(args.cases),
              str(Path(__file__).relative_to(ROOT)): sha(Path(__file__))}
    write(args.output / 'input_manifest.json', pinned)
    results = []
    for case in data['cases']:
        results.append(run_case(case, args.output))
        write(args.output / 'partial_results.json', results)
    assert pinned == {name: sha(ROOT / name) for name in pinned}, 'Evaluation inputs changed'
    seconds = [x for r in results for x in r['turn_seconds']]
    result = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'provenance': data['provenance'],
        'automatic_retries': 0, 'case_count': len(results),
        'ready': sum(r['ready'] for r in results),
        'session_restore_exact': sum(r['session_restore_exact'] for r in results),
        'model_requests': sum(r['resources']['llm_requests'] for r in results),
        'accounted_tokens': sum(r['resources']['llm_tokens'] for r in results),
        'turns': len(seconds), 'seconds_median': statistics.median(seconds),
        'seconds_max': max(seconds), 'seconds_total': sum(seconds),
        'known_field_missing_questions': sum(r['known_field_missing_questions'] for r in results),
        'execution_authorized': any(r['execution_authorized'] for r in results),
        'scientific_claim_verified': any(r['scientific_claim_verified'] for r in results),
        'human_participants': 0, 'human_quality_scores': None,
        'cases': results}
    assert result['model_requests'] <= 48 and result['accounted_tokens'] <= 180000
    write(args.output / 'results.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
