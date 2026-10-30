"""End-to-end planning without real model/API/scientific execution."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.ledger import load,contract_hash
from rut_science.science_bot.general.planning.runtime import review
from test_planning_blueprint import complete_state

ROOT=Path(__file__).resolve().parents[2]


class FakeProvider:
    def __init__(self,updates):self.updates=updates;self.calls=[];self.marks=[]
    def complete(self,messages,tools=None,role=None):
        self.calls.append({'messages':messages,'tools':tools,'role':role})
        return {'content':None,'tool_calls':[{'id':'extract1','name':'propose_research_scope','arguments':{'updates':self.updates,'unknown':[]}}]}
    def mark_validation(self,*args):self.marks.append(args)


class ResearchPlanningTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.local')
        self.session=GeneralSession.create(Path(self.tmp.name),backend='offline')
    def tearDown(self):self.tmp.cleanup()
    def send(self,text):
        result=self.session.message(text)
        self.assertFalse(result.get('planning_error'),result)
        return result
    def fill(self):
        facts={f:r['value'] for f,r in complete_state()['facts'].items()}
        self.send('/plan new')
        items=list(facts.items())
        for start in range(0,len(items),5):self.send('/plan '+json.dumps(dict(items[start:start+5]),ensure_ascii=False))
        self.assertTrue(review(load(self.session))['ready'],review(load(self.session))['blockers'])

    def test_vague_goal_creates_plan_no_job_and_at_most_two_questions(self):
        with patch.object(self.session,'provider',side_effect=AssertionError('offline planning must not call API')):
            out=self.send('我想研究CViT效果，帮我规划实验，但边界还没想清楚')
        self.assertEqual(out['intent'],'planning');self.assertLessEqual(len(out['questions']),2)
        self.assertIsNone(self.session.numeric);self.assertIsNone(self.session.tabular)
        self.assertEqual(self.session.meta['tool_attempts'],0)
        self.assertFalse(out['execution_authorized'])
        self.assertEqual(self.session.resources()['llm_requests'],0)

    def test_native_api_semantics_uses_same_provider_and_grounded_state(self):
        text='我想比较CViT与FNO在同一数据上的误差'
        provider=FakeProvider([{'field':'research_question','value':text,'quote':text,'status':'declared'}])
        self.session.meta['backend']='api';self.session._provider=provider
        out=self.send(text)
        self.assertEqual(load(self.session)['facts']['research_question']['quote'],text)
        self.assertEqual(provider.calls[0]['role'],'experiment_planning')
        self.assertEqual(self.session.meta['tool_attempts'],0)
        self.assertGreater(len(out['questions']),0)

    def test_multiple_rounds_restore_map_and_semantic_options(self):
        self.send('/plan research_question: 比较模型在声明数据上的误差并决定后续验证')
        out=self.send('1')
        self.assertEqual(load(self.session)['facts']['objective_type']['value'],'comparison')
        restored=GeneralSession.restore(self.session.folder)
        self.assertEqual(restored.status()['planning']['facts'],self.session.status()['planning']['facts'])
        self.assertIn('比较模型',restored.message('/plan map')['answer'])

    def test_approval_version_bound_and_revision_invalidates_dependencies(self):
        self.fill();old_hash=contract_hash(load(self.session))
        self.send('/plan approve '+old_hash)
        self.assertTrue(load(self.session)['approval'])
        self.send('/plan revise experimental_unit: 以独立受试者为分配与推断单位，不以重复测量代替重复')
        state=load(self.session)
        self.assertIsNone(state['approval']);self.assertIn('analysis',state['stale'])
        self.assertFalse(review(state)['ready'])
        denied=self.session.message('/plan approve '+old_hash)
        self.assertTrue(denied['planning_error'])

    def test_conflict_preserved_then_explicitly_resolved(self):
        self.send('/plan resources: 最多48次运行，4小时')
        self.send('/plan resources: 最多20次运行，2小时')
        state=load(self.session)
        self.assertEqual(state['facts']['resources']['value'],'最多48次运行，4小时')
        self.assertIn('resources',state['conflicts'])
        self.send('/plan revise resources: 最多20次运行，2小时')
        self.assertNotIn('resources',load(self.session)['conflicts'])

    def test_unknown_does_not_fill_default_or_stop_entire_project(self):
        self.send('/plan sampling: 未知')
        state=load(self.session)
        self.assertIn('sampling',state['unknown']);self.assertTrue(state['active'])
        self.assertNotIn('sampling',state['facts'])
        self.assertNotIn('sigma',json.dumps(state['facts']))

    def test_redeclaring_old_value_resolves_conflict_and_unknown(self):
        self.send('/plan resources: 最多48次运行')
        self.send('/plan resources: 最多20次运行')
        self.send('/plan revise resources: 最多48次运行')
        self.assertNotIn('resources',load(self.session)['conflicts'])
        self.send('/plan resources: 未知')
        self.assertNotIn('resources',load(self.session)['facts'])
        self.send('/plan resources: 最多48次运行')
        self.assertNotIn('resources',load(self.session)['unknown'])

    def test_new_unknown_clears_approval_and_propagates_recheck(self):
        self.fill();self.send('/plan approve '+contract_hash(load(self.session)))
        self.send('/plan experimental_unit: 未知')
        state=load(self.session)
        self.assertIsNone(state['approval']);self.assertNotIn('experimental_unit',state['facts'])
        self.assertIn('analysis',state['stale'])
        self.assertIn('尚未明确',self.send('/plan map')['answer'])

    def test_proposals_require_confirmation_and_do_not_grant_permissions(self):
        text='我想比较误差，但还没有决定方法'
        provider=FakeProvider([{'field':'research_question','value':'比较两种预测器的误差','quote':text,'status':'proposed'}])
        self.session.meta['backend']='api';self.session._provider=provider
        self.send(text)
        self.assertEqual(load(self.session)['facts']['research_question']['status'],'proposed')
        self.send('/plan accept research_question')
        self.assertEqual(load(self.session)['facts']['research_question']['status'],'declared')
        self.assertFalse(self.session.status()['confirmed'])

    def test_export_and_handoff_preserve_manual_capabilities(self):
        self.fill();self.send('/plan approve '+contract_hash(load(self.session)))
        out=self.send('/plan handoff');self.assertFalse(out['handoff']['execution_authorized'])
        self.assertTrue(any(r['capability']=='manual' for r in out['handoff']['steps']))
        exported=self.send('/plan export')['export']
        self.assertTrue((self.session.folder/exported['json_ref']).exists())
        self.assertIn('尚未执行',(self.session.folder/exported['markdown_ref']).read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):self.session.confirm('anything')
        with self.assertRaises(ValueError):self.session.run()
        self.assertIsNone(self.session.numeric)

    def test_snapshot_tamper_and_cross_session_path_rejected(self):
        self.send('/plan research_question: 检验声明范围内的模型差异')
        path=self.session.folder/self.session.meta['planning_ref']
        record=json.loads(path.read_text(encoding='utf-8'));record['facts'].clear()
        path.write_text(json.dumps(record),encoding='utf-8')
        with self.assertRaises(ValueError):GeneralSession.restore(self.session.folder)

    def test_context_switch_and_explicit_tools_are_not_eaten(self):
        self.send('/plan research_question: 比较声明范围内的模型误差')
        self.assertTrue(load(self.session)['active'])
        out=self.session.message('/tools list')
        self.assertEqual(out['intent'],'research');self.assertFalse(load(self.session)['active'])
        self.send('/plan resume');self.assertTrue(load(self.session)['active'])

    def test_concept_question_explains_without_mutating_facts_or_api(self):
        self.send('/plan experimental_unit: 独立运行作为声明的实验单位')
        before=deepcopy(load(self.session)['facts'])
        with patch.object(self.session,'provider',side_effect=AssertionError('concept question is local')):
            result=self.send('什么是实验单位，为什么不能把网格点当作重复？')
        self.assertIn('网格点',result['answer'])
        self.assertEqual(load(self.session)['facts'],before)

    def test_explicit_tool_followup_carries_only_approved_plan_context(self):
        self.fill();self.send('/plan approve '+contract_hash(load(self.session)))
        identity=contract_hash(load(self.session))
        with patch('rut_science.science_bot.general.tool_library.respond',return_value={'intent':'research','answer':'只读交接验证'}) as respond:
            result=self.session.message('/tools chat 按当前规划检查缺失工具参数，不要启动真实作业')
        self.assertEqual(result['planning_context_hash'],identity)
        self.assertIn(identity,respond.call_args.args[1])
        self.assertIn('不执行真实训练',respond.call_args.args[1])
        self.assertEqual(self.session.meta['tool_attempts'],0)

    def test_unapproved_plan_not_passed_to_tool_model(self):
        self.send('/plan research_question: 比较声明范围内的模型误差')
        with patch('rut_science.science_bot.general.tool_library.respond',side_effect=AssertionError('unapproved context')):
            result=self.session.message('/tools chat 按当前规划继续')
        self.assertTrue(result['research_error'])
        self.assertIn('尚未确认',result['answer'])

    def test_whitespace_command_uses_same_planning_route(self):
        result=self.send('   /plan research_question: 比较声明数据范围内的模型误差   ')
        self.assertEqual(result['intent'],'planning')

    def test_vague_reproduction_and_unsatisfactory_model_start_clarification(self):
        for text in ['我想复现LinearNO论文，但不知道从哪里开始','我的模型不太好，不知道怎么评估']:
            with self.subTest(text=text):
                result=self.send(text)
                self.assertEqual(result['intent'],'planning')
                self.assertFalse(result['execution_authorized'])

    def test_knowledge_question_does_not_create_plan(self):
        result=self.session.message('什么是CViT？')
        self.assertEqual(result['intent'],'chat');self.assertIsNone(load(self.session))

    def test_cancel_during_semantic_call_keeps_previous_boundary_and_phase(self):
        self.send('/plan scope: 只讨论声明的合成数据范围')
        before=deepcopy(load(self.session)['facts'])
        self.session.meta['backend']='api'
        provider=FakeProvider([])
        original=provider.complete
        def cancelled(*args,**kwargs):
            value=original(*args,**kwargs);self.session.cancel_requested.set();return value
        provider.complete=cancelled;self.session._provider=provider
        result=self.session.message('请继续帮我明确模型比较的研究问题')
        self.assertTrue(result['planning_error'])
        self.assertEqual(self.session.meta['phase'],'cancelled')
        self.assertEqual(load(self.session)['facts'],before)


if __name__=='__main__':unittest.main()
