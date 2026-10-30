"""Research planning reuses authenticated message/status/report endpoints."""
import unittest
from unittest.mock import patch
import test_general_http as helpers


class ResearchPlanningHTTPTests(unittest.TestCase):
    setUp=helpers.GeneralHTTPTests.setUp
    tearDown=helpers.GeneralHTTPTests.tearDown
    request=helpers.GeneralHTTPTests.request
    create=helpers.GeneralHTTPTests.create

    def test_existing_endpoint_idempotency_restore_and_report(self):
        created=self.create(backend='offline');identity=created['id']
        body={'text':'/plan research_question: 比较声明数据范围内的模型误差并决定下一步'}
        status,first=self.request(f'/{identity}/messages',body,'plan1')
        self.assertEqual(status,200,first);self.assertEqual(first['intent'],'planning')
        status,repeated=self.request(f'/{identity}/messages',body,'plan1')
        self.assertEqual(first,repeated)
        self.server.service.sessions.clear()
        status,current=self.request(f'/{identity}')
        self.assertEqual(status,200,current)
        self.assertEqual(current['planning']['revision'],first['planning']['revision'])
        self.assertEqual(current['resources']['tool_attempts'],0)
        status,report=self.request(f'/{identity}/report')
        self.assertEqual(status,200,report)
        self.assertEqual(report['kind'],'research_planning_contract')
        self.assertFalse(report['execution_authorized'])

    def test_planning_cannot_confirm_or_resume_real_experiment(self):
        created=self.create(backend='offline');identity=created['id']
        self.request(f'/{identity}/messages',{'text':'/plan'},'plan-start')
        status,result=self.request(f'/{identity}/confirm',{'draft_hash':'not-execution'},'confirm-plan')
        self.assertEqual(status,409,result)
        status,result=self.request(f'/{identity}/resume',{},'resume-plan')
        self.assertEqual(status,409,result)
        _,current=self.request(f'/{identity}')
        self.assertIsNone(current['spec']);self.assertFalse(current['confirmed'])

    def test_native_semantic_understanding_stays_same_http_provider(self):
        self.api=helpers.GeneralHTTPTests.api.__get__(self)
        text='我想比较CViT与FNO在声明数据上的误差'
        import json
        response={'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[
            {'id':'scope1','type':'function','function':{'name':'propose_research_scope','arguments':json.dumps(
                {'updates':[{'field':'research_question','value':text,'quote':text,'status':'declared'}],'unknown':[]},ensure_ascii=False)}}]}}],
            'usage':{'prompt_tokens':30,'completion_tokens':30}}
        clarification={'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[
            {'id':'question1','type':'function','function':{'name':'propose_clarification_questions','arguments':json.dumps(
                {'questions':[{'field':'scope','kind':'missing','question':'CViT与FNO的误差比较要限定在哪些数据条件？',
                  'rationale':'当前只提出比较CViT与FNO，需先界定结论适用范围。',
                  'references':[{'source':'answer','key':'current','quote':'比较CViT与FNO'}]}]},ensure_ascii=False)}}]}}],
            'usage':{'prompt_tokens':30,'completion_tokens':30}}
        with self.api(response,clarification) as (network,bodies):
            created=self.create(backend='api');identity=created['id']
            status,result=self.request(f'/{identity}/messages',{'text':text},'semantic-planning')
            self.assertEqual(status,200,result)
            self.assertTrue(result['model_used'])
            self.assertEqual(network.call_count,2)
            self.assertEqual(bodies[0]['tools'][0]['function']['name'],'propose_research_scope')
            self.assertEqual(bodies[1]['tools'][0]['function']['name'],'propose_clarification_questions')
            self.assertEqual(result['clarification']['mode'],'dynamic')
            self.assertEqual(result['planning']['facts']['research_question']['value'],text)
            _,current=self.request(f'/{identity}')
            self.assertEqual(current['resources']['llm_requests'],2)
            self.assertEqual(current['resources']['tool_attempts'],0)


if __name__=='__main__':unittest.main()
