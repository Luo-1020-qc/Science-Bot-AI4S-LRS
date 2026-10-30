"""Host-owned boundary questions, optional trained ranking and local learning traces."""
from copy import deepcopy
import json
import re

from ....util import digest, write_json
from ..contracts import ToolSpec
from .blueprint import FIELDS
from .ledger import validate, contract_hash
from .question_ranker import features, load_policy, score, FEATURES

SPEC = ToolSpec('question_tool',
    'Choose the next research-boundary question from the host ledger. Read-only. '
    'Answers must return through the original planning intake; never grants execution or fills unknown facts.',
    {'type': 'object', 'properties': {
        'policy': {'type': 'string', 'enum': ['rule', 'trained']},
        'max_questions': {'type': 'integer', 'minimum': 1, 'maximum': 2}},
     'additionalProperties': False}, domain='planning',
    preconditions=('host_planning_state',), resource_estimate={'model_requests': 0})


def candidates(state):
    from .runtime import review, _question_candidates
    from .clarification import allowed_fields
    assessment = review(state)
    allowed = allowed_fields(state, assessment)
    rows = []
    for q in _question_candidates(state, assessment):
        if q['kind'] != allowed.get(q['field']) or any(r['field'] == q['field'] for r in rows):
            continue
        rows.append(deepcopy(q))
    # Urgent conflicts/dependencies are host constraints, never learned permissions.
    urgent = set(state['conflicts']) or set(state['stale'])
    if urgent:
        rows = [q for q in rows if q['field'] in urgent]
    return rows, assessment


def execute(arguments, context):
    state = deepcopy(context.get('planning_state'))
    validate(state)
    rows, assessment = candidates(state)
    vectors = {q['field']: features(state, q) for q in rows}
    requested = arguments.get('policy', 'rule')
    actual, reason, policy_hash = 'rule', 'host_template_order', None
    if requested == 'trained' and rows:
        try:
            model = load_policy()
            rows.sort(key=lambda q: score(vectors[q['field']], model['weights']), reverse=True)
            actual, reason, policy_hash = 'trained', 'synthetic_candidate_only', digest(model)
        except (ValueError, OSError, TypeError):
            reason = 'candidate_unavailable_rule_fallback'
    selected = rows[:arguments.get('max_questions', 1)]
    return {'schema_version': 'question_tool_v1', 'plan_hash': contract_hash(state),
        'action': 'ask' if selected else 'review' if assessment['ready'] else 'wait_for_evidence_or_revision',
        'questions': selected, 'policy': actual, 'requested_policy': requested, 'reason': reason,
        'policy_hash': policy_hash, 'candidate_features': vectors, 'feature_names': list(FEATURES),
        'blockers': len(assessment['blockers']), 'execution_authorized': False,
        'scientific_claim_verified': False, 'ledger_updated': False}


def register(registry):
    registry.register(SPEC, execute)


def config(session, state):
    value = session.meta.get('question_tool', {})
    return value if value.get('plan_id') == state['id'] and value.get('enabled') else None


def _path(session, ref):
    if not re.fullmatch(r'question_tool/[a-f0-9]{32}/(?:decisions|transitions)/[0-9]{5}\.json', ref):
        raise ValueError('Invalid question trace reference')
    path = session.folder/ref
    if path.resolve() != path.absolute() or not path.is_relative_to(session.folder):
        raise ValueError('Question trace cannot redirect outside session')
    return path


def _read(session, ref, sha256):
    path = _path(session, ref)
    if not path.is_file() or path.stat().st_size > 200_000:
        raise ValueError('Question trace unavailable')
    value = json.loads(path.read_text(encoding='utf-8'))
    if digest(value) != sha256:
        raise ValueError('Question trace changed')
    return value


def _store(session, ref, value):
    path = _path(session, ref)
    if path.exists():
        raise ValueError('Question trace cannot overwrite a prior decision')
    write_json(path, value)
    return {'ref': ref, 'sha256': digest(value)}


