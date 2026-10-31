"""Experimental drafts, provenance, dialogue and immutable delivery contracts."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import threading
import unittest

from rut_science.budget import RunLimitError
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning import synthesis
from rut_science.science_bot.general.planning.blueprint import review, export_markdown
from rut_science.science_bot.general.planning.ledger import new_state, load, save, contract_hash, validate
from rut_science.science_bot.presentation import export_bundle, export_plan, session_view, delivery_html
from test_planning_intake import Provider, proposal
from test_planning_blueprint import complete_state

ROOT=Path(__file__).resolve().parents[2]
GOAL='比较模型甲乙在合成二维场上的预测误差，最多2小时，本轮只规划。'


def fact(value):return {'value':value,'quote':value,'status':'declared','turn':1}


def fixture(state):
    refs=[{'source':'fact','key':'research_question','quote':state['facts']['research_question']['value']}]
    if 'resources' in state['facts']:refs.append({'source':'fact','key':'resources','quote':state['facts']['resources']['value']})
    return {
        'decision':'在限定合成场景下，判断误差与成本取舍是否值得继续研究。',
        'recommendation':'先核实模型与数据是否就绪，再在共享留出场上配对评测甲乙模型。',
        'rationale':'共享评测对象可以观察对象内差异；先核算耗时避免训练挤占评测预算。',
        'alternatives':['若模型未训练，先做成本探测，只在预算可行时安排训练和验证。'],
        'assumptions':['若完整场来自独立生成过程，可考虑以完整场为推断单位；独立性待核实。'],
        'matrix':[{'comparison':'甲模型与乙模型','unit':'同一完整场配对，网格点不作为独立重复',
                   'controls':'共享最终留出对象和预处理；验证用于选择，测试不用于调参',
                   'measurement':'每个完整场的误差与推理耗时'}],
        'steps':[
            {'title':'核查输入并探测成本','action':'登记数据和模型版本，试运行测耗时，按原资源上限核算可行性。',
             'inputs':'研究者选定的数据与模型配置','output':'版本清单和成本估计','acceptance':'每项有版本；超限则缩小目标或停止'},
            {'title':'冻结配对评测条件','action':'按来源隔离训练、验证和测试；甲乙使用相同最终留出场。',
             'inputs':'核实的对象关系及来源','output':'共享划分清单和冻结配置','acceptance':'对象无跨分区共享，最终测试不选模型'},
            {'title':'计算差异并交付比较','action':'逐场记录甲乙误差和耗时，汇总配对差异与不确定性。',
             'inputs':'冻结配置及后续真实观测','output':'逐场比较表、区间与限制说明','acceptance':'包含失败、阴性和不确定结果'}],
        'analysis':'估计完整场层面的误差差值，按独立场汇总差异与区间；样本不足时只作描述。',
        'budget_plan':'先探测单次成本再核算原上限内能否完成；无法容纳则缩小本轮目标，不自动加预算。',
        'stop_rule':'产物逐项齐全即可交付；阴性和不确定同样报告，资源到上限停止。',
        'open_questions':[{'field':'sampling','issue':'独立场数与方差依据未知','action':'核查生成记录或安排先导后确定样本依据'}],
        'references':refs}


def response(state, questions=None):
    return {'content':None,'tool_calls':[{'name':synthesis.SPEC.name,'arguments':{'plan':fixture(state),'questions':questions or []}}]}


class NativePlans(Provider):
    def complete(self,messages,tools=None,role=None):
        self.calls.append({'messages':messages,'tools':tools,'role':role})
        if role=='experiment_planning':return proposal()
        data=json.loads(messages[-1]['content'])
        state=new_state();state['facts']={r['key']:fact(r['text']) for r in data['sources'] if r['source']=='fact'}
        result=response(state)
        result['tool_calls'][0]['arguments']['plan']['budget_plan']='遵守当前限制：'+state['facts'].get('resources',{}).get('value','资源上限待明确')+'；先测成本，超限停止。'
        if 'data_source' in data['question_context']['allowed_fields']:
            result['tool_calls'][0]['arguments']['questions']=[{
                'field':'data_source','kind':'missing','question':'模型比较现在具备哪些可用材料？',
                'rationale':'模型和数据是否已就绪，会改变先训练还是直接评测的路线。',
                'options':[{'label':'模型和数据都已就绪','value':'已有训练好的模型和明确版本的数据，可以先核对共享评测条件。'},
                           {'label':'有数据，模型还需训练','value':'已有数据但模型尚未训练，先核算训练成本再决定比较路线。'}],
                'references':[{'source':'fact','key':'research_question','quote':state['facts']['research_question']['value']}]}]
        return result


class PlanSynthesisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.local');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.state=new_state();self.state['facts']={'research_question':fact(GOAL),'resources':fact('最多2小时')}
        self.provider=Provider(response(self.state))
        self.session=SimpleNamespace(meta={'backend':'api'},provider=lambda:self.provider,
            pause_requested=threading.Event(),cancel_requested=threading.Event())
    def generate(self,**kwargs):return synthesis.generate(self.session,self.state,GOAL,review(self.state),2,**kwargs)
    def conversation(self):
        s=GeneralSession.create(self.root/'sessions',backend='api',workspace=self.root)
        s._provider=NativePlans();return s
    def send(self,s,text):
        result=s.message(text);self.assertFalse(result.get('planning_error'),result);return result

    def test_generation_is_one_read_only_proposal_with_concrete_steps(self):
        before=deepcopy(self.state);identity=contract_hash(self.state)
        result=self.generate()
        self.assertEqual(result['record']['mode'],'llm');self.assertEqual(len(self.provider.calls),1)
        self.assertEqual(self.provider.calls[0]['role'],'planning_synthesis')
        self.assertEqual(self.state,before);self.assertEqual(contract_hash(self.state),identity)
        for step in result['record']['content']['steps']:
            self.assertTrue(all(step[k] for k in ('inputs','action','output','acceptance')))

    def test_reference_resource_numeric_authority_and_method_checks(self):
        mutations=[lambda p:p['references'][0].update(quote='虚构的论文内容'),
                   lambda p:p['references'].pop(),lambda p:p.update(analysis='使用64个样本保证结果。'),
                   lambda p:p.update(recommendation='已授权执行，自动启动训练。'),
                   lambda p:p['matrix'][0].update(unit='将网格点作为独立样本'),
                   lambda p:p.update(analysis='用最终测试集选择模型并调参。')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.provider.response=response(self.state);mutate(self.provider.response['tool_calls'][0]['arguments']['plan'])
                self.assertEqual(self.generate()['record']['mode'],'template')
                self.assertEqual(self.provider.validations[-1][0],'rejected')

    def test_schema_rejects_missing_actions_and_unregistered_gaps(self):
        for field in ('action','output','acceptance'):
            self.provider.response=response(self.state)
            self.provider.response['tool_calls'][0]['arguments']['plan']['steps'][0].pop(field)
            self.assertIsNone(self.generate()['record']['content'])
        self.provider.response=response(self.state)
        self.provider.response['tool_calls'][0]['arguments']['plan']['open_questions'][0]['field']='made_up'
        self.assertEqual(self.generate()['record']['reason'],'UnknownPlanGapField')

    def test_unknowns_are_not_filled_by_design_suggestions(self):
        self.state['unknown']=['sampling'];result=self.generate()
        self.state['plan_synthesis']=result['record'];validate(self.state)
        self.assertEqual(self.state['unknown'],['sampling']);self.assertNotIn('sampling',self.state['facts'])
        self.assertFalse(review(self.state)['ready'])

    def test_failures_cache_and_explicit_refresh_do_not_retry_implicitly(self):
        self.provider.error=RunLimitError('budget')
        first=self.generate();self.state['plan_synthesis']=first['record']
        self.assertEqual(first['record']['mode'],'template');count=len(self.provider.calls)
        self.assertTrue(self.generate()['cached']);self.assertEqual(len(self.provider.calls),count)
        self.generate(force=True);self.assertEqual(len(self.provider.calls),count+1)

    def test_offline_cancel_context_limit_do_not_call_provider(self):
        self.session.meta['backend']='offline';self.assertEqual(self.generate()['record']['reason'],'offline')
        self.session.meta['backend']='api';self.session.cancel_requested.set()
        self.assertEqual(self.generate()['record']['reason'],'interrupted');self.assertFalse(self.provider.calls)
        self.session.cancel_requested.clear()
        for k in complete_state()['facts']:self.state['facts'][k]=fact('大量输入'*700)
        self.assertEqual(self.generate()['record']['reason'],'context_limit');self.assertFalse(self.provider.calls)

    def test_auto_initial_draft_and_contextual_choice_use_existing_dialogue(self):
        s=self.conversation();result=self.send(s,'/plan '+GOAL)
        self.assertEqual(result['plan_synthesis']['status'],'current',result)
        self.assertIn('实验初稿',result['answer']);self.assertEqual(len(s._provider.calls),2)
        q=result['questions'][0];self.assertEqual(q['field'],'data_source')
        self.assertEqual(q['options'][1]['label'],'有数据，模型还需训练')
        self.assertFalse(result['execution_authorized']);self.assertIsNone(s.numeric);self.assertIsNone(s.tabular)
        second=self.send(s,'2');self.assertIn('模型尚未训练',load(s)['facts']['data_source']['value'])
        self.assertEqual(second['plan_synthesis']['status'],'current')

    def test_current_draft_is_cached_across_views_restore_and_all_exports(self):
        s=self.conversation();self.send(s,'/plan '+GOAL);count=len(s._provider.calls)
        original=contract_hash(load(s))
        for text in ('/plan draft','/plan map','/plan review','/plan synthesize','/plan export'):
            self.send(s,text)
        self.assertEqual(len(s._provider.calls),count);self.assertEqual(contract_hash(load(s)),original)
        paths=export_bundle(s)
        self.assertTrue(paths)
        restored=GeneralSession.restore(s.folder)
        self.assertEqual(session_view(restored)['planning']['design_readout']['synthesis_status'],'current')
        self.assertIn('核查输入',export_markdown(load(restored)))

    def test_resource_correction_regenerates_against_new_limit(self):
        s=self.conversation();self.send(s,'/plan '+GOAL);old=contract_hash(load(s))
        self.send(s,'/plan revise resources: 最多1小时，超限停止')
        state=load(s);self.assertNotEqual(contract_hash(state),old)
        self.assertIn('最多1小时',state['plan_synthesis']['content']['budget_plan'])
        self.assertIsNone(state['approval']);self.assertEqual(synthesis.projection(state)['status'],'current')

    def test_stale_draft_is_hidden_and_blocks_approval_until_updated(self):
        state=complete_state();p=Provider(response(state))
        self.session.provider=lambda:p
        state['plan_synthesis']=synthesis.generate(self.session,state,'',review(state),1)['record']
        self.assertEqual(synthesis.projection(state)['status'],'current')
        state['facts']['resources']=fact('最多1小时')
        self.assertEqual(synthesis.projection(state)['status'],'stale')
        self.assertIsNone(synthesis.sections(state))
        self.assertTrue(any(r['code']=='synthesized_plan_stale' for r in review(state)['blockers']))

    def test_draft_body_is_in_approval_hash_but_empty_extension_keeps_old_hash(self):
        old=contract_hash(self.state);self.session.meta['backend']='offline'
        self.state['plan_synthesis']=self.generate()['record'];self.assertEqual(contract_hash(self.state),old)
        self.session.meta['backend']='api';self.state['plan_synthesis']=self.generate(force=True)['record']
        draft_hash=contract_hash(self.state);self.assertNotEqual(old,draft_hash)
        self.state['plan_synthesis']['content']['recommendation']='改为先核查耗时，再做配对评测。'
        self.assertNotEqual(contract_hash(self.state),draft_hash)

    def test_only_selected_shared_evidence_enters_request_and_references(self):
        s=GeneralSession.create(self.root/'sessions',backend='offline',workspace=self.root)
        (self.root/'paper.md').write_text('PRIVATE_LOCAL_ONLY\n共享的合成片段，只有方法描述。\nUNSELECTED_SECRET',encoding='utf-8')
        self.send(s,'/plan research_question: '+GOAL)
        self.send(s,'/plan evidence add '+json.dumps({'path':'paper.md','start_line':1,'end_line':1}))
        self.send(s,'/plan evidence add '+json.dumps({'path':'paper.md','start_line':2,'end_line':2,'share_with_model':True}))
        s.meta['backend']='api';s._provider=NativePlans()
        self.send(s,'/plan synthesize')
        request=json.dumps(s._provider.calls,ensure_ascii=False)
        self.assertNotIn('PRIVATE_LOCAL_ONLY',request);self.assertNotIn('UNSELECTED_SECRET',request)
        self.assertIn('共享的合成片段',request)

    def test_unshared_evidence_cannot_be_cited_as_a_design_basis(self):
        self.provider.response['tool_calls'][0]['arguments']['plan']['references'].append(
            {'source':'evidence','key':'unselected','quote':'伪造论文依据'})
        self.assertEqual(self.generate()['record']['reason'],'UngroundedPlanReference')

    def test_selected_replication_paper_must_be_cited_not_just_attached(self):
        s=GeneralSession.create(self.root/'sessions',backend='offline',workspace=self.root)
        (self.root/'paper.md').write_text('合成方法：同一完整场配对比较甲乙，未知方差。',encoding='utf-8')
        self.send(s,'/plan '+json.dumps({'research_question':'复现所选合成论文中的甲乙配对比较。','objective_type':'replication','resources':'最多2小时'},ensure_ascii=False))
        self.send(s,'/plan evidence add '+json.dumps({'path':'paper.md','start_line':1,'end_line':1,'share_with_model':True}))
        self.state=load(s);self.provider.response=response(self.state)
        self.assertEqual(self.generate()['record']['reason'],'MissingSelectedPaperReference')
        row=self.state['evidence'][0]
        self.provider.response['tool_calls'][0]['arguments']['plan']['references'].append(
            {'source':'evidence','key':row['id'],'quote':'同一完整场配对比较甲乙'})
        self.assertEqual(self.generate()['record']['mode'],'llm')

    def test_negated_execution_and_power_are_allowed_but_invented_quantities_rejected(self):
        content=self.provider.response['tool_calls'][0]['arguments']['plan']
        content['assumptions']=['不保证功效，不自动启动训练；实际条件仍待核实。']
        self.assertEqual(self.generate()['record']['mode'],'llm')
        content['assumptions']=['建议采用八个独立样本即可。']
        self.assertEqual(self.generate()['record']['reason'],'UnsupportedPlanQuantity')

    def test_accepting_displayed_scope_refreshes_draft_and_preserves_unknowns(self):
        s=self.conversation();self.send(s,'/plan '+GOAL)
        state=load(s);state['facts']['scope']=dict(fact('仅限合成二维场。'),status='proposed')
        state['unknown']=['sampling'];save(s,state)
        count=len(s._provider.calls);self.send(s,'/plan accept scope')
        state=load(s)
        self.assertEqual(state['facts']['scope']['status'],'declared')
        self.assertEqual(state['unknown'],['sampling']);self.assertEqual(len(s._provider.calls),count+1)
        self.assertEqual(synthesis.projection(state)['status'],'current')

    def test_validated_draft_approval_and_export_remain_version_bound(self):
        s=GeneralSession.create(self.root/'sessions',backend='offline')
        self.send(s,'/plan '+json.dumps({f:r['value'] for f,r in complete_state()['facts'].items()},ensure_ascii=False))
        s.meta['backend']='api';s._provider=NativePlans();self.send(s,'/plan synthesize')
        state=load(s);self.assertEqual(synthesis.projection(state)['status'],'current')
        identity=contract_hash(state);self.send(s,'/plan approve '+identity)
        self.assertEqual(load(s)['approval']['contract_hash'],identity)
        export_bundle(s);old=load(s)['last_export'];old_bytes=(s.folder/old['json_ref']).read_bytes()
        self.send(s,'/plan revise resources: 最多1小时，超限停止')
        self.assertIsNone(load(s)['approval']);self.assertNotEqual(contract_hash(load(s)),identity)
        self.assertEqual((s.folder/old['json_ref']).read_bytes(),old_bytes)

    def test_invalid_question_keeps_valid_draft_and_template_question(self):
        self.provider.response['tool_calls'][0]['arguments']['questions']=[{
            'field':'scope','kind':'missing','question':'不存在的论文已经证明方案正确吗？',
            'rationale':'使用未经选择的原文说明范围。',
            'references':[{'source':'evidence','key':'missing','quote':'不存在的原文'}]}]
        result=self.generate();self.assertEqual(result['record']['mode'],'llm');self.assertEqual(result['questions'],[])

    def test_html_escapes_design_proposals_with_original_css(self):
        s=self.conversation();self.send(s,'/plan '+GOAL)
        state=load(s);state['plan_synthesis']['content']['steps'][0]['action']='<script>alert("x")</script>核对数据版本'
        from rut_science.science_bot.general.planning.runtime import _plan
        html=delivery_html(_plan(state))
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html)
        self.assertIn('实验对比',html);self.assertIn('设计建议',html)

    def test_legacy_exports_without_synthesis_keep_original_json_shape_and_remain_readable(self):
        s=GeneralSession.create(self.root/'sessions',backend='offline')
        self.send(s,'/plan '+json.dumps({f:r['value'] for f,r in complete_state()['facts'].items()},ensure_ascii=False))
        bundle=export_bundle(s);before=bundle['json'].read_bytes()
        original=json.loads(before)
        self.assertNotIn('plan_synthesis',original);self.assertNotIn('experiment_steps',original)
        self.send(s,'/plan revise resources: 最多1小时，超限停止')
        _,old,_=export_plan(s);self.assertEqual(old,original)
        self.assertEqual(bundle['json'].read_bytes(),before)


if __name__=='__main__':unittest.main()
