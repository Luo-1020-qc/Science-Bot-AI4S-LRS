"""Run full planning conversations through GeneralSession.message, offline by default.

The respondent alone owns the private answer bank. Offline uses explicit field
syntax after a natural start, testing host orchestration rather than pretending
to measure LLM extraction. --live reuses the native provider for free-text
answers, with a per-case request cap. No labels, weights or approvals are created.
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
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.blueprint import FIELDS
from rut_science.science_bot.general.planning.ledger import load, contract_hash
from rut_science.science_bot.general.planning.runtime import review
from rut_science.science_bot.presentation import export_bundle

DATA = ROOT/'docs/evaluation/mainline_2026-10-30'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def load_cases(path=DATA/'tasks.json'):
    data = json.loads(path.read_text(encoding='utf-8'))
    receipt = json.loads(path.with_name(path.stem+'_manifest.json').read_text(encoding='utf-8'))
    if receipt['sha256'] != sha(path) or len(data['cases']) != receipt['case_count']:
        raise ValueError('Frozen task manifest does not match')
    if len({c['id'] for c in data['cases']}) != len(data['cases']):
        raise ValueError('Duplicate case id')
    return data


def public_start(case):
    # This function must never access private answers or expected annotations.
    return case['initial_input']


def field_answer(values, *, live=False):
    # Field-labelled wording is the documented offline interface. In live mode
    # ordinary natural text uses the same extractor as real users; enum labels
    # remain explicit because the respondent knows its intended purpose/design.
    if not live:
        return '\n'.join(FIELDS[f]['label']+'：'+v for f,v in values.items())
    return '我补充这些决定。'+'；'.join(FIELDS[f]['label']+'采用“'+v+'”' for f,v in values.items())+'。'


def score(case, state, trajectory, artifacts):
    assessment = review(state)
    expected = case['expected']
    missing = [f for f in expected['critical_fields'] if not state['facts'].get(f)
               or f in state['unknown'] or f in state['conflicts'] or f in state['stale']]
    def normalized(text):return text.strip().rstrip('，,；;。\n ')
    wrong = [f for f,v in expected['values'].items() if v != '未知'
             and normalized((state['facts'].get(f) or {}).get('value','')) != normalized(v)]
    unresolved = set(r['field'] for r in assessment['blockers'])
    justified = (not assessment['ready'] and unresolved == {'sampling'}
                 and 'sampling' in state['unknown'] and 'sampling' in state.get('evidence_actions', {})
                 and 'sampling' not in state['facts'])
    ready = assessment['ready'] and not missing and not wrong
    success = justified and not missing and not wrong if expected['outcome'] == 'blocked_with_evidence_step' else ready
    question_rows = [r for r in trajectory if r.get('question')]
    repeats = [r['turn'] for r in question_rows if r['question_unnecessary']]
    host_violations = [r['turn'] for r in trajectory if r['execution_authorized'] or r['scientific_claim_verified']]
    return {'outcome': 'reviewable_design' if assessment['ready'] else 'blocked_with_evidence_step' if justified else 'incomplete',
            'expected_outcome_met': bool(success), 'critical_missing': missing, 'answer_mismatches': wrong,
            'question_count': len(question_rows), 'unnecessary_question_turns': repeats,
            'no_progress_question_turns': [r['turn'] for r in question_rows if r['before_hash']==r['after_hash']],
            'multi_field_answer_turns': sum(r['changed_field_count'] > 1 for r in trajectory),
            'host_violation_turns': host_violations, 'ready': assessment['ready'],
            'blocker_fields': sorted(unresolved), 'all_steps_unexecuted': all(not n['executed'] for n in artifacts['nodes']),
            'automatic_design_readout': any('实验设计草案' in r['answer'] for r in trajectory),
            'semantic_quality_human_rated': False, 'researcher_understanding_measured': False}


def run_case(case, output, *, live=False, request_cap=12):
    folder = output/case['id']; folder.mkdir()
    workspace = folder/'workspace'; workspace.mkdir()
    evidence_path = workspace/'synthetic_methods.md'
    evidence_path.write_text(case['private']['evidence_text']+'\n', encoding='utf-8')
    session = GeneralSession.create(folder/'sessions', backend='api' if live else 'offline', workspace=workspace,
        limits={'llm_requests': request_cap, 'llm_tokens': 60000, 'tool_calls': 40, 'read_bytes': 18000})
    trajectory = []

    def send(text, actor='scripted_respondent'):
        before = load(session)
        result = session.message(text)
        after = load(session)
        q = (result.get('questions') or [None])[0]
        bad_question = False
        if q and after:
            blockers = {r['field'] for r in review(after)['blockers']}
            bad_question = (q['kind'] == 'missing' and q['field'] in after['facts']
                            and q['field'] not in blockers)
        trajectory.append({'turn': len(trajectory)+1, 'actor': actor, 'input': text,
            'answer': result.get('answer', ''), 'question': q, 'question_unnecessary': bad_question,
            'error': bool(result.get('planning_error')), 'before_hash': contract_hash(before) if before else None,
            'after_hash': contract_hash(after) if after else None,
            'changed_field_count': sum((before or {}).get('facts',{}).get(f) != (after or {}).get('facts',{}).get(f) for f in FIELDS),
            'execution_authorized': result.get('execution_authorized',False),
            'scientific_claim_verified': result.get('scientific_claim_verified',False),
            'clarification': result.get('clarification'), 'resources': session.resources()})
        return result

    values = deepcopy(case['private']['answers'])
    remaining_events = deepcopy(case['private']['events'])
    send(public_start(case))
    if case['mechanism'] == 'complete_input':
        # Initial input already carries all choices; no hidden ledger population.
        pass
    for _ in range(24):
        state = load(session)
        if state is None: break
        event = next((e for e in remaining_events if e.get('after_field') in state['facts']
                      or e.get('after_ready') and review(state)['ready']), None)
        if event:
            remaining_events.remove(event)
            if event['kind'] == 'correction':
                values[event['field']] = event['value']; send(event['text'])
            else:
                values = event['values']
                send('/plan revise '+field_answer({f:values[f] for f in ('research_question','objective_type','design')}))
            continue
        if review(state)['ready']: break
        q = state.get('pending')
        if not q: break
        f = q['field']
        if q['kind'] == 'evidence_plan':
            send('先查找已有先导记录，再请方法负责人核实单位与样本依据。')
            # The scripted user explicitly selects this synthetic excerpt; only
            # this selected snapshot can enter the live model context.
            send('/plan evidence add '+json.dumps({'path':'synthetic_methods.md','start_line':1,'end_line':1,
                                                  'share_with_model':live},ensure_ascii=False))
            continue
        if q['kind'] == 'proposal':
            # A respondent validates its own intended value, not all model output.
            if f in values and state['facts'][f]['value'] == values[f]: send('/plan accept '+f)
            elif f in values: send('/plan revise '+field_answer({f:values[f]}))
            else: break
            continue
        if f not in values: break
        bundle = next((b for b in case['private']['bundles'] if f in b), [f])
        fields = {k:values[k] for k in bundle if k in values and (k == f or k not in state['facts']
                   and k not in state['unknown'] or k in state['stale'])}
        # At least one actual version-bound choice per eligible dialogue.
        option = next((o for o in q.get('options',[]) if o.get('value') == values[f] and o.get('action') in {'declare','revise'}),None)
        if f == 'objective_type' and option and case['mechanism']=='multi_answer':
            send('/plan choose '+q['choice_id']+' '+option['id'])
        else:
            text = field_answer(fields,live=live)
            send(('/plan revise ' if q['kind'] in {'conflict','stale'} else '')+text)
    state = load(session)
    if state is None:
        write(folder/'trajectory.json', trajectory)
        return {'id':case['id'],'error':'natural_input_did_not_start_planning','trajectory':str(folder/'trajectory.json')}
    final_state = deepcopy(state)
    final = session.message('/plan draft')
    artifacts = final['blueprint']
    # No approval is submitted; these are diagnostic plans, not human approvals.
    bundle = export_bundle(session)
    assessment = score(case,final_state,trajectory,artifacts)
    write(folder/'trajectory.json',trajectory)
    write(folder/'final_state.json',final_state)
    write(folder/'plan.json',artifacts)
    (folder/'plan.md').write_text(final['answer'],encoding='utf-8')
    for name,key in [('delivery.html','html'),('delivery.md','markdown')]:
        (folder/name).write_bytes(bundle[key].read_bytes())
    result = {'id':case['id'],'root_group':case['root_group'],'mechanism':case['mechanism'],
        'metrics':assessment,'resources':session.resources(),'remaining_events':remaining_events,
        'selected_evidence_count':len(final_state.get('evidence',[])),
        'artifacts':{p.name:sha(p) for p in folder.iterdir() if p.is_file()}}
    write(folder/'result.json',result)
    return result


def evaluate(output, *, live=False, request_cap=12, tasks=DATA/'tasks.json'):
    data = load_cases(tasks)
    output = output.resolve(); output.mkdir(parents=True,exist_ok=False)
    source_paths = [p for p in (ROOT/'RUT_Science/rut_science/science_bot').rglob('*')
                    if p.is_file() and p.suffix in {'.py','.json'} and '__pycache__' not in p.parts]
    source_paths += [Path(__file__).resolve(),ROOT/'RUT_Science/rut_science/science_bot/presentation.py',tasks]
    before = {p.relative_to(ROOT).as_posix():sha(p) for p in source_paths}
    cases=[]
    for c in data['cases']:
        row=run_case(c,output,live=live,request_cap=request_cap); cases.append(row)
        print(json.dumps({'case':row['id'],'metrics':row.get('metrics'),'error':row.get('error')},ensure_ascii=False),flush=True)
    if before != {n:sha(ROOT/n) for n in before}:raise ValueError('Evaluation inputs changed during run')
    metrics=[c['metrics'] for c in cases if 'metrics' in c]
    result={'schema_version':'planning_mainline_evaluation_v1','checked_utc':datetime.now(timezone.utc).isoformat(),
        'mode':'live_natural_language' if live else 'offline_explicit_answer_rule_baseline',
        'provenance':data['provenance'],'case_count':len(cases),
        'expected_outcomes_met':sum(m['expected_outcome_met'] for m in metrics),
        'reviewable_designs':sum(m['outcome']=='reviewable_design' for m in metrics),
        'justified_blocked_drafts':sum(m['outcome']=='blocked_with_evidence_step' for m in metrics),
        'unnecessary_questions':sum(len(m['unnecessary_question_turns']) for m in metrics),
        'no_progress_question_turns':sum(len(m['no_progress_question_turns']) for m in metrics),
        'host_violations':sum(len(m['host_violation_turns']) for m in metrics),
        'automatic_design_readouts':sum(m['automatic_design_readout'] for m in metrics),
        'model_requests':sum(c.get('resources',{}).get('llm_requests',0) for c in cases),
        'human_participants':0,'human_quality_scores':None,'understanding_improvement_measured':False,
        'real_scientific_executions':0,'source_sha256':before,'cases':cases}
    write(output/'results.json',result)
    queue=[{'case_id':c['id'],'review_status':'pending','reviewer':None,'reviewed_at':None,
            'question_relevance':None,'option_usefulness':None,'critical_omissions':None,
            'plan_testability':None,'researcher_explanation':None,'consent':None}
           for c in data['cases']]
    write(output/'human_review_queue.json',queue)
    print(json.dumps({k:v for k,v in result.items() if k not in {'cases','source_sha256','provenance'}},ensure_ascii=False))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True,help='Fresh output directory; refuses to overwrite')
    p.add_argument('--live',action='store_true',help='Explicitly allow real model requests for natural answers')
    p.add_argument('--request-cap',type=int,default=12)
    args=p.parse_args()
    if not 1<=args.request_cap<=20:p.error('request cap must be 1..20 per case')
    result=evaluate(args.output,live=args.live,request_cap=args.request_cap)
    return 0 if result['expected_outcomes_met']==result['case_count'] else 1


if __name__=='__main__':raise SystemExit(main())