def control(session, state, payload):
    command = payload.strip() or 'rule'
    if command in {'history', 'export'}:
        rows = trace_rows(session, state)
        if command == 'history':
            return '边界问答记录（不代表问题已获专家认可）：\n'+json.dumps(rows, ensure_ascii=False, indent=2)
        target = session.folder/'question_tool'/state['id']/'training_observations.jsonl'
        if target.resolve() != target.absolute():
            raise ValueError('Question export cannot redirect')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows), encoding='utf-8')
        return '已导出脱敏结构化观察：'+str(target)+'\n不含问题原文、回答原文或论文片段；标签未经专家审阅，不能直接当作正确答案或PPO采样。'
    if command == 'off':
        session.meta.pop('question_tool', None)
        return '边界问答工具已关闭，原规划与动态澄清继续可用。'
    if command not in {'rule', 'trained'}:
        raise ValueError('使用 /plan question [rule|trained|history|export|off]')
    old = config(session, state)
    if not old or old['policy'] != command:
        session.meta['question_tool'] = {'plan_id': state['id'], 'enabled': True, 'policy': command}
    return None


def choose(session, state, turn, *, responding=False):
    cfg = config(session, state)
    if not cfg:
        return None
    pending = cfg.get('pending')
    if pending and not responding:
        old = _read(session, **pending)
        if old['plan_hash'] == contract_hash(state):
            return {**old['tool_result'], 'questions': deepcopy(old['displayed_questions']), 'reused_pending': True}
    return session._execute_tool('question_tool', {'policy': cfg['policy'], 'max_questions': 1},
        {'planning_state': deepcopy(state)}, f'question_tool_{state["id"]}_{turn}')


def record_question(session, state, result, questions, turn):
    cfg = config(session, state)
    if not cfg or result.get('reused_pending') or not questions:
        return
    value = {'schema_version': 'question_decision_v1', 'plan_hash': contract_hash(state),
        'turn': turn, 'tool_result': deepcopy(result), 'displayed_questions': deepcopy(questions)}
    row = _store(session, f'question_tool/{state["id"]}/decisions/{turn:05d}.json', value)
    cfg['pending'] = row
    session.meta.setdefault('question_tool_records', []).append({'plan_id': state['id'], 'decision': row})


def record_answer(session, before, after, turn):
    from .runtime import review
    cfg = config(session, after)
    if not cfg or not before or not cfg.get('pending'):
        return
    pending = cfg['pending']
    decision = _read(session, **pending)
    changed = [f for f in FIELDS if before['facts'].get(f) != after['facts'].get(f)
               or (f in before['unknown']) != (f in after['unknown'])
               or before['conflicts'].get(f) != after['conflicts'].get(f)
               or before['stale'].get(f) != after['stale'].get(f)
               or before.get('evidence_actions', {}).get(f) != after.get('evidence_actions', {}).get(f)]
    targets = [q['field'] for q in decision['displayed_questions']]
    row = {'schema_version': 'question_transition_v1', 'decision': pending,
        'answer_turn': turn, 'before_hash': contract_hash(before), 'after_hash': contract_hash(after),
        'changed_fields': changed, 'answered_target_fields': [f for f in targets if f in changed],
        'remaining_unknown': list(after['unknown']), 'blockers_before': len(review(before)['blockers']),
        'blockers_after': len(review(after)['blockers']), 'supervision': 'unreviewed_user_observation',
        'ppo_eligible': False, 'execution_authorized': False}
    stored = _store(session, f'question_tool/{after["id"]}/transitions/{turn:05d}.json', row)
    for record in reversed(session.meta.get('question_tool_records', [])):
        if record['decision'] == pending:
            record['transition'] = stored
            break
    cfg.pop('pending', None)


def trace_rows(session, state):
    """Explicit export includes numeric features/field outcomes, no raw dialogue/evidence."""
    result = []
    for record in session.meta.get('question_tool_records', []):
        if record['plan_id'] != state['id']:
            continue
        decision = _read(session, **record['decision'])
        transition = _read(session, **record['transition']) if record.get('transition') else None
        result.append({'schema_version': 'question_training_observation_v1',
            'source_group': digest(state['id']), 'candidate_features': decision['tool_result']['candidate_features'],
            'feature_names': decision['tool_result']['feature_names'],
            'selected_fields': [q['field'] for q in decision['displayed_questions']],
            'policy': decision['tool_result']['policy'], 'policy_hash': decision['tool_result']['policy_hash'],
            'outcome': {k: v for k, v in transition.items() if k not in {'decision', 'schema_version'}} if transition else None,
            'supervision': 'unreviewed_user_observation', 'ppo_eligible': False})
    return result
