"""Explicit file/range selection, snapshot provenance and safe plan integration."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.blueprint import review, export_markdown
from rut_science.science_bot.general.planning.clarification import context
from rut_science.science_bot.general.planning.evidence import select, validate_sources
from rut_science.science_bot.general.planning.ledger import load, contract_hash, new_state, validate, save
from rut_science.science_bot.general.planning.understanding import review_reflection
from test_planning_clarification import response, question
from test_planning_intake import Provider

ROOT = Path(__file__).resolve().parents[2]


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT/'.local'); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.paper = self.root/'paper.md'
        self.paper.write_text('# 合成论文\n仅在恒温条件比较电池寿命。\n没有核实温度变化下的效果。\n', encoding='utf-8')
        self.session = GeneralSession.create(self.root/'sessions', backend='offline', workspace=self.root)

    def send(self, text):
        result = self.session.message(text)
        self.assertFalse(result.get('planning_error'), result)
        return result

    def add(self, **kwargs):
        arguments = dict(path='paper.md', start_line=2, end_line=3, **kwargs)
        return self.send('/plan evidence add '+json.dumps(arguments, ensure_ascii=False))

    def test_select_requires_workspace_explicit_path_range_and_text_policy(self):
        args = dict(path='paper.md', start_line=2, end_line=3)
        self.session.workspace = None
        with self.assertRaises(ValueError): select(self.session, args, 1)
        self.session.workspace = GeneralSession.restore(self.session.folder).workspace
        outside = self.root.parent/'outside.md'
        for bad in [dict(args, path=str(outside)), dict(args, path='../outside.md'),
                    dict(args, path='paper.pdf'), dict(args, start_line=0), dict(args, end_line=122),
                    dict(args, share_with_model='yes'), dict(args, execute=True)]:
            with self.subTest(bad=bad), self.assertRaises(ValueError): select(self.session, bad, 1)
        (self.root/'.env.md').write_text('sensitive', encoding='utf-8')
        with self.assertRaises(ValueError): select(self.session, dict(args, path='.env.md'), 1)

    def test_selected_snapshot_citations_local_default_and_immutable_restore(self):
        self.add(); state = load(self.session); row = state['evidence'][0]
        self.assertFalse(row['share_with_model']); self.assertEqual(row['start_line'], 2)
        self.assertNotIn('# 合成论文', row['text'])
        self.assertNotIn('evidence', {r['source'] for r in context(state, '', review(state))['sources']})
        identity = contract_hash(state)
        self.paper.write_text('changed externally', encoding='utf-8')
        restored = GeneralSession.restore(self.session.folder)
        self.assertEqual(contract_hash(load(restored)), identity)
        shown = restored.message('/plan evidence show '+row['id'])['answer']
        self.assertIn('2: 仅在恒温条件', shown); self.assertNotIn('changed externally', shown)
        markdown = export_markdown(state)
        self.assertIn(row['sha256'], markdown); self.assertIn(row['text'].splitlines()[0], markdown)

    def test_share_with_model_is_explicit_and_only_selected_lines_enter_context(self):
        self.add(share_with_model=True); state = load(self.session)
        shared = [r for r in context(state, '', review(state))['sources'] if r['source'] == 'evidence']
        self.assertEqual(len(shared), 1); self.assertNotIn('# 合成论文', shared[0]['text'])
        self.assertIn(':L2-L3#', shared[0]['citation'])
        row = state['evidence'][0]
        provider = Provider(response(question(text='电池寿命只在恒温条件下比较，先复现哪个适用范围？',
            refs=[{'source': 'evidence', 'key': row['id'], 'quote': '恒温条件比较电池寿命'}])))
        self.session.meta['backend'] = 'api'; self.session._provider = provider
        result = self.send('/plan resume')
        self.assertEqual(result['clarification']['mode'], 'dynamic')
        self.assertIn(row['sha256'], result['questions'][0]['references'][0]['citation'])
        self.assertEqual(self.session.meta['tool_attempts'], 0)

    def test_adding_shared_evidence_displays_the_new_question_in_terminal_answer(self):
        # Evidence selection must not hide questions behind a fixed success answer;
        # the original terminal deliberately prefers the complete answer string.
        from rut_science.science_bot.general.planning.evidence import source_id
        row = select(self.session, dict(path='paper.md', start_line=2, end_line=3), 1)
        q = question(text='电池寿命只在恒温条件下比较，本轮要限定哪些工况？',
            refs=[{'source': 'evidence', 'key': source_id(row), 'quote': '电池寿命'}])
        self.session.meta['backend'] = 'api'; self.session._provider = Provider(response(q))
        out = self.add(share_with_model=True)
        self.assertEqual(out['clarification']['mode'], 'dynamic')
        self.assertIn(q['question'], out['answer'])
        self.assertNotIn('依据：',out['answer'])
        self.assertNotIn(row['sha256'],out['answer'])
        self.assertIn(row['sha256'],out['questions'][0]['references'][0]['citation'])

    def test_selection_invalidation_keeps_facts_and_prior_snapshots(self):
        self.send('/plan scope: 只研究恒温条件下的电池寿命')
        state = load(self.session); state['approval'] = {'contract_hash': contract_hash(state), 'scope': 'planning_contract_only'}
        save(self.session, state); before_ref = self.session.meta['planning_ref']; previous = (self.session.folder/before_ref).read_bytes()
        self.add(); state = load(self.session)
        self.assertIsNone(state['approval']); self.assertIn('scope', state['stale'])
        self.assertEqual(state['facts']['scope']['value'], '只研究恒温条件下的电池寿命')
        self.assertEqual((self.session.folder/before_ref).read_bytes(), previous)
        self.assertFalse(self.session.status()['confirmed'])
        identity = contract_hash(state)
        self.send('/plan evidence remove '+state['evidence'][0]['id'])
        self.assertNotEqual(contract_hash(load(self.session)), identity)

    def test_changed_file_refresh_is_explicit_and_tamper_rejected(self):
        self.add(); old = load(self.session)['evidence'][0]
        self.paper.write_text('# 新版本\n仅在低温条件比较电池寿命。\n原结论不适用。\n', encoding='utf-8')
        self.add(); rows = load(self.session)['evidence']
        self.assertEqual(len(rows), 1); self.assertNotEqual(rows[0]['sha256'], old['sha256'])
        tampered = deepcopy(rows); tampered[0]['text'] = 'forged'
        with self.assertRaises(ValueError): validate_sources(tampered)

    def test_oversize_and_empty_selection_are_atomic(self):
        self.send('/plan scope: 只研究恒温条件下的电池寿命'); before = load(self.session)
        self.paper.write_text('x'*6001, encoding='utf-8')
        result = self.session.message('/plan evidence add {"path":"paper.md","start_line":1,"end_line":1}')
        self.assertTrue(result['planning_error']); self.assertEqual(load(self.session), before)
        self.paper.write_text('\n\n', encoding='utf-8')
        with self.assertRaises(ValueError): select(self.session, dict(path='paper.md', start_line=1, end_line=2), 1)

    def test_unknown_step_is_not_promoted_to_known_parameter(self):
        out = self.send('/plan sampling: 未知')
        self.assertEqual(out['questions'][0]['kind'], 'evidence_plan')
        self.send('先查找先导记录并请导师核实重复依据')
        state = load(self.session)
        self.assertIn('sampling', state['unknown']); self.assertNotIn('sampling', state['facts'])
        self.assertIn('sampling', state['evidence_actions'])
        self.assertTrue(any(r['code'] == 'explicit_unknown' for r in review(state)['blockers']))
        self.send('/plan sampling: 先做固定预算的先导，不保证功效')
        self.assertNotIn('sampling', load(self.session)['evidence_actions'])

    def test_old_v1_hash_and_new_question_history_compatible(self):
        state = new_state(); identity = contract_hash(state)
        self.assertEqual(validate(state), state)
        state.update(evidence=[], question_history=[], clarification={'mode': 'template'}, evidence_actions={})
        self.assertEqual(contract_hash(state), identity); validate(state)

    def test_read_only_map_keeps_dynamic_pending_and_does_not_call_api(self):
        self.add(share_with_model=True); row = load(self.session)['evidence'][0]
        provider = Provider(response(question(refs=[{'source': 'evidence', 'key': row['id'], 'quote': '电池寿命'}])))
        self.session.meta['backend'] = 'api'; self.session._provider = provider
        self.send('/plan resume'); pending = deepcopy(load(self.session)['pending'])
        count = len(provider.calls)
        self.send('/plan map'); self.send('/plan understanding'); self.send('/plan evidence list')
        self.send('/plan evidence show '+row['id']); self.send('什么是实验单位？')
        self.assertEqual(load(self.session)['pending'], pending); self.assertEqual(len(provider.calls), count)

    def test_formative_reflection_never_scores_correctness_or_understanding(self):
        result = review_reflection(new_state(), '我认为有混杂但已经证明因果；我会复核并停止。')
        self.assertFalse(result['human_understanding_measured']); self.assertFalse(result['correctness_scored'])
        self.assertTrue(result['discussion_flags'])
        out = self.send('/plan reflect 我的理解是先核实实验单位，未知条件要查证，不能因模拟成功而声称实测成功。')
        self.assertFalse(out['understanding']['human_understanding_measured'])

    def test_cancelling_dynamic_question_does_not_save_prior_local_updates(self):
        self.send('/plan scope: 只研究恒温条件下的电池寿命')
        before = load(self.session)
        provider = Provider(response(question()))
        provider.on_complete = self.session.cancel_requested.set
        self.session.meta['backend'] = 'api'; self.session._provider = provider
        result = self.session.message('/plan outcomes: 每个电池的寿命均值，越高越好')
        self.assertTrue(result['planning_error']); self.assertEqual(load(self.session), before)
        self.assertEqual(self.session.meta['phase'], 'cancelled')

    def test_selected_excerpt_respects_lower_session_read_budget(self):
        self.session.limits['read_bytes'] = 10
        with self.assertRaises(ValueError):
            select(self.session, dict(path='paper.md', start_line=2, end_line=3), 1)

    def test_local_paper_display_is_not_replayed_to_general_chat_after_restore(self):
        self.paper.write_text('PRIVATE_SYNTHETIC_PAPER_PHRASE\n', encoding='utf-8')
        out = self.send('/plan evidence add {"path":"paper.md","start_line":1,"end_line":1}')
        row = load(self.session)['evidence'][0]
        shown = self.send('/plan evidence show '+row['id'])
        self.assertIn('PRIVATE_SYNTHETIC_PAPER_PHRASE', shown['answer'])
        self.assertNotIn('PRIVATE_SYNTHETIC_PAPER_PHRASE', json.dumps(self.session.meta['messages']))
        restored = GeneralSession.restore(self.session.folder)
        restored.meta['backend'] = 'api'
        provider = Provider({'content': '普通聊天回答', 'tool_calls': []})
        restored._provider = provider
        result = restored.message('换个话题，说明什么是科学方法')
        self.assertEqual(result['intent'], 'chat')
        self.assertNotIn('PRIVATE_SYNTHETIC_PAPER_PHRASE', json.dumps(provider.calls))
        self.assertIn('PRIVATE_SYNTHETIC_PAPER_PHRASE', shown['answer'])


if __name__ == '__main__': unittest.main()
