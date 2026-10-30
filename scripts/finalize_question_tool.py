"""Append the authorized question-tool layer; preserve all earlier receipts."""
import json
from integrity import (ROOT, QUESTION_RECORD, QUESTION_HOST_FILES, QUESTION_NEW_FILES,
                       QUESTION_TRAINING_FILES, sha, check_project)


def main():
    record = ROOT/QUESTION_RECORD
    before = json.loads((record/'before_snapshot.json').read_text(encoding='utf-8'))
    for name, checksum in {**before['unchanged_history'], **before['provider_and_configuration']}.items():
        if sha(ROOT/name) != checksum:
            raise ValueError('Earlier receipt/provider modified: '+name)
    changes = {name: {'before_sha256': before['files'][name], 'sha256': sha(ROOT/name),
        'reason': 'User authorized a trainable boundary-clarification question tool; existing scientific execution, model provider and weights preserved'}
        for name in sorted(QUESTION_HOST_FILES)}
    for name, value in {
        'authorized_source_changes.json': {'files': changes},
        'runtime_manifest.json': {'sha256': {n: sha(ROOT/n) for n in sorted(QUESTION_HOST_FILES|QUESTION_NEW_FILES)}},
        'training_manifest.json': {'sha256': {n: sha(ROOT/n) for n in sorted(QUESTION_TRAINING_FILES)}}}.items():
        (record/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(check_project()))


if __name__ == '__main__':
    main()
