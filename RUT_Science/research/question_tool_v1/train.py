"""Offline synthetic question-selection BC experiment; no LLM fine tuning or PPO."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'RUT_Science'))
from rut_science.science_bot.general.planning.blueprint import FIELDS
from rut_science.science_bot.general.planning.ledger import apply, accept, contract_hash
from rut_science.science_bot.general.planning.clarification import remember
from rut_science.science_bot.general.planning.question_tool import candidates
from rut_science.science_bot.general.planning.question_ranker import FEATURES, VERSION, features, score
from rut_science.science_bot.interface_demo import example_state, PILOT_ANSWER

HERE = Path(__file__).resolve().parent
SEED = 20261029


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def teacher_weights():
    # Explicit scripted curriculum, not human preference or scientific ground truth.
    values = {'kind:proposal': 3, 'kind:evidence_plan': 1, 'kind:refine': 2,
        'unresolved_prerequisites': -12, 'affected_dependents': 3, 'recently_asked': -1.5,
        'field:research_question': 5, 'field:objective_type': 4, 'field:scope': 3,
        'field:experimental_unit': 3, 'field:outcomes': 2, 'field:design': 1}
    return [values.get(f, 0) for f in FEATURES]


def prepare():
    if (HERE/'dataset.json').exists():
        raise ValueError('Frozen dataset already exists; create a new experiment version')
    rng = random.Random(SEED)
    families = {'train': ['synthetic_field', 'battery_lifetime', 'cell_assay', 'forecast', 'paired_sensor', 'image_baseline'],
        'dev': ['crop_block', 'chemical_screen'], 'test': ['software_replication', 'elasticity_field', 'water_quality', 'time_group_split']}
    groups = []
    for split, names in families.items():
        for family in names:
            for index in range(16):
                state = example_state()
                state['id'] = hashlib.sha256((family+str(index)).encode()).hexdigest()[:32]
                state['pending'] = None
                bank = {f: r['value'] for f, r in state['facts'].items()}
                bank['sampling'] = PILOT_ANSWER
                bank['research_question'] = '合成任务 '+family+'：比较已声明候选与基线，决定是否继续研究。'
                state['facts'] = {f: {'value': value, 'quote': value, 'status': 'declared', 'turn': 1} for f, value in bank.items()}
                state['unknown'] = []
                omitted = rng.sample(list(FIELDS), rng.randint(3, 9))
                for field in omitted:
                    state['facts'].pop(field, None)
                if index % 3 == 0:
                    state['unknown'] = [rng.choice(omitted)]
                if index % 4 == 0:
                    field = rng.choice(list(state['facts']))
                    state['facts'][field]['status'] = 'proposed'
                if index % 5 == 0:
                    field = rng.choice(list(state['facts']))
                    state['conflicts'][field] = [deepcopy(state['facts'][field]),
                        {'value': '另一项合成声明，需要用户更正', 'quote': '另一项合成声明，需要用户更正', 'status': 'declared', 'turn': 2}]
                if index % 7 == 0:
                    field = rng.choice(list(state['facts']))
                    state['stale'][field] = '合成上游边界已改变，需用户重新核对'
                if index % 2:
                    field = rng.choice(list(FIELDS))
                    state['question_history'] = [{'field': field, 'kind': 'missing', 'question': '之前的合成澄清问题',
                        'turn': 1, 'origin': 'template', 'basis_hash': contract_hash(state)}]
                rows, _ = candidates(state)
                if not rows:
                    continue
                target = max(rows, key=lambda q: score(features(state, q), teacher_weights()))['field']
                groups.append({'case_id': family+'_'+str(index), 'split': split, 'source_group': family,
                    'source_type': 'scripted_synthetic_not_expert', 'state': state,
                    'private_answer_bank': bank, 'preferred_field': target})
    dump(HERE/'dataset.json', groups)
    dump(HERE/'dataset_manifest.json', {'sha256': {'dataset.json': sha(HERE/'dataset.json')},
        'seed': SEED, 'source_groups': families, 'human_expert_labels': 0,
        'limitations': 'Disjoint named source groups share the same synthetic generator, answer templates and scripted teacher; not blind or real-world generalization.'})
    print('Prepared frozen synthetic cases:', len(groups))


def data():
    manifest = json.loads((HERE/'dataset_manifest.json').read_text(encoding='utf-8'))
    if sha(HERE/'dataset.json') != manifest['sha256']['dataset.json']:
        raise ValueError('Frozen question dataset changed')
    cases = json.loads((HERE/'dataset.json').read_text(encoding='utf-8'))
    splits = {s: {r['source_group'] for r in cases if r['split'] == s} for s in ('train', 'dev', 'test')}
    if any(splits[a] & splits[b] for a, b in (('train', 'dev'), ('train', 'test'), ('dev', 'test'))):
        raise ValueError('Question source groups overlap')
    return cases


def fit(cases):
    pairs = []
    for case in cases:
        if case['split'] != 'train':
            continue
        rows, _ = candidates(case['state'])
        x = {q['field']: np.asarray(features(case['state'], q)) for q in rows}
        pairs += [x[case['preferred_field']]-vector for f, vector in x.items() if f != case['preferred_field']]
    matrix = np.asarray(pairs)
    weights = np.zeros(len(FEATURES))
    initial = weights.copy()
    # Fixed, predeclared run. Dev/test never affect gradients or checkpoint selection.
    for _ in range(800):
        margins = np.clip(matrix @ weights, -40, 40)
        gradient = -(matrix.T @ (1/(1+np.exp(margins))))/len(matrix)+0.001*weights
        weights -= 0.2*gradient
    return weights.tolist(), {'algorithm': 'pairwise_logistic_behavior_cloning', 'epochs': 800,
        'learning_rate': 0.2, 'l2': 0.001, 'training_pairs': len(matrix),
        'initial_weights': initial.tolist(), 'parameter_l2_change': float(np.linalg.norm(weights-initial))}


def rollout(case, weights):
    state = deepcopy(case['state'])
    actions, unknown_violations, invalid = [], 0, 0
    for turn in range(1, 25):
        rows, assessment = candidates(state)
        if not rows:
            break
        chosen = max(rows, key=lambda q: score(features(state, q), weights)) if weights else rows[0]
        field, kind = chosen['field'], chosen['kind']
        identity = contract_hash(state)
        if kind == 'evidence_plan':
            state.setdefault('evidence_actions', {})[field] = {'text': '先查找合成先导记录并请研究者核实，不填入未知数值',
                'turn': turn, 'status': 'user_proposed_step_not_evidence'}
            unknown_violations += int(field not in state['unknown'] or field in state['facts'])
        elif kind in {'proposal', 'stale'}:
            accept(state, [field], turn)
        else:
            value = case['private_answer_bank'][field]
            apply(state, {'updates': {field: {'value': value, 'quote': value, 'status': 'declared'}}, 'unknown': []}, turn, revise=True)
        remember(state, [chosen], turn)
        actions.append({'field': field, 'kind': kind, 'before_hash': identity,
            'after_hash': contract_hash(state), 'remaining_blockers': len(candidates(state)[1]['blockers'])})
    else:
        invalid += 1
    return {'case_id': case['case_id'], 'turns': len(actions), 'steps': actions,
        'unknown_overwrites': unknown_violations, 'budget_exhausted': bool(invalid),
        'ready_for_review': candidates(state)[1]['ready'], 'unknown_retained': list(state['unknown']),
        'execution_authorized': False}


def evaluate(cases, weights):
    result = {}
    for split in ('train', 'dev', 'test'):
        selected = [r for r in cases if r['split'] == split]
        agreement = {'rule': 0, 'trained': 0}
        for case in selected:
            rows, _ = candidates(case['state'])
            agreement['rule'] += int(rows[0]['field'] == case['preferred_field'])
            chosen = max(rows, key=lambda q: score(features(case['state'], q), weights))
            agreement['trained'] += int(chosen['field'] == case['preferred_field'])
        result[split] = {'cases': len(selected), 'scripted_teacher_agreement': agreement}
    trajectories = {policy: [rollout(case, weights if policy == 'trained' else None)
        for case in cases if case['split'] == 'test'] for policy in ('rule', 'trained')}
    result['test_rollouts'] = {policy: {'cases': len(rows), 'total_questions': sum(r['turns'] for r in rows),
        'unknown_overwrites': sum(r['unknown_overwrites'] for r in rows),
        'budget_exhausted': sum(r['budget_exhausted'] for r in rows),
        'ready_for_review': sum(r['ready_for_review'] for r in rows)} for policy, rows in trajectories.items()}
    return result, trajectories


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--output', type=Path, default=HERE/'run_001')
    args = parser.parse_args()
    if args.prepare:
        prepare()
        return
    args.output.mkdir(parents=True, exist_ok=False)
    cases = data()
    weights, training = fit(cases)
    model = {'version': VERSION, 'features': list(FEATURES), 'weights': weights,
        'training_source': 'scripted_synthetic_not_expert', 'dataset_sha256': sha(HERE/'dataset.json'),
        'default_enabled': False, 'language_model_weights_changed': False}
    dump(args.output/'policy.json', model)
    result, trajectories = evaluate(cases, weights)
    dump(args.output/'trajectories.json', trajectories)
    dump(args.output/'results.json', {'training': training, 'evaluation': result,
        'seed': SEED, 'model_requests': 0, 'real_scientific_executions': 0, 'human_expert_labels': 0,
        'understanding_improvement_measured': False, 'evaluation_type': 'source_group_held_out_synthetic_diagnostic',
        'limitations': 'Teacher agreement measures imitation of the scripted curriculum, not human question quality or scientific validity.'})
    dump(args.output/'manifest.json', {'sha256': {p.name: sha(p) for p in sorted(args.output.glob('*.json'))},
        'training_source_sha256': sha(Path(__file__))})
    print(json.dumps(result))


if __name__ == '__main__':
    main()
