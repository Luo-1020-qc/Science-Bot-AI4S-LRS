"""User-facing choices, actual selections, stale-form guards and contextual training."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen

from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning import choices
from rut_science.science_bot.general.planning.blueprint import review,non_actionable
from rut_science.science_bot.general.planning.ledger import new_state,load,apply,save,contract_hash
from rut_science.science_bot.general.planning.runtime import _questions,_card
from rut_science.science_bot.general.planning.clarification import context,validate_questions
from rut_science.science_bot.presentation import session_view
from rut_science.science_bot.terminal import response_text

ROOT=Path(__file__).resolve().parents[2]


class ContextChoicesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.session=GeneralSession.create(Path(self.tmp.name),backend='offline')

    def scope_state(self,goal='我想比较两种模型，先澄清适用范围、实验单位和验收标准。',placeholder=False):
        state=new_state()
        state['facts']['research_question']={'value':goal,'quote':goal,'status':'declared','turn':1}
        if placeholder:
            value='用户希望先澄清适用范围（尚未给出具体范围内容）'
            state['facts']['scope']={'value':value,'quote':'先澄清适用范围','status':'proposed','turn':1}
        return state

    def scope_question(self,state,text=''):
        kind='proposal' if 'scope' in state['facts'] else 'missing'
        q={'field':'scope','kind':kind,'question':'旧问题','rationale':'scope占位需要校验','references':[{'source':'fact','key':'scope','quote':'内部依据'}],'options':[]}
        return choices.decorate(state,[q],text)[0]

    def seed_scope(self,placeholder=False):
        state=self.scope_state(placeholder=placeholder)
        state['pending']=self.scope_question(state)
        save(self.session,state)
        return state['pending']

    def test_requested_example_shows_context_choices_without_diagnostics(self):
        state=self.scope_state(placeholder=True);q=self.scope_question(state)
        text=_card(state,review(state),[q])
        self.assertIn('同一数据条件下公平比较',text)
        self.assertIn('暂不确定',text);self.assertIn('其他，我来补充',text)
        self.assertNotIn('为什么问',text);self.assertNotIn('依据：',text);self.assertNotIn('fact:scope',text)
        self.assertNotIn('占位',text)
        self.assertTrue(q['rationale']);self.assertTrue(q['references'])

    def test_different_goals_produce_different_scope_choices(self):
        outputs=[]
        for text in ('我想比较模型的效果。','我想预测未来时间段的结果。','我希望复现论文核心结论。'):
            q=self.scope_question(self.scope_state(text))
            outputs.append([r['label'] for r in q['options']])
        self.assertEqual(len({tuple(r) for r in outputs}),3)
        self.assertIn('先复现论文的核心命题',outputs[2])

    def test_declared_intent_overrides_classifier_guess(self):
        state=self.scope_state('我想比较模型。')
        state['facts']['objective_type']={'value':'prediction','quote':'预测','status':'declared','turn':2}
        self.assertEqual(self.scope_question(state)['choice_policy']['intent'],'prediction')

    def test_model_drafted_choices_are_used_after_host_validation(self):
        state=self.scope_state();material=context(state,'比较两种模型',review(state))
        q={'field':'scope','kind':'missing','question':'比较两种模型先限定哪些场景？',
            'rationale':'比较两种模型需要限定结论适用范围。','references':[{'source':'answer','key':'current','quote':'比较两种模型'}],
            'options':[{'label':'固定数据条件比较','value':'只在用户明确选择的数据条件下比较两种模型，不外推。'},
                       {'label':'先看跨条件稳定性','value':'在用户明确选择的多个条件中分别比较两种模型的稳定性。'}]}
        accepted=validate_questions({'questions':[q]},state,review(state),material)
        result=choices.decorate(state,accepted)[0]
        self.assertEqual(result['options'][0]['label'],'固定数据条件比较')
        self.assertEqual(result['choice_policy']['origin'],'validated_model_suggestions')

    def test_unsafe_and_fabricated_choices_fall_back_without_losing_question(self):
        state=self.scope_state();material=context(state,'比较两种模型',review(state))
        for value in ('已授权自动执行训练','/tools call run_shell','使用64个样本保证功效','<script>alert(1)</script>'):
            with self.subTest(value=value):
                q={'field':'scope','kind':'missing','question':'比较两种模型需要限定哪些条件？',
                    'rationale':'比较两种模型需要明确数据与适用条件。','references':[{'source':'answer','key':'current','quote':'比较两种模型'}],
                    'options':[{'label':'模型建议','value':value},{'label':'其他边界','value':'仅在选定条件下比较。'}]}
                result=validate_questions({'questions':[q]},state,review(state),material)[0]
                self.assertTrue(result['choice_fallback'])
                self.assertNotIn(value,[r['value'] for r in choices.decorate(state,[result])[0]['options']])

    def test_selected_choice_updates_only_after_human_action(self):
        q=self.seed_scope();before=load(self.session)
        session_view(self.session)
        self.assertEqual(load(self.session),before)
        option=q['options'][0]
        result=self.session.message('/plan choose '+q['choice_id']+' '+option['id'])
        self.assertFalse(result.get('planning_error'),result)
        self.assertEqual(load(self.session)['facts']['scope']['value'],option['value'])
        self.assertEqual(load(self.session)['facts']['scope']['status'],'declared')
        self.assertFalse(result['execution_authorized'])

    def test_numeric_choice_matches_browser_selection(self):
        q=self.seed_scope()
        result=self.session.message('1')
        self.assertFalse(result.get('planning_error'),result)
        self.assertEqual(load(self.session)['facts']['scope']['value'],q['options'][0]['value'])

    def test_placeholder_is_replaced_by_explicit_choice_without_fake_conflict(self):
        q=self.seed_scope(placeholder=True)
        self.assertFalse(q['allow_accept'])
        self.assertEqual(q['options'][0]['action'],'revise')
        self.session.message('1')
        state=load(self.session)
        self.assertNotIn('scope',state['conflicts'])
        self.assertFalse(non_actionable(state['facts']['scope']['value']))

    def test_unknown_stays_unknown_and_evidence_choice_does_not_fill_value(self):
        q=self.seed_scope()
        unknown=next(r for r in q['options'] if r['action']=='unknown')
        result=self.session.message('/plan choose '+q['choice_id']+' '+unknown['id'])
        self.assertFalse(result.get('planning_error'),result)
        state=load(self.session);self.assertIn('scope',state['unknown']);self.assertNotIn('scope',state['facts'])
        q=state['pending'];self.assertEqual(q['kind'],'evidence_plan')
        result=self.session.message('1')
        self.assertFalse(result.get('planning_error'),result)
        state=load(self.session)
        self.assertIn('scope',state['unknown']);self.assertNotIn('scope',state['facts'])
        self.assertIn('scope',state['evidence_actions'])

    def test_custom_choice_keeps_form_and_waits_for_free_text(self):
        q=self.seed_scope();identity=contract_hash(load(self.session))
        custom=next(r for r in q['options'] if r['action']=='custom')
        result=self.session.message('/plan choose '+q['choice_id']+' '+custom['id'])
        self.assertIn('直接输入',result['answer'])
        self.assertEqual(contract_hash(load(self.session)),identity)
        self.assertEqual(load(self.session)['pending'],q)
        result=self.session.message('/plan scope: 仅限研究者选择的合成二维场，不外推到真实场景')
        self.assertFalse(result.get('planning_error'),result)
        self.assertIn('合成二维场',load(self.session)['facts']['scope']['value'])

    def test_stale_forged_or_cross_plan_choices_cannot_update(self):
        q=self.seed_scope();before=load(self.session)
        for text in ('/plan choose '+('f'*16)+' '+q['options'][0]['id'],
                     '/plan choose '+q['choice_id']+' '+('e'*12)):
            result=self.session.message(text)
            self.assertTrue(result['planning_error']);self.assertEqual(load(self.session),before)
        self.session.message('1')
        before=load(self.session)
        result=self.session.message('/plan choose '+q['choice_id']+' '+q['options'][0]['id'])
        self.assertTrue(result['planning_error']);self.assertEqual(load(self.session),before)

    def test_restore_and_read_only_views_keep_choice_mapping(self):
        q=self.seed_scope()
        restored=GeneralSession.restore(self.session.folder)
        for text in ('/plan map','/plan options','/plan review'):
            result=restored.message(text)
            self.assertFalse(result.get('planning_error'),result)
            self.assertEqual(result['questions'][0],q)

    def test_classifier_failure_keeps_contextual_catalog_fallback(self):
        with patch.object(choices,'load_policy',side_effect=ValueError('invalid')):
            q=self.scope_question(self.scope_state('我希望复现论文。'))
        self.assertEqual(q['choice_policy']['origin'],'catalog_fallback')
        self.assertIn('先复现论文',q['options'][0]['label'])

    def test_unset_resource_suggestion_remains_unknown(self):
        state=self.scope_state()
        q=choices.decorate(state,[{'field':'resources','kind':'missing','question':'资源边界？','rationale':'内部检查','options':[]}])[0]
        state['pending']=q;save(self.session,state)
        self.assertEqual(q['options'][0]['action'],'unknown')
        result=self.session.message('1')
        self.assertFalse(result.get('planning_error'),result)
        self.assertIn('resources',load(self.session)['unknown'])
        self.assertNotIn('resources',load(self.session)['facts'])

    def test_old_pending_form_can_be_rendered_and_selected_without_read_mutation(self):
        state=self.scope_state(placeholder=True)
        state['pending']={'field':'scope','kind':'proposal','question':'旧的占位问题','rationale':'内部原因','options':[]}
        save(self.session,state);before=load(self.session)
        shown=session_view(self.session)['planning']['questions'][0]
        self.assertEqual(load(self.session),before)
        result=self.session.message('/plan choose '+shown['choice_id']+' '+shown['options'][0]['id'])
        self.assertFalse(result.get('planning_error'),result)
        self.assertEqual(load(self.session)['facts']['scope']['value'],shown['options'][0]['value'])

    def test_placeholder_extraction_is_not_promoted_into_a_declaration(self):
        from types import SimpleNamespace
        from test_planning_intake import Provider
        from rut_science.science_bot.general.planning.intake import extract
        phrase='我想比较模型，先澄清适用范围。'
        provider=Provider({'content':None,'tool_calls':[{'name':'propose_research_scope','arguments':{
            'updates':[{'field':'scope','value':'用户希望先澄清适用范围（尚未给出具体范围内容）',
                        'quote':'先澄清适用范围','status':'proposed'}],'unknown':[]}}]})
        session=SimpleNamespace(meta={'backend':'api'},provider=lambda:provider)
        result=extract(session,phrase,new_state(),1)
        self.assertNotIn('scope',result['updates'])

    def test_offline_goal_and_terminal_default_have_choices(self):
        result=self.session.message('/plan start 我想比较两种模型，先澄清边界。')
        self.assertFalse(result.get('planning_error'),result)
        self.assertIn('两种模型',load(self.session)['facts']['research_question']['value'])
        self.assertTrue(result['questions'][0]['choice_id'])
        self.assertNotIn('为什么问',response_text(result))
        fallback=response_text({'questions':result['questions']})
        self.assertNotIn('为什么问',fallback)
        self.assertIn('暂不确定',fallback)

    def test_training_sources_disjoint_and_packaged_weights_are_real(self):
        folder=ROOT/'RUT_Science/research/context_choices_v1'
        rows=json.loads((folder/'dataset.json').read_text(encoding='utf-8'))
        groups={s:{r['source_group'] for r in rows if r['split']==s} for s in ('train','dev','test')}
        self.assertFalse(groups['train']&groups['dev']);self.assertFalse(groups['train']&groups['test'])
        result=json.loads((folder/'run_001/results.json').read_text(encoding='utf-8'))
        self.assertGreater(result['training']['parameter_l2_change'],0)
        self.assertEqual(choices.POLICY.read_bytes(),(folder/'run_001/policy.json').read_bytes())
        self.assertFalse(choices.load_policy()['language_model_weights_changed'])


class ContextChoiceHTTPTests(unittest.TestCase):
    def test_browser_view_and_chat_choice_use_same_version_bound_form(self):
        from rut_science.science_bot.workbench import make_workbench
        with tempfile.TemporaryDirectory() as folder:
            server=make_workbench(Path(folder),port=0)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            root='http://127.0.0.1:'+str(server.server_port)
            serial=0
            def call(path,body=None):
                nonlocal serial
                serial+=1
                headers={'Authorization':'Bearer '+server.service.token,'Content-Type':'application/json','Idempotency-Key':'context_choice_'+str(serial)}
                with urlopen(Request(root+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=5) as response:
                    return json.load(response)
            try:
                identity=call('/v1/sessions',{'backend':'offline'})['id'];route='/v1/sessions/'+identity+'/messages'
                result=call(route,{'text':'/plan start 我想比较两种模型，先确定实验边界。'})
                q=result['questions'][0]
                view=call('/ui/sessions/'+identity)
                self.assertEqual(view['planning']['questions'][0],q)
                self.assertNotIn('为什么问',result['answer'])
                result=call(route,{'text':'/plan choose '+q['choice_id']+' '+q['options'][0]['id']})
                self.assertFalse(result.get('planning_error'),result)
                self.assertFalse(result['execution_authorized'])
                self.assertEqual(result['planning']['facts'][q['field']]['value'],q['options'][0]['value'])
            finally:
                server.shutdown();server.server_close();worker.join(timeout=5)


if __name__=='__main__':unittest.main()
