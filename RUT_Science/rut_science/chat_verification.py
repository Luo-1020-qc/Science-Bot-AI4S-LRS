"""Read-only research audit, except publishing its verification result; no API."""
import json
from pathlib import Path

from .intake_contract import validate_receipt, evidence_matches
from .planning_agent import read_checkpoint
from .planning_evaluation import verify_artifacts
from .research_spec import ResearchSpec
from .util import digest, write_json


def verify_chat(output):
    output = Path(output).resolve()
    state = read_checkpoint(output)
    for name, checksum in state['source_hashes'].items():
        if digest((output/'source_snapshot'/name).read_text(encoding='utf-8')) != checksum:
            raise ValueError('Frozen conversation source changed')
    if json.loads((output/'conversation.json').read_text(encoding='utf-8')) != state['turns']:
        raise ValueError('Conversation differs from checkpoint')
    receipts = {}
    for path in (output/'confirmations').glob('*.json'):
        receipt = json.loads(path.read_text(encoding='utf-8'))
        validate_receipt(receipt, ResearchSpec(**receipt['draft']['spec']))
        turn = state['turns'][receipt['turn']]
        if turn.get('role') != 'user' or turn.get('actor') != receipt['actor'] or turn.get('content', '').strip() != receipt['command']:
            raise ValueError('Confirmation was not submitted by the recorded operator')
        if not any(t['role'] == 'assistant' and receipt['bound_draft_hash'] in t['content'] for t in state['turns'][:receipt['turn']]):
            raise ValueError('Confirmed draft was never presented')
        for field, record in receipt['draft']['provenance'].items():
            if record['origin'] == 'user':
                user = state['turns'][record['turn']]
                if user['role'] != 'user' or not evidence_matches(field, record['value'], record['evidence'], user['content']):
                    raise ValueError('User field lacks semantic evidence in the indicated user turn')
        receipts[receipt['confirmation_hash']] = receipt
    calls = list(state['model_calls'])
    verified = []
    for item in state['executions']:
        path = Path(item['output']).resolve()
        if not path.is_relative_to(output) or item['confirmation_hash'] not in receipts:
            raise ValueError('Execution is outside its confirmed conversation')
        manifest = json.loads((path/'manifest.json').read_text(encoding='utf-8'))
        if manifest['intake_confirmation'] != receipts[item['confirmation_hash']]:
            raise ValueError('Execution confirmation differs from conversation receipt')
        verification = verify_artifacts(path)
        calls.extend(read_checkpoint(path)['model_calls'])
        verified.append({'output': path.name, **verification})
    ledger = json.loads((output/'budget.json').read_text(encoding='utf-8'))
    indices = [call['request_index'] for call in calls]
    if sorted(indices) != list(range(1, ledger['requests']+1)) or len(ledger['calls']) != ledger['requests']:
        raise ValueError('Shared API ledger contains missing or duplicated requests')
    for call in calls:
        if digest(call['request_body']) != call['request_body_hash'] or ledger['calls'][call['request_index']-1]['request_body_hash'] != call['request_body_hash']:
            raise ValueError('Model request body or shared ledger hash mismatch')
    result = {'status': 'passed', 'confirmation_count': len(receipts), 'executions': verified,
        'operator_confirmation_and_provenance_verified': True, 'shared_api_budget_verified': True,
        'requests': ledger['requests'], 'reported_prompt_tokens': ledger['reported_prompt_tokens'],
        'reported_completion_tokens': ledger['reported_completion_tokens'],
        'unresolved_token_reservations': ledger['unresolved_token_reservations'],
        'actors': sorted({r['actor'] for r in receipts.values()})}
    write_json(output/'verification.json', result)
    return result
