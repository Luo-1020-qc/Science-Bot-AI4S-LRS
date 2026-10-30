"""Finalize only the authorized interface layer; never rewrite prior evidence."""
import json
from integrity import ROOT,INTERFACE_RECORD,INTERFACE_HOST_FILES,INTERFACE_NEW_FILES,sha,check_project


def main():
    if (ROOT/'docs/integration/question_tool_2026-10-29/authorized_source_changes.json').exists():
        from finalize_question_tool import main as finalize_current_question_tool
        return finalize_current_question_tool()
    record=ROOT/INTERFACE_RECORD
    before=json.loads((record/'before_snapshot.json').read_text(encoding='utf-8'))
    packaging=json.loads((record/'before_packaging.json').read_text(encoding='utf-8'))
    files={**before['files'],**packaging['files']}
    for name,checksum in {**before['unchanged_history'],**before['provider_and_configuration']}.items():
        if sha(ROOT/name)!=checksum:raise ValueError('Prior evidence or API modified: '+name)
    changes={name:{'before_sha256':files[name],'sha256':sha(ROOT/name),
        'reason':'User authorized terminal and local-browser entry/delivery examples on the existing planning engine; no MetaGPT, model or scientific execution changes'}
        for name in sorted(INTERFACE_HOST_FILES)}
    runtime={name:sha(ROOT/name) for name in sorted(INTERFACE_HOST_FILES|INTERFACE_NEW_FILES)}
    (record/'authorized_source_changes.json').write_text(json.dumps({'files':changes},indent=2)+'\n',encoding='utf-8')
    (record/'runtime_manifest.json').write_text(json.dumps({'sha256':runtime,'scope':'Terminal/browser presentation, launch and packaged assets; prior planning/API/weights unchanged'},indent=2)+'\n',encoding='utf-8')
    print(json.dumps(check_project()))


if __name__=='__main__':main()
