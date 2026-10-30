"""Check immutable historical baselines plus explicitly chained source upgrades."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[1]
TOOL_RECORD = "docs/integration/tool_library_2026-10-28"
PLANNING_RECORD = "docs/integration/planning_2026-10-29"
TOOL_HOST_FILES = frozenset({
    "RUT_Science/rut_science/science_bot/general/registry.py",
    "RUT_Science/rut_science/science_bot/general/router.py",
    "RUT_Science/rut_science/science_bot/general/conversation.py",
    "RUT_Science/rut_science/science_bot/terminal.py",
})
PLANNING_HOST_FILES = frozenset({
    "RUT_Science/rut_science/science_bot/general/graph.py",
    "RUT_Science/rut_science/science_bot/general/router.py",
    "RUT_Science/rut_science/science_bot/general/conversation.py",
    "RUT_Science/rut_science/science_bot/terminal.py",
})
PLANNING_NEW_FILES = frozenset(
    "RUT_Science/rut_science/science_bot/general/planning/"+name
    for name in ("__init__.py", "blueprint.py", "intake.py", "ledger.py", "runtime.py")
)
PROVIDER_FILES = frozenset({
    "RUT_Science/rut_science/science_bot/general/provider.py",
    "RUT_Science/rut_science/configuration.py",
})
DYNAMIC_RECORD = 'docs/integration/dynamic_clarification_2026-10-29'
DYNAMIC_CHANGED_FILES = frozenset('RUT_Science/rut_science/science_bot/general/planning/'+name
    for name in ('ledger.py','blueprint.py','runtime.py'))
DYNAMIC_NEW_FILES = frozenset('RUT_Science/rut_science/science_bot/general/planning/'+name
    for name in ('clarification.py','evidence.py','understanding.py'))
DYNAMIC_HISTORY = frozenset({'docs/cleanup/2026-10-28/protected_current.json',
    TOOL_RECORD+'/authorized_source_changes.json', TOOL_RECORD+'/runtime_manifest.json',
    PLANNING_RECORD+'/before_snapshot.json', PLANNING_RECORD+'/authorized_source_changes.json',
    PLANNING_RECORD+'/runtime_manifest.json'})|PROVIDER_FILES
PRIVACY_RECORD = DYNAMIC_RECORD+'/history_privacy'
PRIVACY_HOST = 'RUT_Science/rut_science/science_bot/general/conversation.py'
INTERFACE_RECORD = 'docs/integration/interfaces_2026-10-29'
INTERFACE_HOST_FILES = frozenset({'RUT_Science/rut_science/science_bot/terminal.py',
    'Start-ScienceBot.ps1','RUT_Science/pyproject.toml','.gitignore'})
INTERFACE_NEW_FILES = frozenset('RUT_Science/rut_science/science_bot/'+name for name in (
    'interface_demo.py','presentation.py','workbench.py','workbench_assets/dist/index.html',
    'workbench_assets/dist/styles.css','workbench_assets/dist/app.js'))|frozenset({'science-bot-web.cmd'})
QUESTION_RECORD = 'docs/integration/question_tool_2026-10-29'
QUESTION_HOST_FILES = frozenset({'RUT_Science/rut_science/science_bot/general/registry.py',
    'RUT_Science/rut_science/science_bot/general/planning/runtime.py', 'RUT_Science/pyproject.toml'})
QUESTION_NEW_FILES = frozenset('RUT_Science/rut_science/science_bot/general/planning/'+name
    for name in ('question_tool.py', 'question_ranker.py', 'question_policy.json'))
QUESTION_TRAINING_FILES = frozenset('RUT_Science/research/question_tool_v1/'+name for name in (
    'train.py', 'dataset.json', 'dataset_manifest.json', 'run_001/policy.json',
    'run_001/results.json', 'run_001/trajectories.json', 'run_001/manifest.json'))
BRANDING_RECORD = 'docs/integration/branding_2026-10-29'
BRANDING_FILES = frozenset({'RUT_Science/rut_science/science_bot/workbench_assets/dist/index.html',
    'RUT_Science/rut_science/science_bot/workbench_assets/dist/styles.css',
    'RUT_Science/rut_science/science_bot/presentation.py',
    'examples/interfaces/browser.html', 'examples/interfaces/delivery.html'})
CHOICES_RECORD = 'docs/integration/context_choices_2026-10-29'
CHOICES_HOST_FILES = frozenset('RUT_Science/rut_science/science_bot/'+n for n in (
    'general/planning/runtime.py','general/planning/intake.py','general/planning/clarification.py',
    'general/planning/blueprint.py','terminal.py','presentation.py','workbench_assets/dist/app.js'))|frozenset({
    'RUT_Science/pyproject.toml','examples/interfaces/browser.html'})
CHOICES_NEW_FILES = frozenset('RUT_Science/rut_science/science_bot/general/planning/'+n
    for n in ('choices.py','choice_policy.json'))
CHOICES_TRAINING_FILES = frozenset('RUT_Science/research/context_choices_v1/'+n for n in (
    'train.py','dataset.json','dataset_manifest.json','run_001/policy.json','run_001/results.json',
    'run_001/examples.json','run_001/manifest.json'))
MAINLINE_RECORD = 'docs/integration/mainline_2026-10-30'
MAINLINE_HOST_FILES = frozenset({
    'RUT_Science/rut_science/science_bot/general/planning/runtime.py',
    'RUT_Science/rut_science/science_bot/general/planning/ledger.py',
    'RUT_Science/rut_science/science_bot/presentation.py',
    'RUT_Science/rut_science/science_bot/workbench_assets/dist/app.js',
    'RUT_Science/rut_science/science_bot/workbench_assets/dist/index.html',
    '.gitignore', 'examples/interfaces/browser.html', 'examples/interfaces/delivery.html',
    'examples/interfaces/terminal.html',
})
MAINLINE_NEW_FILES = frozenset({'RUT_Science/rut_science/science_bot/general/planning/delivery.py'})
SESSION_HISTORY_RECORD = 'docs/integration/session_history_2026-10-30'
SESSION_HISTORY_HOST_FILES = frozenset('RUT_Science/rut_science/science_bot/'+n for n in (
    'api.py','workbench.py','workbench_assets/dist/app.js','workbench_assets/dist/styles.css'))|frozenset({'examples/interfaces/browser.html'})
SESSION_HISTORY_NEW_FILES = frozenset({'RUT_Science/rut_science/science_bot/session_history.py'})
PDF_RECORD='docs/integration/pdf_reading_2026-10-30'
PDF_HOST_FILES=frozenset('RUT_Science/rut_science/science_bot/'+n for n in (
    'general/planning/evidence.py','general/planning/runtime.py','general/planning/blueprint.py','presentation.py',
    'workbench_assets/dist/app.js','workbench_assets/dist/index.html'))|frozenset({'RUT_Science/pyproject.toml','examples/interfaces/browser.html'})
PDF_NEW_FILES=frozenset('RUT_Science/rut_science/science_bot/general/planning/'+n for n in (
    'pdf_document.py','pdf_worker.py','paper_reading.py'))|frozenset({'requirements-science-bot.lock.txt','examples/papers/synthetic_paper.pdf'})


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""): h.update(chunk)
    return h.hexdigest()


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _hashes(value):
    if type(value) is not dict: raise ValueError("Hash map required")
    for name, checksum in value.items():
        if not isinstance(name, str): raise ValueError("Artifact path must be text")
        path = PurePosixPath(name)
        if (not name or "\\" in name or ":" in name or path.is_absolute()
                or ".." in path.parts or str(path) != name or not isinstance(checksum, str)
                or not re.fullmatch(r"[0-9a-f]{64}", checksum)):
            raise ValueError("Invalid relative artifact path or SHA-256")
    return value


def _file_matches(root, name, expected):
    path = root/name
    return path.is_file() and path.resolve() == path and sha(path) == expected


def _apply_overlay(value, expected, allowed, label):
    if type(value) is not dict or type(value.get("files")) is not dict:
        raise ValueError(label+" overlay requires a files map")
    edits = value["files"]
    if set(edits)-allowed: raise ValueError(label+" overlay exceeds authorized host wiring")
    for name, row in edits.items():
        if type(row) is not dict or set(row) != {"before_sha256", "sha256", "reason"}:
            raise ValueError(label+" source change requires before/after hashes and reason")
        _hashes({name: row["sha256"]}); _hashes({name: row["before_sha256"]})
        if not isinstance(row["reason"], str) or not row["reason"].strip():
            raise ValueError(label+" source change requires an authorization reason")
        if row["before_sha256"] != expected.get(name):
            raise ValueError(label+" overlay does not chain from the prior protected source")
        expected[name] = row["sha256"]
    return edits


def _expectations(root):
    """Construct a chain without mutating either historical source manifest."""
    root = Path(root).resolve()
    original = _hashes(_read(root/"docs/cleanup/2026-10-28/protected_current.json")["sha256"])
    expected = dict(original)
    edits = {}
    tool_record = root/TOOL_RECORD
    overlay = tool_record/"authorized_source_changes.json"
    if overlay.exists(): edits.update(_apply_overlay(_read(overlay), expected, TOOL_HOST_FILES, "Tool integration"))
    runtime_path = tool_record/"runtime_manifest.json"
    runtime = _hashes(_read(runtime_path)["sha256"]) if runtime_path.exists() else {}
    for name, checksum in runtime.items():
        if name in expected and expected[name] != checksum:
            raise ValueError("Historical tool runtime and protected source disagree")
        expected[name] = checksum

    record = root/PLANNING_RECORD
    before_path = record/"before_snapshot.json"
    before = _read(before_path) if before_path.exists() else None
    if before is not None:
        if before.get("version") != "planning_upgrade_before_v1" or set(before.get("files", {})) != PLANNING_HOST_FILES:
            raise ValueError("Planning before snapshot has an unexpected source scope")
        for name, row in before["files"].items():
            if row != {"before_sha256": expected.get(name)}:
                raise ValueError("Planning before snapshot differs from the prior effective source")
        constraints = _hashes(before.get("unchanged_history_and_provider", {}))
        required = {"docs/cleanup/2026-10-28/protected_current.json",
                    TOOL_RECORD+"/authorized_source_changes.json", TOOL_RECORD+"/runtime_manifest.json"}|PROVIDER_FILES
        if set(constraints) != required: raise ValueError("Planning history/provider constraints incomplete")
        if any(not _file_matches(root, name, h) for name, h in constraints.items()):
            raise ValueError("Historical baseline or unchanged API provider/configuration modified")

    new_overlay = record/"authorized_source_changes.json"
    planning_edits = {}
    if new_overlay.exists():
        if before is None: raise ValueError("Planning upgrade lacks a prior source snapshot")
        planning_edits = _apply_overlay(_read(new_overlay), expected, PLANNING_HOST_FILES, "Planning integration")
        edits.update(planning_edits)
    planning_runtime_path = record/"runtime_manifest.json"
    planning_runtime = {}
    if planning_runtime_path.exists():
        if not planning_edits: raise ValueError("Planning runtime requires an authorized source overlay")
        planning_runtime = _hashes(_read(planning_runtime_path)["sha256"])
        allowed = PLANNING_HOST_FILES|PLANNING_NEW_FILES|PROVIDER_FILES
        if set(planning_runtime) != allowed:
            raise ValueError("Planning runtime manifest must pin exactly the authorized host/modules/provider scope")
        for name, checksum in planning_runtime.items():
            if name in expected and expected[name] != checksum:
                raise ValueError("Planning runtime disagrees with the authorized effective source")
            expected[name] = checksum
    dynamic = root/DYNAMIC_RECORD
    dynamic_before_path = dynamic/'before_snapshot.json'
    if dynamic_before_path.exists():
        prior = _read(dynamic_before_path)
        if (prior.get('version') != 'dynamic_clarification_before_v1'
                or set(prior.get('files', {})) != DYNAMIC_CHANGED_FILES
                or set(prior.get('unchanged_history_and_provider', {})) != DYNAMIC_HISTORY):
            raise ValueError('Dynamic clarification before snapshot scope mismatch')
        for name, checksum in _hashes(prior['files']).items():
            if expected.get(name) != checksum:
                raise ValueError('Dynamic clarification does not chain from planning runtime')
        for name, checksum in _hashes(prior['unchanged_history_and_provider']).items():
            if not _file_matches(root, name, checksum):
                raise ValueError('Prior planning/history/API files changed: '+name)
    dynamic_overlay = dynamic/'authorized_source_changes.json'
    if dynamic_overlay.exists():
        if not dynamic_before_path.exists():raise ValueError('Dynamic clarification lacks a before snapshot')
        dynamic_changes = _apply_overlay(_read(dynamic_overlay), expected, DYNAMIC_CHANGED_FILES, 'Dynamic clarification')
        if set(dynamic_changes) != DYNAMIC_CHANGED_FILES:
            raise ValueError('Dynamic clarification source changes incomplete')
        dynamic_runtime = _hashes(_read(dynamic/'runtime_manifest.json')['sha256'])
        if set(dynamic_runtime) != DYNAMIC_CHANGED_FILES|DYNAMIC_NEW_FILES:
            raise ValueError('Dynamic clarification runtime scope mismatch')
        for name, checksum in dynamic_runtime.items():
            if name in expected and expected[name] != checksum:
                raise ValueError('Dynamic runtime disagrees with authorized source changes')
            expected[name] = checksum
    privacy = root/PRIVACY_RECORD
    if (privacy/'authorized_source_changes.json').exists():
        prior = _read(privacy/'before_snapshot.json')
        if (prior.get('version') != 'planning_history_privacy_before_v1' or prior.get('file') != PRIVACY_HOST
                or prior.get('before_sha256') != expected.get(PRIVACY_HOST)
                or prior.get('dynamic_runtime_manifest_sha256') != sha(dynamic/'runtime_manifest.json')):
            raise ValueError('Planning history privacy overlay has an invalid prior source')
        privacy_changes = _apply_overlay(_read(privacy/'authorized_source_changes.json'), expected,
                                         frozenset({PRIVACY_HOST}), 'Planning history privacy')
        if set(privacy_changes) != {PRIVACY_HOST}:
            raise ValueError('Planning history privacy overlay is incomplete')
    interface = root/INTERFACE_RECORD
    if (interface/'authorized_source_changes.json').exists():
        before = _read(interface/'before_snapshot.json')
        packaging = _read(interface/'before_packaging.json')
        files = {**before.get('files',{}),**packaging.get('files',{})}
        if (before.get('version') != 'interfaces_before_v1' or packaging.get('version') != 'interfaces_packaging_before_v1'
                or set(files) != INTERFACE_HOST_FILES):
            raise ValueError('Interface source snapshot scope mismatch')
        for name,checksum in _hashes(files).items():
            if name in expected and expected[name] != checksum:
                raise ValueError('Interface source does not chain from previous runtime')
            expected[name] = checksum
        for name,checksum in _hashes({**before['unchanged_history'],**before['provider_and_configuration']}).items():
            if not _file_matches(root,name,checksum):raise ValueError('Interface prior evidence or API changed: '+name)
        interface_edits = _apply_overlay(_read(interface/'authorized_source_changes.json'),expected,INTERFACE_HOST_FILES,'Interfaces')
        if set(interface_edits) != INTERFACE_HOST_FILES:raise ValueError('Interface source overlay incomplete')
        interface_runtime = _hashes(_read(interface/'runtime_manifest.json')['sha256'])
        if set(interface_runtime) != INTERFACE_HOST_FILES|INTERFACE_NEW_FILES:raise ValueError('Interface runtime scope mismatch')
        for name,checksum in interface_runtime.items():
            if name in expected and expected[name] != checksum:raise ValueError('Interface runtime disagrees with authorized changes')
            expected[name] = checksum
    question = root/QUESTION_RECORD
    if (question/'authorized_source_changes.json').exists():
        before = _read(question/'before_snapshot.json')
        if before.get('version') != 'question_tool_before_v1' or set(before.get('files', {})) != QUESTION_HOST_FILES:
            raise ValueError('Question tool before source scope mismatch')
        for name, checksum in _hashes(before['files']).items():
            if expected.get(name) != checksum:
                raise ValueError('Question tool source does not chain from previous runtime')
        for name, checksum in _hashes({**before['unchanged_history'], **before['provider_and_configuration']}).items():
            if not _file_matches(root, name, checksum):
                raise ValueError('Question tool prior evidence or provider changed: '+name)
        changes = _apply_overlay(_read(question/'authorized_source_changes.json'), expected, QUESTION_HOST_FILES, 'Question tool')
        if set(changes) != QUESTION_HOST_FILES:
            raise ValueError('Question tool overlay incomplete')
        question_runtime = _hashes(_read(question/'runtime_manifest.json')['sha256'])
        if set(question_runtime) != QUESTION_HOST_FILES|QUESTION_NEW_FILES:
            raise ValueError('Question tool runtime scope mismatch')
        for name, checksum in question_runtime.items():
            if name in expected and expected[name] != checksum:
                raise ValueError('Question tool runtime disagrees with authorized changes')
            expected[name] = checksum
        training = _hashes(_read(question/'training_manifest.json')['sha256'])
        if set(training) != QUESTION_TRAINING_FILES:
            raise ValueError('Question tool training scope mismatch')
        expected.update(training)
    branding = root/BRANDING_RECORD
    if (branding/'authorized_source_changes.json').exists():
        before = _read(branding/'before_snapshot.json')
        if before.get('version') != 'branding_before_v1' or set(before.get('files', {})) != BRANDING_FILES:
            raise ValueError('Branding before source scope mismatch')
        for name, checksum in _hashes(before['files']).items():
            if name in expected and expected[name] != checksum:
                raise ValueError('Branding source does not chain from previous runtime')
            expected[name] = checksum
        for name, checksum in _hashes(before['unchanged_history']).items():
            if not _file_matches(root, name, checksum):
                raise ValueError('Branding prior evidence changed: '+name)
        changes = _apply_overlay(_read(branding/'authorized_source_changes.json'), expected, BRANDING_FILES, 'Branding')
        if set(changes) != BRANDING_FILES:
            raise ValueError('Branding source overlay incomplete')
        current = _hashes(_read(branding/'runtime_manifest.json')['sha256'])
        if set(current) != BRANDING_FILES or any(expected[n] != h for n, h in current.items()):
            raise ValueError('Branding runtime disagrees with authorized changes')
    choices = root/CHOICES_RECORD
    if (choices/'authorized_source_changes.json').exists():
        before = _read(choices/'before_snapshot.json')
        if before.get('version') != 'context_choices_before_v1' or set(before.get('files',{})) != CHOICES_HOST_FILES:
            raise ValueError('Context choices before source scope mismatch')
        for name,checksum in _hashes(before['files']).items():
            if expected.get(name) != checksum:raise ValueError('Context choices do not chain from prior runtime')
        for name,checksum in _hashes(before['unchanged_history']).items():
            if not _file_matches(root,name,checksum):raise ValueError('Context choices prior evidence changed: '+name)
        changes = _apply_overlay(_read(choices/'authorized_source_changes.json'),expected,CHOICES_HOST_FILES,'Context choices')
        if set(changes) != CHOICES_HOST_FILES:raise ValueError('Context choices overlay incomplete')
        current = _hashes(_read(choices/'runtime_manifest.json')['sha256'])
        if set(current) != CHOICES_HOST_FILES|CHOICES_NEW_FILES:raise ValueError('Context choices runtime scope mismatch')
        for name,checksum in current.items():
            if name in expected and expected[name] != checksum:raise ValueError('Context choices runtime disagrees with authorized changes')
            expected[name] = checksum
        training = _hashes(_read(choices/'training_manifest.json')['sha256'])
        if set(training) != CHOICES_TRAINING_FILES:raise ValueError('Context choices training scope mismatch')
        expected.update(training)
    mainline = root/MAINLINE_RECORD
    if (mainline/'authorized_source_changes.json').exists():
        before = _read(mainline/'before_snapshot.json')
        if before.get('version') != 'mainline_before_v1' or before.get('prior_mismatches'):
            raise ValueError('Mainline requires a matching prior source snapshot')
        if _hashes(before['prior_effective_sha256']) != expected:
            raise ValueError('Mainline does not chain from prior effective sources')
        migration = {n: 'Training_Data/'+n.split('/',1)[1] for n in expected
                     if n.startswith('Training_Data_Darcy_CViT/')}
        if before.get('directory_migration') != migration:
            raise ValueError('Mainline directory migration exceeds the renamed training directory')
        for old, new in migration.items():
            if new in expected or (root/old).exists():
                raise ValueError('Mainline directory migration collides with an existing artifact')
            expected[new] = expected.pop(old)
        # Historical manifests and provider bytes remain frozen; only the final
        # path map changes. Never rewrite old task/weight hashes to hide a move.
        for name, checksum in _hashes(before['files']).items():
            if name.startswith('docs/integration/') or name in PROVIDER_FILES:
                if not _file_matches(root,name,checksum):
                    raise ValueError('Mainline prior evidence or provider changed: '+name)
        for name in MAINLINE_HOST_FILES:
            prior = before['files'].get(name)
            if prior is None or (name in expected and expected[name] != prior):
                raise ValueError('Mainline before source scope mismatch')
            expected[name] = prior
        changes = _apply_overlay(_read(mainline/'authorized_source_changes.json'), expected,
                                 MAINLINE_HOST_FILES, 'Mainline')
        if set(changes) != MAINLINE_HOST_FILES:
            raise ValueError('Mainline overlay incomplete')
        current = _hashes(_read(mainline/'runtime_manifest.json')['sha256'])
        if set(current) != MAINLINE_HOST_FILES|MAINLINE_NEW_FILES:
            raise ValueError('Mainline runtime scope mismatch')
        for name, checksum in current.items():
            if name in expected and expected[name] != checksum:
                raise ValueError('Mainline runtime disagrees with authorized changes')
            expected[name] = checksum
    history = root/SESSION_HISTORY_RECORD
    if (history/'authorized_source_changes.json').exists():
        before=_read(history/'before_snapshot.json')
        if before.get('version')!='session_history_before_v1' or _hashes(before['prior_effective_sha256'])!=expected:
            raise ValueError('Session history does not chain from prior runtime')
        for name,checksum in _hashes(before['files']).items():
            if name.startswith('docs/integration/') or name in PROVIDER_FILES:
                if not _file_matches(root,name,checksum):raise ValueError('Session history prior evidence/provider changed: '+name)
        for name in SESSION_HISTORY_HOST_FILES:
            prior=before['files'].get(name)
            if prior is None or name in expected and prior!=expected[name]:raise ValueError('Session history before source mismatch')
            expected[name]=prior
        changes=_apply_overlay(_read(history/'authorized_source_changes.json'),expected,SESSION_HISTORY_HOST_FILES,'Session history')
        if set(changes)!=SESSION_HISTORY_HOST_FILES:raise ValueError('Session history overlay incomplete')
        current=_hashes(_read(history/'runtime_manifest.json')['sha256'])
        if set(current)!=SESSION_HISTORY_HOST_FILES|SESSION_HISTORY_NEW_FILES:raise ValueError('Session history runtime scope mismatch')
        for name,checksum in current.items():
            if name in expected and expected[name]!=checksum:raise ValueError('Session history runtime disagrees with changes')
            expected[name]=checksum
    pdf=root/PDF_RECORD
    if (pdf/'authorized_source_changes.json').exists():
        before=_read(pdf/'before_snapshot.json')
        if before.get('version')!='pdf_reading_before_v1' or _hashes(before['prior_effective_sha256'])!=expected:
            raise ValueError('PDF reading does not chain from prior runtime')
        for name,checksum in _hashes(before['files']).items():
            if name.startswith('docs/integration/') or name in PROVIDER_FILES:
                if not _file_matches(root,name,checksum):raise ValueError('PDF reading prior evidence/provider changed: '+name)
        for name in PDF_HOST_FILES:
            if before['files'].get(name)!=expected.get(name):raise ValueError('PDF reading before source mismatch')
        changes=_apply_overlay(_read(pdf/'authorized_source_changes.json'),expected,PDF_HOST_FILES,'PDF reading')
        if set(changes)!=PDF_HOST_FILES:raise ValueError('PDF reading overlay incomplete')
        current=_hashes(_read(pdf/'runtime_manifest.json')['sha256'])
        if set(current)!=PDF_HOST_FILES|PDF_NEW_FILES:raise ValueError('PDF reading runtime scope mismatch')
        for name,checksum in current.items():
            if name in expected and expected[name]!=checksum:raise ValueError('PDF reading runtime disagrees with changes')
            expected[name]=checksum
    return expected, original, edits, runtime, planning_edits, planning_runtime


def effective_hashes(root=ROOT):
    """Read the final expected source hashes; auditors keep the old baselines intact."""
    return _expectations(root)[0]


def check_project(root=ROOT):
    root = Path(root).resolve()
    expected, original, edits, runtime, planning_edits, planning_runtime = _expectations(root)
    changed = [name for name, checksum in expected.items() if not _file_matches(root, name, checksum)]
    if changed: raise ValueError("Protected Harness/weight files changed: "+str(changed[:12]))
    return {"passed": True, "protected_files_checked": len(original),
            "authorized_host_changes": len(edits), "integration_runtime_files_checked": len(runtime),
            "planning_authorized_host_changes": len(planning_edits),
            "planning_runtime_files_checked": len(planning_runtime),
            "dynamic_runtime_files_checked": len(_read(root/DYNAMIC_RECORD/'runtime_manifest.json')['sha256'])
                if (root/DYNAMIC_RECORD/'authorized_source_changes.json').exists() else 0,
            "planning_history_privacy_files_checked": 1 if (root/PRIVACY_RECORD/'authorized_source_changes.json').exists() else 0,
            "interface_runtime_files_checked": len(INTERFACE_HOST_FILES|INTERFACE_NEW_FILES)
                if (root/INTERFACE_RECORD/'authorized_source_changes.json').exists() else 0,
            "question_tool_runtime_files_checked": len(QUESTION_HOST_FILES|QUESTION_NEW_FILES)
                if (root/QUESTION_RECORD/'authorized_source_changes.json').exists() else 0,
            "question_tool_training_files_checked": len(QUESTION_TRAINING_FILES)
                if (root/QUESTION_RECORD/'authorized_source_changes.json').exists() else 0,
            "branding_files_checked": len(BRANDING_FILES)
                if (root/BRANDING_RECORD/'authorized_source_changes.json').exists() else 0,
            "context_choices_runtime_files_checked": len(CHOICES_HOST_FILES|CHOICES_NEW_FILES)
                if (root/CHOICES_RECORD/'authorized_source_changes.json').exists() else 0,
            "context_choices_training_files_checked": len(CHOICES_TRAINING_FILES)
                if (root/CHOICES_RECORD/'authorized_source_changes.json').exists() else 0,
            "mainline_runtime_files_checked": len(MAINLINE_HOST_FILES|MAINLINE_NEW_FILES)
                if (root/MAINLINE_RECORD/'authorized_source_changes.json').exists() else 0,
            "session_history_runtime_files_checked": len(SESSION_HISTORY_HOST_FILES|SESSION_HISTORY_NEW_FILES)
                if (root/SESSION_HISTORY_RECORD/'authorized_source_changes.json').exists() else 0,
            "pdf_runtime_files_checked": len(PDF_HOST_FILES|PDF_NEW_FILES)
                if (root/PDF_RECORD/'authorized_source_changes.json').exists() else 0,
            "changed": []}


if __name__ == "__main__": print(json.dumps(check_project()))
