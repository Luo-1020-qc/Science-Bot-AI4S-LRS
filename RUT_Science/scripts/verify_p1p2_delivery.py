"""Audit v0.5 deliverables without model requests or changing old run records."""
import json
from pathlib import Path
import re
from urllib.parse import unquote

from rut_science.chat_verification import verify_chat
from rut_science.configuration import load_profiles
from rut_science.planning_agent import read_checkpoint
from rut_science.planning_evaluation import verify_artifacts
from rut_science.util import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
CHAT = 'chat_ps_offline_release_2026-10-15_v050'
DARCY_CHAT = 'chat_darcy_offline_release_2026-10-15_v050'
RECOVERY = 'plan_p1p2_recovery_release_2026-10-15_v050'
API_RUNS = ['chat_api_p1p2_2026-10-15_v050', 'chat_api_p1p2_network_2026-10-15_v050',
            'chat_api_p1p2_final_2026-10-15_v050']


def main():
    conversation = verify_chat(ROOT/'outputs'/CHAT)
    darcy_conversation = verify_chat(ROOT/'outputs'/DARCY_CHAT)
    recovery = verify_artifacts(ROOT/'outputs'/RECOVERY)
    state = read_checkpoint(ROOT/'outputs'/RECOVERY)
    calls = [e for e in state['events'] if e['event_type'] == 'tool_call']
    errors = [e for e in calls if e['tool_result']['status'] != 'ok']
    score = state['score']
    recovered_safely = (len(calls) == 9 and len(errors) == 1 and errors[0]['fault_injected']
        and state['environment_state']['budget']['train_calls'] == 2 and state['environment_state']['budget']['test_calls'] == 1
        and score['strict_execution_success'] is False and score['recovery_success'] is True
        and all(score['recovery_checks'].values()) and state['plan']['version'] == 2)
    current_sources = {p.name: digest(p.read_text(encoding='utf-8')) for p in (ROOT/'rut_science').glob('*.py')}
    snapshots_match = all(current_sources == read_checkpoint(path)['source_hashes'] if path.name in {CHAT, DARCY_CHAT} else
        current_sources == json.loads((path/'manifest.json').read_text(encoding='utf-8'))['source_hashes']
        for path in [ROOT/'outputs'/CHAT, ROOT/'outputs'/DARCY_CHAT, ROOT/'outputs'/RECOVERY])
    normal = read_checkpoint(ROOT/'outputs'/DARCY_CHAT/'execution_001')
    same_science = (normal['spec'] == state['spec'] and normal['tool_calls'] == 8 and normal['score']['strict_execution_success'] is True
        and normal['environment_state']['reports'] == state['environment_state']['reports'])
    api = []
    for name in API_RUNS:
        path = ROOT/'outputs'/name
        state_api = read_checkpoint(path)
        ledger = json.loads((path/'budget.json').read_text(encoding='utf-8'))
        api.append({'output': name, 'phase': state_api['phase'], 'executions': len(state_api['executions']),
            'requests': ledger['requests'], 'unknown_token_reservations': ledger['unresolved_token_reservations'],
            'request_statuses': [call['status'] for call in ledger['calls']]})
    secrets = [v for p in load_profiles() for k, v in p.items()
               if k.lower() in {'api', 'api_2', 'api_key', 'api_key_2', 'api2'} and isinstance(v, str)]
    leaks, count = [], 0
    folders = [ROOT/'rut_science', ROOT/'scripts', ROOT/'docs', ROOT/'outputs'/CHAT, ROOT/'outputs'/DARCY_CHAT, ROOT/'outputs'/RECOVERY]
    folders += [ROOT/'outputs'/name for name in API_RUNS]
    for folder in folders:
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix in {'.py', '.json', '.jsonl', '.md', '.ps1'}:
                count += 1
                text = path.read_text(encoding='utf-8-sig')
                if any(secret and secret in text for secret in secrets):
                    leaks.append(str(path.relative_to(ROOT)))
    links = []
    for doc in [ROOT/'docs/Research_Interaction_and_Recovery_zh.md', ROOT/'docs/P1_P2_Delivery_2026-10-15_zh.md']:
        for link in re.findall(r'\]\(([^)]+)\)', doc.read_text(encoding='utf-8')):
            if not link.startswith(('http://', 'https://', '#')):
                links.append((doc.parent/unquote(link.split('#')[0])).exists())
    passed = conversation['status'] == darcy_conversation['status'] == recovery['status'] == 'passed' and recovered_safely and same_science and snapshots_match and not leaks and all(links)
    result = {'status': 'passed' if passed else 'failed', 'scope': 'offline P1/P2 engineering and real Darcy numerical verification',
        'api_end_to_end_status': 'not_verified_transport_timeouts', 'conversation': conversation, 'darcy_conversation': darcy_conversation, 'recovery': recovery,
        'normal_and_fault_runs_same_scientific_protocol_and_report': same_science,
        'strict_failure_retained_and_bounded_recovery_verified': recovered_safely, 'current_sources_match_frozen_runs': snapshots_match,
        'api_attempts': api, 'credential_scan_files': count, 'credential_leak_files': leaks,
        'document_links_checked': len(links), 'document_links_passed': all(links)}
    write_json(ROOT/'outputs/p1p2_delivery_verification_v050.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
