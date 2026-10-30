"""Registered boundary questions, guarded selection and actual answer/trace routes."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from rut_science.science_bot.general.registry import ToolRegistry
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.ledger import new_state, load, contract_hash
from rut_science.science_bot.general.planning.question_tool import execute, candidates, trace_rows
from rut_science.science_bot.general.planning.question_ranker import FEATURES, load_policy, features, score
from rut_science.science_bot.interface_demo import create_example, PILOT_ANSWER

ROOT = Path(__file__).resolve().parents[2]


class QuestionToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.session = create_example(Path(self.tmp.name))

    def enable(self, policy='rule'):
        result = self.session.message('/plan question '+policy)
        self.assertFalse(result.get('planning_error'), result)
        return result

    def test_registered_tool_closed_arguments_and_host_owned_state(self):
        registry = ToolRegistry()
        self.assertTrue(next(s for s in registry.specs() if s['name'] == 'question_tool')['read_only'])
        for args in ({'state': {}}, {'policy': 'unrestricted'}, {'max_questions': 3}, {'execute': True}):
            with self.assertRaises(ValueError):
                registry.execute('question_tool', args, {'planning_state': new_state()})
        with self.assertRaises(ValueError):
            registry.execute('question_tool', {}, {})

    def test_read_only_candidate_does_not_create_facts_or_authorize_execution(self):
        state = load(self.session)
        before = deepcopy(state)
        result = execute({'policy': 'trained'}, {'planning_state': state})
        self.assertEqual(state, before)
        self.assertEqual(result['plan_hash'], contract_hash(state))
        self.assertFalse(result['ledger_updated'])
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(len(result['questions']), 1)

    def test_conflicts_then_stale_are_constraints_even_for_trained_policy(self):
        state = load(self.session)
        state['conflicts']['resources'] = [state['facts']['resources'], deepcopy(state['facts']['resources'])]
        state['stale']['scope'] = '资源边界变化需要核对范围'
        result = execute({'policy': 'trained'}, {'planning_state': state})
        self.assertEqual(result['questions'][0]['field'], 'resources')
        self.assertEqual(result['questions'][0]['kind'], 'conflict')
        state['conflicts'].clear()
        self.assertEqual(execute({'policy': 'trained'}, {'planning_state': state})['questions'][0]['field'], 'scope')

    def test_unknown_with_acquisition_step_not_reasked_or_filled(self):
        state = load(self.session)
        state['evidence_actions'] = {'sampling': {'text': '查找先导记录', 'turn': 1, 'status': 'user_proposed_step_not_evidence'}}
        result = execute({}, {'planning_state': state})
        self.assertNotIn('sampling', [q['field'] for q in result['questions']])
        self.assertIn('sampling', state['unknown'])
        self.assertNotIn('sampling', state['facts'])

    def test_invalid_candidate_weights_fall_back_to_original_templates(self):
        with patch('rut_science.science_bot.general.planning.question_tool.load_policy', side_effect=ValueError('corrupt')):
            result = execute({'policy': 'trained'}, {'planning_state': load(self.session)})
        self.assertEqual(result['policy'], 'rule')
        self.assertEqual(result['reason'], 'candidate_unavailable_rule_fallback')

    def test_known_nonblocking_fields_never_become_candidates(self):
        state = load(self.session)
        rows, _ = candidates(state)
        self.assertNotIn('resources', [q['field'] for q in rows])
        self.assertNotIn('research_question', [q['field'] for q in rows])

    def test_actual_command_reuses_unanswered_question_and_preserves_contract(self):
        state = load(self.session)
        first = self.enable()
        count = self.session.resources()['tool_attempts']
        self.assertEqual(contract_hash(load(self.session)), contract_hash(state))
        self.assertEqual(first['question_tool']['policy'], 'rule')
        again = self.enable()
        self.assertEqual(first['questions'], again['questions'])
        self.assertTrue(again['question_tool']['reused_pending'])
        self.assertEqual(self.session.resources()['tool_attempts'], count)
        self.assertEqual(self.session.resources()['llm_requests'], 0)

    def test_answer_uses_original_intake_and_records_target_outcome(self):
        first = self.enable()
        target = first['questions'][0]['field']
        self.assertEqual(target, 'hypothesis')
        result = self.session.message('/plan accept hypothesis')
        self.assertFalse(result.get('planning_error'), result)
        rows = trace_rows(self.session, load(self.session))
        self.assertEqual(rows[0]['selected_fields'], [target])
        self.assertIn(target, rows[0]['outcome']['answered_target_fields'])
        self.assertNotEqual(rows[0]['outcome']['before_hash'], rows[0]['outcome']['after_hash'])
        self.assertFalse(rows[0]['ppo_eligible'])

    def test_repeated_tool_preserves_displayed_model_wording_without_another_request(self):
        def wording(session, state, text, assessment, fallback):
            q = deepcopy(fallback[0])
            q.update(question='已展示并校验的上下文问题', origin='model')
            return {'questions': [q], 'mode': 'dynamic', 'reason': 'validated', 'model_used': True}
        with patch('rut_science.science_bot.general.planning.runtime.propose_questions', side_effect=wording) as proposal:
            first = self.enable()
            second = self.enable()
        self.assertEqual(first['questions'], second['questions'])
        self.assertEqual(proposal.call_count, 1)

    def test_evidence_question_answer_retains_unknown_and_does_not_claim_result(self):
        self.session.message('/plan accept hypothesis')
        result = self.enable()
        self.assertEqual(result['questions'][0]['kind'], 'evidence_plan')
        self.session.message('先查找先导记录，再请导师核对适用范围。')
        state = load(self.session)
        self.assertIn('sampling', state['unknown'])
        self.assertNotIn('sampling', state['facts'])
        self.assertIn('sampling', state['evidence_actions'])
        self.assertFalse(state['approval'])
        self.assertEqual(trace_rows(self.session, state)[0]['outcome']['remaining_unknown'], ['sampling'])

    def test_trace_export_redacts_wording_and_requires_review(self):
        secret = '私有材料_SENTINEL_XYZ'
        self.session.message('/plan revise hypothesis: '+secret+'作为待检验命题')
        self.enable('trained')
        result = self.session.message('/plan question export')
        self.assertFalse(result.get('planning_error'), result)
        state = load(self.session)
        path = self.session.folder/'question_tool'/state['id']/'training_observations.jsonl'
        raw = path.read_text(encoding='utf-8')
        self.assertNotIn(secret, raw)
        for line in raw.splitlines():
            row = json.loads(line)
            self.assertEqual(row['supervision'], 'unreviewed_user_observation')
            self.assertFalse(row['ppo_eligible'])
            self.assertNotIn('question', row)

    def test_views_restore_and_off_do_not_rewrite_pending_option_mapping(self):
        first = self.enable('trained')
        for command in ('/plan map', '/plan review', '/plan question history', '/plan question export'):
            result = self.session.message(command)
            self.assertFalse(result.get('planning_error'), result)
            self.assertEqual(result['questions'][0], first['questions'][0])
        restored = GeneralSession.restore(self.session.folder)
        self.assertEqual(restored.meta['question_tool']['policy'], 'trained')
        result = restored.message('/plan question off')
        self.assertFalse(result.get('planning_error'), result)
        self.assertNotIn('question_tool', restored.meta)

    def test_budget_exhaustion_keeps_original_ledger_and_confirmation(self):
        before = load(self.session)
        self.session.meta['tool_attempts'] = self.session.limits['tool_calls']
        result = self.session.message('/plan question rule')
        self.assertTrue(result['planning_error'])
        self.assertEqual(load(self.session), before)

    def test_confirmed_plan_not_executed_and_revision_still_invalidates_approval(self):
        self.session.message('/plan accept hypothesis')
        self.session.message('/plan sampling: '+PILOT_ANSWER)
        identity = contract_hash(load(self.session))
        self.session.message('/plan approve '+identity)
        result = self.enable('trained')
        self.assertEqual(result['question_tool']['action'], 'review')
        self.assertTrue(result['planning']['approved'])
        self.assertFalse(result['execution_authorized'])
        self.session.message('/plan revise resources: 演示预算最多4次运行、1小时')
        self.assertFalse(load(self.session)['approval'])

    def test_trace_tampering_rejected_on_resume(self):
        self.enable()
        ref = self.session.meta['question_tool']['pending']['ref']
        (self.session.folder/ref).write_text('{}', encoding='utf-8')
        result = self.session.message('/plan question')
        self.assertTrue(result['planning_error'])
        self.assertIn('trace changed', result['answer'])

    def test_training_provenance_features_and_actual_candidate_match(self):
        folder = ROOT/'RUT_Science/research/question_tool_v1'
        dataset = json.loads((folder/'dataset.json').read_text(encoding='utf-8'))
        groups = {s: {r['source_group'] for r in dataset if r['split'] == s} for s in ('train', 'dev', 'test')}
        self.assertFalse(groups['train'] & groups['test'])
        self.assertFalse(groups['train'] & groups['dev'])
        self.assertFalse(groups['dev'] & groups['test'])
        self.assertFalse(any('case_id' in f or 'source_group' in f or 'preferred' in f for f in FEATURES))
        model = load_policy()
        self.assertFalse(model['default_enabled'])
        self.assertEqual(model['training_source'], 'scripted_synthetic_not_expert')
        for case in [r for r in dataset if r['split'] == 'test'][:8]:
            rows, _ = candidates(case['state'])
            best = max(rows, key=lambda q: score(features(case['state'], q), model['weights']))
            actual = execute({'policy': 'trained'}, {'planning_state': case['state']})
            self.assertEqual(actual['questions'][0]['field'], best['field'])


class QuestionToolHTTPTests(unittest.TestCase):
    def test_existing_http_message_route_supports_question_answer_and_export(self):
        from rut_science.science_bot.api import make_server
        with tempfile.TemporaryDirectory() as folder:
            server = make_server(Path(folder), port=0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            url = 'http://127.0.0.1:'+str(server.server_port)
            serial = 0
            def call(path, body):
                nonlocal serial
                serial += 1
                headers = {'Authorization': 'Bearer '+server.service.token, 'Content-Type': 'application/json',
                           'Idempotency-Key': 'question_http_'+str(serial)}
                with urlopen(Request(url+path, data=json.dumps(body).encode(), headers=headers), timeout=5) as response:
                    return json.load(response)
            try:
                created = call('/v1/sessions', {'backend': 'offline'})
                route = '/v1/sessions/'+created['id']+'/messages'
                call(route, {'text': '/plan start 我想比较两种模型，先澄清实验边界。'})
                result = call(route, {'text': '/plan question trained'})
                self.assertFalse(result.get('planning_error'), result)
                self.assertEqual(result['question_tool']['policy'], 'trained')
                field = result['questions'][0]['field']
                result = call(route, {'text': '/plan '+field+': 仅限本次合成先导研究'})
                self.assertFalse(result.get('planning_error'), result)
                result = call(route, {'text': '/plan question export'})
                self.assertIn('不含问题原文', result['answer'])
                self.assertFalse(result['execution_authorized'])
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
