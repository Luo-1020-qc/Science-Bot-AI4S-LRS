"""Append only this authorized upgrade's hashes; preserve all prior manifests."""
import json
from integrity import (ROOT, DYNAMIC_RECORD, DYNAMIC_CHANGED_FILES, DYNAMIC_NEW_FILES,
                       DYNAMIC_HISTORY, PRIVACY_RECORD, PRIVACY_HOST, sha, check_project)


def main():
    record = ROOT/DYNAMIC_RECORD
    before = json.loads((record/'before_snapshot.json').read_text(encoding='utf-8'))
    if set(before['unchanged_history_and_provider']) != DYNAMIC_HISTORY:
        raise ValueError('Incomplete unchanged history constraints')
    for name, checksum in before['unchanged_history_and_provider'].items():
        if sha(ROOT/name) != checksum:
            raise ValueError('Prior planning/history/API file changed: '+name)
    changes = {name: {'before_sha256': before['files'][name], 'sha256': sha(ROOT/name),
        'reason': 'User authorized grounded dynamic clarification, explicit paper excerpts, template fallback and independent synthetic-task evaluation'}
        for name in sorted(DYNAMIC_CHANGED_FILES)}
    runtime = {name: sha(ROOT/name) for name in sorted(DYNAMIC_CHANGED_FILES|DYNAMIC_NEW_FILES)}
    (record/'authorized_source_changes.json').write_text(json.dumps({'files': changes}, indent=2)+'\n', encoding='utf-8')
    (record/'runtime_manifest.json').write_text(json.dumps({'sha256': runtime,
        'scope': 'Chained dynamic clarification upgrade; prior planning manifests, API and weights unchanged'}, indent=2)+'\n', encoding='utf-8')
    privacy = ROOT/PRIVACY_RECORD
    if (privacy/'before_snapshot.json').exists():
        prior = json.loads((privacy/'before_snapshot.json').read_text(encoding='utf-8'))
        if prior['dynamic_runtime_manifest_sha256'] != sha(record/'runtime_manifest.json'):
            raise ValueError('Question runtime changed after the history privacy snapshot')
        overlay = {PRIVACY_HOST: {'before_sha256': prior['before_sha256'], 'sha256': sha(ROOT/PRIVACY_HOST),
            'reason': 'User-authorized explicit paper sharing requires local-only planning displays to stay out of later general-chat history'}}
        (privacy/'authorized_source_changes.json').write_text(json.dumps({'files': overlay}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(check_project()))


if __name__ == '__main__': main()
