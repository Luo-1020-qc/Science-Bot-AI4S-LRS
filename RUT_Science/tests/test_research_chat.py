import copy
import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rut_science.intake_contract import (apply_extraction, build_catalog, build_draft, evidence_matches,
                                        make_receipt, offline_extract, validate_receipt)
from rut_science.research_chat import ResearchChat
from rut_science.research_spec import ResearchSpec
from rut_science.util import write_json


@unittest.skipUnless(importlib.util.find_spec('langgraph'), 'Optional planning dependencies required')
class ResearchChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.chat = ResearchChat.create(self.root/'chat', backend='offline', progress=lambda _: None)

    def tearDown(self):
        self.temp.cleanup()

    def complete_draft(self):
        self.chat.submit('Materials-A predict conductivity with linear, seed 11')
        self.assertIsNotNone(self.chat.state['draft'])

    def test_missing_target_clarifies_without_execution(self):
        self.chat.submit('Materials-A')
        self.assertIsNone(self.chat.state['draft'])
        self.assertTrue(self.chat.state['issues'])
        self.chat.submit('/confirm')
        self.assertFalse(list(self.chat.output.glob('execution_*')))

    def test_default_provenance_is_distinct_from_user(self):
        self.complete_draft()
        p = self.chat.state['draft']['provenance']
        self.assertEqual(p['model']['origin'], 'user')
        self.assertEqual(p['train_fraction']['origin'], 'system_default')
        self.assertEqual(p['max_train_calls']['origin'], 'method_contract')

    def test_confirmation_and_idempotent_execution(self):
        self.complete_draft()
        self.chat.submit('/confirm', actor='scripted_operator')
        self.assertEqual(self.chat.state['executions'][0]['phase'], 'complete')
        self.chat.submit('/confirm', actor='scripted_operator')
        self.assertEqual(len(self.chat.state['executions']), 1)
        state = json.loads((self.chat.output/'execution_001'/'checkpoint.json').read_text())['state']
        self.assertEqual(state['tool_calls'], 6)
        receipt = self.chat.state['confirmation']
        self.assertEqual(receipt['actor'], 'scripted_operator')
        self.assertEqual(state['environment_state']['research_spec']['confirmation']['reference'], 'intake:'+receipt['confirmation_hash'])
        from rut_science.chat_verification import verify_chat
        self.assertEqual(verify_chat(self.chat.output)['status'], 'passed')

    def test_edit_invalidates_confirmation_and_old_hash_is_refused(self):
        self.complete_draft()
        old = self.chat.state['draft']['draft_hash']
        self.chat.submit('/confirm', execute=False)
        self.chat.submit('seed 42')
        self.assertIsNone(self.chat.state['confirmation'])
        self.chat.submit('/confirm '+old, execute=False)
        self.assertIsNone(self.chat.state['confirmation'])
        self.assertEqual(self.chat.state['draft']['spec']['split_seed'], 42)
        self.assertTrue(list((self.chat.output/'confirmations').glob('*.json')))

    def test_unsupported_dataset_and_wrong_target_refuse_execution(self):
        self.chat.submit('unknown dataset')
        self.assertIsNone(self.chat.state['draft'])
        self.chat.submit('Materials-A predict modulus')
        self.assertIsNone(self.chat.state['draft'])
        with self.assertRaises(ValueError):
            self.chat.execute()

    def test_conflicting_training_constraint_requires_resolution(self):
        self.chat.submit('Materials-A conductivity, no training')
        self.assertIsNone(self.chat.state['draft'])
        self.chat.submit('allow training')
        self.assertIsNotNone(self.chat.state['draft'])

    def test_ambiguous_dataset_does_not_become_model_choice(self):
        self.chat.submit('Materials-A conductivity')
        self.chat.submit('Materials-A or Materials-B?')
        self.assertIsNone(self.chat.state['draft'])

    def test_conflicting_numbers_block_until_unambiguous_correction(self):
        self.complete_draft()
        self.chat.submit('seed 11 or seed 12')
        self.assertIsNone(self.chat.state['draft'])
        self.chat.submit('seed 12')
        self.assertEqual(self.chat.state['draft']['spec']['split_seed'], 12)

    def test_ungrounded_required_target_cannot_be_used_as_default(self):
        fields = apply_extraction({}, {'fields': {'dataset_name': {'value': 'Materials-A', 'evidence': 'Materials-A'},
            'target': {'value': 'conductivity', 'evidence': ''}}, 'questions': [], 'conflicts': []}, 'Materials-A', 0)
        draft, issues = build_draft(fields, {}, build_catalog(), 1, {})
        self.assertIsNone(draft)
        self.assertTrue(issues)

    def test_model_cannot_confirm_itself_or_spoof_user_provenance(self):
        text = 'Materials-A'
        with self.assertRaises(ValueError):
            apply_extraction({}, {'fields': {}, 'questions': [], 'conflicts': [], 'confirmed': True}, text, 0)
        fields = apply_extraction({}, {'fields': {'split_seed': {'value': 42, 'evidence': 'Materials-A'}},
                                      'questions': [], 'conflicts': []}, text, 0)
        self.assertEqual(fields['split_seed']['origin'], 'model_suggestion')
        self.assertFalse(evidence_matches('model', 'linear', '不要linear', '不要linear'))

    def test_suggestion_cannot_override_explicit_value(self):
        current = apply_extraction({}, offline_extract('seed 11'), 'seed 11', 0)
        updated = apply_extraction(current, {'fields': {'split_seed': {'value': 99, 'evidence': ''}},
                                            'questions': [], 'conflicts': []}, 'keep it', 1)
        self.assertEqual(updated['split_seed']['value'], 11)

    def test_resume_preserves_draft_receipt_and_pause_boundary(self):
        self.complete_draft()
        self.chat.submit('/confirm', stop_after=3)
        restored = ResearchChat.restore(self.chat.output, progress=lambda _: None)
        self.assertEqual(restored.state['confirmation'], self.chat.state['confirmation'])
        restored.submit('/resume')
        final = json.loads((restored.output/'execution_001'/'checkpoint.json').read_text())['state']
        self.assertEqual(final['tool_calls'], 6)
        self.assertEqual(restored.state['executions'][0]['phase'], 'complete')

    def test_prepare_only_disables_run_command(self):
        self.complete_draft()
        self.chat.submit('/confirm', execute=False)
        self.chat.submit('/run', execute=False)
        self.assertFalse(self.chat.state['executions'])

    def test_receipt_hash_and_execution_policy_tampering_refused(self):
        self.complete_draft()
        self.chat.submit('/confirm', execute=False)
        receipt = copy.deepcopy(self.chat.state['confirmation'])
        receipt['draft']['execution_policy']['recovery_policy']['enabled'] = True
        with self.assertRaises(ValueError):
            validate_receipt(receipt, ResearchSpec(**self.chat.state['draft']['spec']))
        self.chat.state['policy']['max_tool_calls'] = 10
        with self.assertRaisesRegex(ValueError, 'confirmed intake policy'):
            self.chat.execute()

    def test_api_intake_and_planner_share_persistent_request_quota(self):
        config = self.root/'API_key_Agent.json'
        write_json(config, {'API': 'fake_local_test_key', 'base_url': 'https://example.invalid/v1'})
        chat = ResearchChat.create(self.root/'api_chat', backend='api', api_config=config, max_requests=1,
                                   progress=lambda _: None)
        extraction = offline_extract('Materials-A conductivity')
        class Reply:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return json.dumps({'model': 'mock', 'choices': [{'message': {'content': json.dumps(extraction)}}],
                                   'usage': {'prompt_tokens': 100, 'completion_tokens': 50}}).encode()
        with patch('urllib.request.urlopen', return_value=Reply()) as network:
            chat.submit('Materials-A conductivity')
            chat.submit('/confirm', actor='scripted_operator')
            self.assertEqual(network.call_count, 1)
        self.assertEqual(chat.state['executions'][0]['phase'], 'limit_reached')
        restored = ResearchChat.restore(chat.output, progress=lambda _: None)
        self.assertEqual(len(restored.budget.calls), 1)
        self.assertEqual(restored.budget.snapshot()['accounted_tokens'], 150)
        self.assertNotIn('fake_local_test_key', (chat.output/'model_calls.json').read_text())
