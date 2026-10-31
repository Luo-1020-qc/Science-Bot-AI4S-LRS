"""Real conversation/HTTP regression for routing, correction guards and method risks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.router import route_request
from rut_science.science_bot.general.planning.routing import route_override
from rut_science.science_bot.general.planning.ledger import load, contract_hash, validate
from rut_science.science_bot.general.planning.runtime import review
from rut_science.science_bot.presentation import session_view, export_bundle
from test_planning_blueprint import complete_state
from test_planning_intake import Provider, proposal, update
import test_general_http as http_helpers

ROOT=Path(__file__).resolve().parents[2]
NATURAL_GOALS=[
    '想比较两种吸附材料，请通过选项帮我做实验计划。',
    '请规划材料甲乙的配对比较，先做固定预算先导。',
    '我要比较两个模型，请先做科研规划，数据还没确定。',
    '请规划合成二维场上的模型比较，记录代码版本和配置，不执行训练。',
    '帮我整理实验计划，比较两个处理的响应。',
    '实验计划是比较新旧催化剂，样本依据还不清楚。',
    '研究方案先从两种算法的公平比较开始。',
    '计划研究温度与产率的关系，先明确边界。',
    '设计一下设备故障预测的验证方案。',
    '能帮我把论文复现变成一个实验方案吗？',
    '希望研究材料的稳定性，先做方案讨论。',
    '我想比较模型A与模型B在合成数据上的误差。',
    '我们准备复现论文中的核心比较，请先澄清实验单位。',
    '我打算评估预测模型在新设备上的表现。',
    '帮我规划小规模先导实验，没有方差记录。',
    '本轮的研究计划只讨论独立样本及验收。',
    '请设计预测评估方案，包含数据划分和种子记录。',
    '我们想验证一种材料能否提高响应，先规划。',
    '我希望比较两种模型，最后形成实验设计。',
    '研究计划需要先确定适用范围和停止条件。',
    'Help me plan an experiment comparing two models.',
    'I want to design a paired study of two materials.',
    'We need a research plan for a pilot experiment.',
    'Plan a prediction evaluation study with held out devices.',
    'Design an experiment for a synthetic field model comparison.',
    '想复现一个论文结论，不知道先确认哪些条件。',
    '我想研究模型效果，暂时没有执行授权。',
    '先写实验方案，再由导师决定是否执行。',
    '帮我形成模型比较的研究计划，预算是两小时。',
    '给我一个材料实验的规划，通过选项确定边界。'
]


class ReliabilityConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.local')
        self.session=GeneralSession.create(Path(self.tmp.name)/'sessions',backend='offline')
    def tearDown(self):self.tmp.cleanup()
    def send(self,text):
        row=self.session.message(text)
        self.assertFalse(row.get('planning_error'),row)
        return row
    def fill(self):
        values={f:r['value'] for f,r in complete_state()['facts'].items()}
        self.send('/plan '+json.dumps(values,ensure_ascii=False))
        self.assertTrue(review(load(self.session))['ready'])
    def test_thirty_phrasings_enter_the_real_planning_ledger(self):
        for text in NATURAL_GOALS:
            with self.subTest(text=text):
                session=GeneralSession.create(Path(self.tmp.name)/'phrases',backend='offline')
                result=session.message(text)
                self.assertEqual(result['intent'],'planning',result)
                self.assertEqual(load(session)['facts']['research_question']['value'],text)
                self.assertEqual(session.resources()['llm_requests'],0)
                self.assertIsNone(session.numeric);self.assertIsNone(session.tabular)
    def test_old_eight_initial_inputs_now_route_to_planning(self):
        cases=json.loads((ROOT/'docs/evaluation/comprehensive_2026-10-30/live_cases.json').read_text(encoding='utf-8'))['cases']
        for case in cases:
            with self.subTest(case=case['id']):
                result=GeneralSession.create(Path(self.tmp.name)/'old_cases',backend='offline').message(case['inputs'][0])
                self.assertEqual(result['intent'],'planning',result)
    def test_explicit_file_execution_and_other_commands_stay_separate(self):
        self.send('帮我做实验计划，比较模型误差。')
        for text in ['运行 generated 预算2','直接训练CViT','读取 notes.md','/tools list','/research status','/doe demo','什么是强化学习','今天天气如何','我想比较两款手机的价格']:
            with self.subTest(text=text):
                self.assertFalse(route_override(self.session,text,route_request(text)))
    def test_multi_round_prediction_language_stays_in_planning(self):
        self.send('我想比较两个模型，请做实验计划。')
        for text in ['本轮只预测未见设备，不做因果结论。','训练与验证按设备隔离，最后测试另留设备。','记录代码版本、配置和种子，暂不执行。']:
            self.assertEqual(self.send(text)['intent'],'planning')
    def test_literal_budget_correction_shows_old_new_and_invalidates_approval(self):
        self.fill();self.send('/plan approve '+contract_hash(load(self.session)))
        row=self.send('更正：经费缩减了，后续最多两次运行、一小时上限，之前六次运行的说法作废。请重查样本与验收。')
        state=load(self.session)
        self.assertEqual(state['facts']['resources']['value'],'后续最多两次运行、一小时上限')
        self.assertIsNone(state['approval']);self.assertIn('sampling',state['stale'])
        self.assertIn('→',row['update_feedback']['text']);self.assertIn('已采纳',row['update_feedback']['text'])
        self.assertFalse(row['execution_authorized'])
    def test_failed_revision_blocks_old_approval_across_restore_and_accept(self):
        self.fill();old=contract_hash(load(self.session));self.send('/plan approve '+old)
        row=self.send('/plan revise resources: ')
        self.assertIn('未采纳',row['update_feedback']['text'])
        state=load(self.session);self.assertIn('resources',state['pending_revisions']);self.assertIsNone(state['approval'])
        self.session=GeneralSession.restore(self.session.folder)
        self.send('/plan accept resources')
        self.assertTrue(any(r['code']=='unapplied_revision' for r in review(load(self.session))['blockers']))
        denied=self.session.message('/plan approve '+old);self.assertTrue(denied.get('planning_error'))
        self.send('/plan resources: 最多48次处理应用，4小时上限。')
        self.assertFalse(load(self.session).get('pending_revisions'))
    def test_failed_semantic_revision_is_visible_and_never_reuses_budget(self):
        self.fill();before=deepcopy(load(self.session)['facts']['resources'])
        self.session.meta['backend']='api';self.session._provider=Provider(error=ValueError('invalid provider shape'))
        row=self.send('更正：预算待重新核实，请修改原来的安排。')
        self.assertEqual(load(self.session)['facts']['resources'],before)
        self.assertIn('未采纳',row['answer']);self.assertIn('resources',load(self.session)['pending_revisions'])
        self.assertIn('校验',row['update_feedback']['text'])
        self.assertFalse(review(load(self.session))['ready'])
    def test_supplement_does_not_rewrite_question_but_explicit_goal_change_does(self):
        self.send('我想比较两个模型，请规划实验。');old=load(self.session)['facts']['research_question']['value']
        text='只限本校的合成设备数据，不讨论因果。'
        api=Provider(proposal([update('research_question','研究本校数据',text,'proposed'),update('scope',text,text)]))
        self.session.meta['backend']='api';self.session._provider=api
        row=self.send(text)
        self.assertEqual(load(self.session)['facts']['research_question']['value'],old)
        self.assertNotIn('research_question',load(self.session)['conflicts'])
        self.assertIn('scope',load(self.session)['facts']);self.assertIn('未替换',row['update_feedback']['text'])
        text='更正：研究目的改为预测未见设备。'
        api.response=proposal([update('objective_type','prediction','预测未见设备')])
        self.send(text);self.assertEqual(load(self.session)['facts']['objective_type']['value'],'prediction')
    def test_unknown_feedback_and_literal_declared_updates(self):
        self.send('/plan research_question: 比较两个模型')
        row=self.send('/plan sampling: 未知')
        self.assertIn('已保留未知',row['update_feedback']['text'])
        self.assertNotIn('sampling',load(self.session)['facts'])
    def test_feedback_persists_and_exports_with_method_notice(self):
        self.send('/plan research_question: 比较两个模型')
        restored=GeneralSession.restore(self.session.folder)
        self.assertIn('已采纳',session_view(restored)['last_answer'])
        self.assertIn('方法状态',session_view(restored)['last_answer'])
        paths=export_bundle(restored)
        self.assertIn('方法状态',paths['markdown'].read_text(encoding='utf-8'))
    def test_short_yes_confirmation_also_has_an_update_receipt(self):
        text='我想比较两种模型，先规划。'
        self.session.meta['backend']='api'
        self.session._provider=Provider(proposal([update('research_question','比较两种模型的误差',text,'proposed')]))
        self.send(text);row=self.send('是')
        self.assertEqual(load(self.session)['facts']['research_question']['status'],'declared')
        self.assertIn('已采纳',row['update_feedback']['text'])
    def test_evidence_step_receipt_keeps_the_original_unknown(self):
        self.send('/plan research_question: 比较两种模型')
        self.send('/plan sampling: 未知')
        row=self.send('先核查既有先导记录，再请导师复核独立单位。')
        self.assertIn('已记录拟议',row['update_feedback']['text'])
        self.assertIn('sampling',load(self.session)['unknown'])
        self.assertNotIn('sampling',load(self.session)['facts'])
    def test_legacy_state_hash_is_unchanged_with_empty_extensions(self):
        from rut_science.science_bot.general.planning.ledger import new_state
        state=new_state();old=contract_hash(state)
        state['pending_revisions']={};self.assertEqual(contract_hash(state),old);validate(state)
        state['last_update']={'turn':1,'entries':[],'text':'本轮未修改。'}
        self.assertEqual(contract_hash(state),old);validate(state)
    def test_explicit_research_question_is_not_replaced_by_the_complete_input(self):
        values={f:r['value'] for f,r in complete_state()['facts'].items()}
        self.send('/plan '+json.dumps(values,ensure_ascii=False))
        self.assertEqual(load(self.session)['facts']['research_question']['value'],values['research_question'])
        other=GeneralSession.create(Path(self.tmp.name)/'labelled',backend='offline')
        text='研究问题：比较两种模型\n研究边界：仅限同一分布的合成数据\n资源边界：2小时上限'
        other.message('/plan '+text)
        self.assertEqual(load(other)['facts']['research_question']['value'],'比较两种模型')
        exact='演示预算最多4次拟合，1小时上限'
        self.send('/plan revise resources: '+exact)
        self.assertEqual(load(self.session)['facts']['resources']['value'],exact)
    def test_uncertain_budget_question_does_not_become_a_declared_new_limit(self):
        self.fill();text='更正：我还不确定是否最多两次运行、一小时上限。'
        self.session.meta['backend']='api'
        self.session._provider=Provider(proposal(unknown=[{'field':'resources','quote':'我还不确定是否最多两次运行、一小时上限'}]))
        self.send(text)
        self.assertIn('resources',load(self.session)['unknown'])
        self.assertNotIn('resources',load(self.session)['facts'])
    def test_narrative_colon_is_not_an_unknown_field_error(self):
        text='实验计划：比较两种材料，先确认适用范围。'
        self.session.meta['backend']='api'
        self.session._provider=Provider(proposal([update('research_question',text,text)]))
        row=self.send(text)
        self.assertEqual(row['intent'],'planning');self.assertTrue(row['model_used'])
        self.assertNotIn('未登记字段',row['update_feedback']['text'])
    def test_old_twelve_risk_probes_block_all_bad_declarations(self):
        cases=json.loads((ROOT/'docs/evaluation/comprehensive_2026-10-30/risk_probes/cases.json').read_text(encoding='utf-8'))
        for case in cases:
            with self.subTest(case=case['id']):
                session=GeneralSession.create(Path(self.tmp.name)/'risks',backend='offline')
                row=session.message('/plan '+json.dumps(case['input'],ensure_ascii=False))
                self.assertFalse(row.get('planning_error'),row)
                assessment=review(load(session))
                self.assertEqual(assessment['ready'],case['id']=='complete_pilot',assessment)
                if case['diagnostic_hypothesis']=='flag_semantic_risk_for_human':
                    self.assertTrue(assessment['declarations_complete']);self.assertTrue(assessment['method_risks'])
                self.assertFalse(assessment['scientific_claim_verified'])
    def test_good_negations_do_not_trigger_method_risks(self):
        examples={
            'experimental_unit':['不把网格点作为独立样本；每个完整场是单位。','同一完整场配对，网格点不是独立重复。','并非没有配对关系，每个完整场内匹配。','每个独立合成数据实现为单位；同一实现上的网格点不作为独立重复。'],
            'analysis':['不用最终测试误差选择模型，使用验证集选择。','最终测试集不用于选择模型；报告均值差和区间。','不以网格点重采样，以完整场为单位bootstrap区间。'],
            'acceptance':['阴性结果不能不报告；资源上限即停止。','不得隐瞒阴性；不一直试到显著，按预算停止。','阴性和不确定结果都报告，不按结果加预算。'],
            'sampling':['假定方差用于敏感性分析，不保证功效。','固定预算先导，不宣称功效保证。']}
        for field,values in examples.items():
            for value in values:
                with self.subTest(field=field,value=value):
                    state=complete_state();state['facts']['design']['value']='paired'
                    state['facts'][field]['value']=value
                    self.assertEqual(review(state)['method_risks'],[])
    def test_method_review_is_pending_even_for_complete_or_approved_plan(self):
        self.fill();state=load(self.session);self.assertTrue(review(state)['declarations_complete'])
        self.send('/plan approve '+contract_hash(state));result=self.send('/plan draft')
        self.assertIn('方法状态：待人工复核',result['answer'])
        self.assertFalse(result['scientific_claim_verified'])


class ReliabilityHTTPTests(unittest.TestCase):
    setUp=http_helpers.GeneralHTTPTests.setUp
    tearDown=http_helpers.GeneralHTTPTests.tearDown
    request=http_helpers.GeneralHTTPTests.request
    create=http_helpers.GeneralHTTPTests.create
    def test_feedback_and_guard_are_idempotent_and_survive_http_restore(self):
        identity=self.create(backend='offline')['id'];url=f'/{identity}/messages'
        status,row=self.request(url,{'text':'帮我做实验计划，比较两个模型。'},'new-plan')
        self.assertEqual(status,200,row);self.assertEqual(row['intent'],'planning')
        body={'text':'/plan revise resources: '}
        _,first=self.request(url,body,'budget-change')
        _,second=self.request(url,body,'budget-change')
        self.assertEqual(first,second);self.assertIn('未采纳',first['update_feedback']['text'])
        self.server.service.sessions.clear()
        _,current=self.request(f'/{identity}')
        self.assertTrue(any(r['code']=='unapplied_revision' for r in current['planning']['review']['blockers']))


if __name__=='__main__':unittest.main()
