import copy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rut_science.benchmark import build_tasks
from rut_science.environment import ScientificMLEnvironment
from rut_science.planning_agent import PlanningSession
from rut_science.planning_evaluation import verify_artifacts
from rut_science.plan_spec import PlanSpec, PlanValidationError, public_control_plan, resolve_node
from rut_science.recovery import RecoveryPolicy, recovery_checks
from rut_science.research_spec import ResearchSpec


@unittest.skipUnless(importlib.util.find_spec('langgraph'), 'Optional planning dependencies required')
class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name)
        env = ScientificMLEnvironment()
        spec = ResearchSpec.from_task(build_tasks()[0], env.snapshot())
        self.session = PlanningSession.create(self.output, env, spec, workflow='synthetic', task_id='science_001',
            recovery_policy=RecoveryPolicy(enabled=True).to_dict(),
            fault_injection={'tool': 'train_model', 'count': 1, 'error_code': 'transient_unavailable'})

    def tearDown(self):
        self.temp.cleanup()

    def test_atomic_failure_retries_with_versions_and_separate_strict_score(self):
        status = self.session.run()
        self.assertTrue(status['execution_success'])
        score = self.session.state['score']
        self.assertFalse(score['strict_execution_success'])
        self.assertTrue(score['recovery_success'])
        self.assertEqual(status['tool_calls'], 7)
        self.assertEqual(status['plan_version'], 2)
        errors = [e for e in self.session.state['events'] if e['event_type'] == 'tool_call' and e['tool_result']['status'] == 'error']
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0]['fault_injected'])
        self.assertEqual(errors[0]['state_before'], errors[0]['state_after'])
        self.assertEqual(verify_artifacts(self.output)['status'], 'passed')

    def test_exhaustion_stops_without_infinite_replanning(self):
        self.session.state['faults_remaining'] = 2
        self.assertEqual(self.session.run()['phase'], 'execution_failed')
        self.assertEqual(self.session.state['recovery_count'], 1)
        self.assertEqual(self.session.state['tool_calls'], 5)
        self.assertFalse(self.session.env.snapshot()['evaluations'])

    def test_nontransient_or_mutating_failures_never_retry(self):
        policy = RecoveryPolicy(enabled=True)
        event = {'node_id': 'train', 'tool_result': {'status': 'error', 'error_code': 'research_spec_mismatch'},
                 'state_before': {}, 'state_after': {}}
        self.assertFalse(policy.permits(event, [], 0))
        event['tool_result']['error_code'] = 'transient_unavailable'
        event['state_after'] = {'changed': True}
        self.assertFalse(policy.permits(event, [], 0))

    def test_resume_after_failed_call_preserves_retry_count_and_completed_nodes(self):
        self.session.propose({})
        self.session.validate({})
        for _ in range(4): self.session.execute({})
        self.assertEqual(self.session.state['phase'], 'recovering')
        restored = PlanningSession.restore(self.output, ScientificMLEnvironment())
        self.assertTrue(restored.run()['execution_success'])
        self.assertEqual(restored.state['tool_calls'], 7)
        self.assertEqual(restored.state['recovery_count'], 1)
        tools = [e['tool_name'] for e in restored.state['events'] if e['event_type'] == 'tool_call']
        self.assertEqual(tools.count('split_dataset'), 1)

    def test_recovery_score_rejects_changed_retry_arguments(self):
        self.session.run()
        episode = self.session.episode()
        calls = [e for e in episode['events'] if e['event_type'] == 'tool_call']
        calls[4]['arguments'] = {'model': 'mean'}
        checks = recovery_checks(self.session.manifest, episode, self.session.state['history'])
        self.assertFalse(checks['retry_preserves_arguments'])

    def test_crash_after_persisted_recovery_decision_does_not_consume_second_retry(self):
        self.session.propose({})
        self.session.validate({})
        for _ in range(4): self.session.execute({})
        with patch.object(self.session, 'revise', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.session.recover({})
        restored = PlanningSession.restore(self.output, ScientificMLEnvironment())
        self.assertTrue(restored.run()['execution_success'])
        self.assertEqual(restored.state['recovery_count'], 1)
        self.assertEqual(restored.state['plan']['version'], 2)
        self.assertEqual(restored.state['tool_calls'], 7)

    def test_total_retry_bound_is_hard_limited(self):
        with self.assertRaises(ValueError): RecoveryPolicy(enabled=True, max_total_retries=99)


@unittest.skipUnless(importlib.util.find_spec('scipy') and importlib.util.find_spec('langgraph'), 'Darcy and planning dependencies required')
class AdaptivePlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_darcy_workflow as fixture
        fixture.DarcyWorkflowTests.setUpClass.__func__(cls)
        cls.spec = replace(cls.spec, model='validation_select', max_train_calls=2)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def make_env(self):
        from rut_science.adaptive_workflow import SelectionDarcyEnvironment
        return SelectionDarcyEnvironment(self.folder)

    def test_plan_roundtrip_and_selected_model_binding_enforced(self):
        plan = public_control_plan(self.spec)
        parsed = PlanSpec.from_dict(plan.to_dict())
        self.assertEqual(parsed.validate(self.spec, self.make_env().available_tools())['nodes'], 8)
        value = plan.to_dict()
        next(n for n in value['nodes'] if n['role'] == 'evaluate')['arguments']['model_id'] = '$fit_ridge.model_id'
        with self.assertRaises(PlanValidationError):
            PlanSpec.from_dict(value).validate(self.spec, self.make_env().available_tools())

    def test_selection_requires_both_candidates_and_only_selected_is_tested(self):
        env, results = self.make_env(), {}
        env.confirm_research_spec(self.spec, source='operator_config', reference='test')
        plan = public_control_plan(self.spec)
        for node in plan.nodes[:5]:
            results[node.node_id] = env.invoke(node.tool, resolve_node(node, results))
            self.assertEqual(results[node.node_id]['status'], 'ok')
        split_id = results['split']['split_id']
        self.assertEqual(env.invoke('train_model', {'split_id': split_id, 'model': 'ridge_field'})['status'], 'error')
        self.assertEqual(env.invoke('evaluate_model', {'model_id': results['fit_ridge']['model_id']})['status'], 'error')
        result = env.invoke('select_model', resolve_node(plan.nodes[5], results))
        self.assertEqual(result['selected_method'], 'ridge_field')
        self.assertEqual(env.invoke('evaluate_model', {'model_id': results['fit_mean']['model_id']})['status'], 'error')
        self.assertEqual(env.invoke('evaluate_model', {'model_id': result['model_id']})['status'], 'ok')
        self.assertEqual(env.invoke('evaluate_model', {'model_id': result['model_id']})['status'], 'error')

    def test_both_data_dependent_selection_outcomes_and_tie_rule(self):
        from rut_science.adaptive_workflow import select_method
        self.assertEqual(select_method({'ridge_field': .1, 'mean_field': .2}), 'ridge_field')
        self.assertEqual(select_method({'ridge_field': .3, 'mean_field': .2}), 'mean_field')
        self.assertEqual(select_method({'ridge_field': .2, 'mean_field': .2}), 'mean_field')

    def test_full_mean_branch_on_constant_field_fixture(self):
        import numpy as np
        from rut_science.darcy_workflow import file_hash
        from rut_science.adaptive_workflow import SelectionDarcyEnvironment
        from rut_science.util import digest, write_json
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)/'data'
            data.mkdir()
            metadata = json.loads((self.folder/'dataset.json').read_text())
            for split in ('train', 'test'):
                with np.load(self.folder/(split+'.npz')) as bundle:
                    coeff, sol = bundle['coeff'], bundle['sol']
                sol[:] = 0.015625  # Exactly representable constant -> both fits tie, mean wins.
                sol[:, [0, -1], :] = 0
                sol[:, :, [0, -1]] = 0
                np.savez_compressed(data/(split+'.npz'), coeff=coeff, sol=sol)
                metadata['bundles'][split]['sha256'] = file_hash(data/(split+'.npz'))
            metadata.pop('dataset_hash')
            metadata['dataset_hash'] = digest(metadata)
            write_json(data/'dataset.json', metadata)
            spec = replace(self.spec, dataset_hash=metadata['dataset_hash'])
            output = Path(directory)/'run'
            output.mkdir()
            session = PlanningSession.create(output, SelectionDarcyEnvironment(data), spec, data=data)
            self.assertTrue(session.run()['execution_success'])
            branch = next(h for h in session.state['history'] if h.get('event') == 'branch_decision')
            self.assertEqual(branch['phase'], 'branch_mean')
            self.assertEqual(branch['selected_method'], 'mean_field')
            self.assertEqual(session.env.snapshot()['budget']['test_calls'], 1)

    def test_full_selection_and_recovery_independent_scientific_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            session = PlanningSession.create(Path(directory), self.make_env(), self.spec, data=self.folder,
                recovery_policy=RecoveryPolicy(enabled=True).to_dict(),
                fault_injection={'tool': 'train_model', 'count': 1, 'error_code': 'transient_unavailable'})
            self.assertTrue(session.run()['execution_success'])
            self.assertTrue(all(session.state['score']['checks'][k] for k in session.state['score']['checks'] if k != 'logical_compliance'))
            self.assertFalse(session.state['score']['strict_execution_success'])
            self.assertEqual(len(session.env.snapshot()['models']), 2)
            self.assertEqual(session.env.snapshot()['budget']['test_calls'], 1)
            self.assertEqual(session.state['tool_calls'], 9)
            self.assertEqual(len([h for h in session.state['history'] if h.get('event') == 'branch_decision']), 1)
            self.assertEqual(verify_artifacts(Path(directory))['status'], 'passed')

    def test_mock_api_intake_plan_execution_recovery_and_shared_ledger(self):
        from rut_science.research_chat import ResearchChat
        from rut_science.intake_contract import offline_extract
        from rut_science.chat_verification import verify_chat
        from rut_science.util import write_json
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)/'API_key_Agent.json'
            write_json(config, {'API': 'fake_local_test_key', 'endpoint': 'https://example.invalid/chat/completions'})
            chat = ResearchChat.create(Path(directory)/'chat', data=self.folder, api_config=config,
                recover=True, max_requests=4, fault_tool='train_model', fault_count=1, progress=lambda _: None)
            class Reply:
                def __init__(self, value): self.value = value
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, *args):
                    return json.dumps({'model': 'mock-deepseek', 'choices': [{'message': {'content': json.dumps(self.value)}}],
                        'usage': {'prompt_tokens': 100, 'completion_tokens': 50}}).encode()
            def provider(request, **kwargs):
                body = json.loads(request.data)
                content = body['messages'][-1]['content']
                if 'latest_user_text' in content:
                    context = json.loads(content)
                    return Reply(offline_extract(context['latest_user_text'], context['current_fields']))
                context = json.loads(content.split('\n', 1)[1])
                plan = replace(public_control_plan(ResearchSpec(**context['research_spec'])),
                    max_tool_calls=context['requested_tool_budget'], plan_id='mock_generated_plan').to_dict()
                for node in plan['nodes']:
                    node['node_id'] = 'job_'+node['node_id']
                    node['depends_on'] = ['job_'+n for n in node['depends_on']]
                    node['arguments'] = {k: '$job_'+v[1:] if isinstance(v, str) and v.startswith('$') else v for k, v in node['arguments'].items()}
                return Reply(plan)
            with patch('urllib.request.urlopen', side_effect=provider) as network:
                chat.submit('Darcy')
                self.assertFalse(chat.state['executions'])
                chat.submit('pressure validation_select alpha=1 seed=2026 max_train_calls=2 max_test_calls=1')
                self.assertFalse(chat.state['executions'])
                chat.submit(' /confirm ', actor='scripted_operator')
                self.assertEqual(network.call_count, 3)
            self.assertEqual(chat.budget.snapshot()['requests'], 3)
            self.assertEqual(chat.budget.snapshot()['accounted_tokens'], 450)
            self.assertEqual(chat.state['executions'][0]['phase'], 'complete')
            self.assertEqual(verify_chat(chat.output)['status'], 'passed')
