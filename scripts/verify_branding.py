"""Local branding integrity and focused presentation/HTTP regression; no browser automation."""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import re
import sys
import time
import unittest

from integrity import ROOT, BRANDING_RECORD, BRANDING_FILES, sha, check_project

sys.path.insert(0, str(ROOT/'RUT_Science'))
sys.dont_write_bytecode = True
RECORD = ROOT/BRANDING_RECORD
ASSETS = ROOT/'RUT_Science/rut_science/science_bot/workbench_assets/dist'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def finalize():
    before = read(RECORD/'before_snapshot.json')
    for name, checksum in before['unchanged_history'].items():
        if sha(ROOT/name) != checksum:
            raise ValueError('Prior evidence modified: '+name)
    changes = {name: {'before_sha256': before['files'][name], 'sha256': sha(ROOT/name),
        'reason': 'User requested a CityU-inspired red theme, OpenCode-style original wordmark and robot icon; presentation only'}
        for name in sorted(BRANDING_FILES)}
    for name, value in {'authorized_source_changes.json': {'files': changes},
                        'runtime_manifest.json': {'sha256': {n: sha(ROOT/n) for n in sorted(BRANDING_FILES)}}}.items():
        (RECORD/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    check_project()


def inputs(*, full=False):
    paths = [ROOT/n for n in BRANDING_FILES]
    paths += (list((ROOT/'RUT_Science/tests').rglob('test*.py')) if full else
              [ROOT/'RUT_Science/tests'/n for n in ('test_interface_delivery.py', 'test_workbench_http.py')])
    paths += [ROOT/'scripts'/n for n in ('test_integrity.py', 'integrity.py', 'verify_branding.py', 'verify_question_tool.py')]
    paths += [RECORD/'runtime_manifest.json', RECORD/'authorized_source_changes.json']
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def run_checks(*, full=False):
    before = inputs(full=full)
    groups = {}
    suites = [('test*.py', 'RUT_Science/tests')] if full else [
        ('test_interface_delivery.py', 'RUT_Science/tests'), ('test_workbench_http.py', 'RUT_Science/tests')]
    for pattern, folder in suites+[('test_integrity.py', 'scripts')]:
        started = time.monotonic()
        result = unittest.TextTestRunner(verbosity=1).run(unittest.TestLoader().discover(str(ROOT/folder), pattern=pattern))
        groups[pattern] = {'run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                           'skipped': len(result.skipped), 'passed': result.wasSuccessful(),
                           'seconds': round(time.monotonic()-started, 3)}
    if inputs(full=full) != before:
        raise ValueError('Presentation or checks changed during verification')
    value = {'passed': all(g['passed'] for g in groups.values()), 'groups': groups,
        'source_sha256': before, 'checked_utc': datetime.now(timezone.utc).isoformat(),
        'full_application_regression': full,
        'scope': 'full_application_and_integrity' if full else 'focused_presentation_http_and_integrity_not_a_new_full_application_regression'}
    (RECORD/'checks.json').write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    if not value['passed']:
        raise ValueError('Branding checks failed')


def contrast(foreground, background):
    def lum(color):
        c = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
        c = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in c]
        return sum(v*w for v, w in zip(c, (.2126, .7152, .0722)))
    values = sorted([lum(foreground), lum(background)])
    return (values[1]+.05)/(values[0]+.05)


def asset_checks():
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(); self.ids = []
        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key == 'id': self.ids.append(value)
    html = (ASSETS/'index.html').read_text(encoding='utf-8')
    css = (ASSETS/'styles.css').read_text(encoding='utf-8')
    js = (ASSETS/'app.js').read_text(encoding='utf-8')
    parsed = Parser(); parsed.feed(html)
    refs = set(re.findall(r'\$\("([^"]+)"\)', js))
    if len(parsed.ids) != len(set(parsed.ids)) or refs-set(parsed.ids):
        raise ValueError('Duplicate or missing JavaScript element binding')
    tokens = dict(re.findall(r'--([a-z-]+):\s*(#[a-fA-F0-9]{6})', css))
    pairs = [('primary_button', '#ffffff', tokens['accent']),
             ('body', tokens['ink'], tokens['paper']), ('muted', tokens['muted'], tokens['white']),
             ('secondary_text', tokens['quiet'], tokens['paper']),
             ('sidebar_text', tokens['muted'], tokens['sidebar']),
             ('selected_navigation', tokens['accent-dark'], '#efd9e2')]
    ratios = {name: round(contrast(fg, bg), 3) for name, fg, bg in pairs}
    if min(ratios.values()) < 4.5:
        raise ValueError('Normal-text contrast below 4.5:1: '+str(ratios))
    if 'var(--green' in css or '#285b43' in css or 'class="brand-wordmark"' not in html:
        raise ValueError('Red theme or pixel wordmark missing')
    return {'javascript_bindings_checked': len(refs), 'text_contrast_ratios': ratios,
            'minimum_checked_text_contrast': min(ratios.values())}


def main():
    if (ROOT/'docs/integration/context_choices_2026-10-29/authorized_source_changes.json').exists():
        from verify_context_choices import main as verify_current_choices
        return verify_current_choices()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finalize', action='store_true')
    parser.add_argument('--run-checks', action='store_true')
    parser.add_argument('--run-tests', action='store_true', help='Run full application and integrity regression')
    args = parser.parse_args()
    if args.finalize: finalize()
    protected = check_project()
    if args.run_checks or args.run_tests: run_checks(full=args.run_tests)
    checks = read(RECORD/'checks.json')
    if not checks['passed'] or checks['source_sha256'] != inputs(full=checks.get('full_application_regression', False)):
        raise ValueError('Focused checks stale; run --run-checks')
    from verify_interfaces import check_examples
    full = checks.get('full_application_regression', False)
    regression = ({'record': BRANDING_RECORD+'/checks.json', 'run': checks['groups']['test*.py']['run'],
        'skipped': checks['groups']['test*.py']['skipped'], 'rerun_for_branding': True} if full else
        {'record': 'docs/integration/question_tool_2026-10-29/full_tests.json',
         'run': 444, 'skipped': 2, 'rerun_for_branding': False})
    result = {'passed': True, 'integrity': protected, 'checks': checks['groups'],
        'assets': asset_checks(), 'example_sha256': check_examples(),
        'last_full_application_regression': regression,
        'browser_visual_qa': False,
        'browser_visual_qa_reason': 'Computer Use could not reliably identify the current Windows browser URL and stopped; no other browser automation was attempted.',
        'model_requests': 0, 'real_scientific_executions': 0, 'committed_or_pushed': False}
    (RECORD/'verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__': main()
