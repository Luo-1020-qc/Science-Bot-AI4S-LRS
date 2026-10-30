"""Grounding and failure behavior of read-only dynamic clarification."""
from copy import deepcopy
from types import SimpleNamespace
import threading
import unittest

from rut_science.budget import RunLimitError
from rut_science.science_bot.general.planning.blueprint import review
from rut_science.science_bot.general.planning.clarification import propose, remember
from rut_science.science_bot.general.planning.ledger import new_state, contract_hash
from rut_science.science_bot.general.planning.runtime import _questions
from test_planning_intake import Provider


def question(field='scope', kind='missing', text='电池寿命比较要限定哪些温度与工况？',
             rationale='当前只提到电池寿命，明确适用条件后才能限制外推。', refs=None):
    return {'field': field, 'kind': kind, 'question': text, 'rationale': rationale,
            'references': refs or [{'source': 'answer', 'key': 'current', 'quote': '电池寿命'}]}


def response(*questions):
    return {'content': None, 'tool_calls': [{'name': 'propose_clarification_questions',
            'arguments': {'questions': list(questions)}}]}


class ClarificationTests(unittest.TestCase):
    def setUp(self):
        self.state = new_state()
        self.text = '我只想比较电池寿命，资源上限保持不变'
        self.provider = Provider(response(question()))
        self.session = SimpleNamespace(meta={'backend': 'api'}, provider=lambda: self.provider,
            pause_requested=threading.Event(), cancel_requested=threading.Event())

    def run_proposal(self):
        assessment = review(self.state)
        return propose(self.session, self.state, self.text, assessment, _questions(self.state, assessment))

    def test_contextual_question_native_call_is_read_only(self):
        before = deepcopy(self.state); identity = contract_hash(self.state)
        result = self.run_proposal()
        self.assertEqual(result['mode'], 'dynamic')
        self.assertEqual(self.state, before); self.assertEqual(contract_hash(self.state), identity)
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.provider.calls[0]['role'], 'planning_clarification')
        self.assertEqual(result['questions'][0]['origin'], 'model')
        self.assertEqual(self.provider.validations[-1][0], 'accepted')

    def test_answered_field_cannot_be_reasked(self):
        self.state['facts']['scope'] = {'value': '只比较电池寿命', 'quote': '只比较电池寿命', 'status': 'declared', 'turn': 1}
        self.assertEqual(self.run_proposal()['mode'], 'template')

    def test_malformed_ungrounded_numeric_and_authority_proposals_fall_back(self):
        examples = []
        q = question(); q['references'][0]['quote'] = '不存在的论文结果'; examples.append(q)
        q = question(text='电池寿命需要64个样本才能保证功效吗？'); examples.append(q)
        q = question(text='电池寿命已授权执行，请自动启动训练好吗？'); examples.append(q)
        q = question(); q['execute'] = True; examples.append(q)
        q = question(); q['references'][0]['source'] = 'evidence'; examples.append(q)
        for item in examples:
            with self.subTest(item=item):
                self.provider.response = response(item)
                result = self.run_proposal()
                self.assertEqual(result['mode'], 'template')
                self.assertTrue(result['questions'])
                self.assertEqual(self.provider.validations[-1][0], 'rejected')

    def test_duplicate_and_more_than_two_questions_rejected(self):
        self.provider.response = response(question(), question())
        result = self.run_proposal()
        self.assertEqual(result['mode'], 'dynamic'); self.assertEqual(len(result['questions']), 1)
        self.provider.response = response(question(), question(), question())
        self.assertEqual(self.run_proposal()['mode'], 'template')

    def test_repeated_wording_rejected_without_changing_contract(self):
        identity = contract_hash(self.state)
        remember(self.state, self.run_proposal()['questions'], 1)
        self.assertEqual(contract_hash(self.state), identity)
        self.assertEqual(self.run_proposal()['mode'], 'template')

    def test_unknown_becomes_evidence_acquisition_not_a_value_request(self):
        self.state['unknown'] = ['sampling']
        self.text = '电池寿命重复数还不知道'
        self.provider.response = response(question('sampling', 'evidence_plan',
            '能先查找电池寿命先导记录，作为重复依据的来源吗？',
            refs=[{'source': 'answer', 'key': 'current', 'quote': '电池寿命'},
                  {'source': 'unknown', 'key': 'sampling', 'quote': '样本与重复依据：明确未知'}]))
        self.assertEqual(self.run_proposal()['mode'], 'dynamic')
        self.assertIn('sampling', self.state['unknown']); self.assertNotIn('sampling', self.state['facts'])
        self.provider.response['tool_calls'][0]['arguments']['questions'][0]['kind'] = 'missing'
        self.assertEqual(self.run_proposal()['questions'][0]['kind'], 'evidence_plan')
        self.provider.response['tool_calls'][0]['arguments']['questions'][0].update(
            kind='evidence_plan', question='电池寿命到底需要多少重复？现在能给出确定答案吗？')
        self.assertEqual(self.run_proposal()['mode'], 'template')

    def test_host_classifies_and_supplies_state_reference_without_mutation(self):
        self.state['unknown'] = ['sampling']
        self.text = '电池寿命方差还不知道'
        self.provider.response = response(question('sampling', 'missing',
            '能先查找电池寿命的先导记录再决定重复依据吗？'))
        result = self.run_proposal(); self.assertEqual(result['mode'], 'dynamic')
        q = result['questions'][0]
        self.assertEqual(q['kind'], 'evidence_plan')
        self.assertTrue(any(r.get('host_context') for r in q['references']))
        self.assertNotIn('sampling', self.state['facts'])

    def test_one_invalid_question_does_not_discard_another_valid_one(self):
        bad = question('analysis', text='电池寿命需要64次重复，是否直接执行？')
        self.provider.response = response(question(), bad)
        result = self.run_proposal()
        self.assertEqual(result['mode'], 'dynamic'); self.assertEqual(len(result['questions']), 1)
        self.assertEqual(result['reason'], 'validated_partial')

    def test_conflict_prioritized_and_options_are_host_owned(self):
        rows = [{'value': v, 'quote': v, 'status': 'declared', 'turn': 1} for v in ('最多4小时', '最多8小时')]
        self.state['facts']['resources'] = rows[0]; self.state['conflicts']['resources'] = rows
        self.assertEqual(self.run_proposal()['mode'], 'template')
        self.provider.response = response(question('resources', 'conflict',
            '电池寿命实验的最多4小时与最多8小时，哪个是当前上限？',
            '两个资源声明冲突，先核实上限才能继续规划。',
            [{'source': 'conflict', 'key': 'resources:0', 'quote': '最多4小时'},
             {'source': 'conflict', 'key': 'resources:1', 'quote': '最多8小时'}]))
        result = self.run_proposal()
        self.assertEqual(result['mode'], 'dynamic')
        self.assertEqual([o['value'] for o in result['questions'][0]['options']], ['最多4小时', '最多8小时'])
        self.assertIsNone(self.state['approval'])

    def test_proposal_confirmation_must_display_actual_proposal(self):
        self.state['facts']['scope'] = {'value': '只比较电池寿命', 'quote': self.text, 'status': 'proposed', 'turn': 1}
        self.provider.response = response(question(kind='proposal'))
        self.assertEqual(self.run_proposal()['mode'], 'template')
        self.provider.response = response(question(kind='proposal', text='我理解为“只比较电池寿命”，是否准确？'))
        self.assertEqual(self.run_proposal()['mode'], 'dynamic')
        self.assertEqual(self.state['facts']['scope']['status'], 'proposed')

    def test_budget_transport_offline_and_cancel_keep_template_and_state(self):
        before = deepcopy(self.state)
        for error in (RunLimitError('budget'), OSError('transport')):
            self.provider.error = error
            self.assertEqual(self.run_proposal()['mode'], 'template')
        self.provider.error = None; self.session.meta['backend'] = 'offline'
        count = len(self.provider.calls)
        self.assertEqual(self.run_proposal()['reason'], 'offline'); self.assertEqual(len(self.provider.calls), count)
        self.session.meta['backend'] = 'api'; self.session.cancel_requested.set()
        self.assertEqual(self.run_proposal()['reason'], 'interrupted')
        self.assertEqual(self.state, before)


if __name__ == '__main__': unittest.main()
