"""Whole-document extraction, lossless batching and grounded downstream plans."""
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader,PdfWriter
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.evidence import select,validate_sources
from rut_science.science_bot.general.planning.ledger import load,save
from rut_science.science_bot.general.planning import synthesis
from rut_science.science_bot.general.planning.paper_context import chunks,coverage,model_text,CHUNK_BYTES
from rut_science.science_bot.general.planning.paper_reading import understand,validate_reading
from rut_science.science_bot.general.provider import GeneralProvider,OutputTruncatedError,output_tokens
from rut_science.science_bot.presentation import export_bundle
from test_general_provider import envelope,native_call,CONFIG,MESSAGES,TOOLS
from test_plan_synthesis import NativePlans,GOAL,fixture

ROOT=Path(__file__).resolve().parents[2]


class ChunkProvider:
    def __init__(self,fail_at=None):self.calls=[];self.fail_at=fail_at
    def complete(self,messages,tools=None,role=None):
        self.calls.append({'messages':deepcopy(messages),'role':role})
        if self.fail_at==len(self.calls):raise OutputTruncatedError('output length limit')
        pages=json.loads(messages[-1]['content'])['selected_pdf_pages']
        return {'content':None,'tool_calls':[{'name':'interpret_selected_paper','arguments':{
            'items':[{'category':'methods','statement':'该页保留模型比较的原文依据，解释仍需复核。',
                      'page':p['page'],'quote':p['text'][:160]} for p in pages if p['text'].strip()],
            'unanswered':['尚需核实真实数据与方差。']}}]}
    def mark_validation(self,*args):pass


class FullPDFTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.local');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);reader=PdfReader(ROOT/'examples/papers/synthetic_paper.pdf');writer=PdfWriter()
        for index in range(31):writer.add_page(reader.pages[index%2])
        with (self.root/'paper.pdf').open('wb') as stream:writer.write(stream)
        self.session=GeneralSession.create(self.root/'sessions',backend='offline',workspace=self.root)

    def source(self,shared=True):
        result=self.session.message('/plan evidence add '+json.dumps({'path':'paper.pdf','share_with_model':shared}))
        self.assertFalse(result.get('planning_error'),result)
        return load(self.session)['evidence'][0]

    def api(self,provider):self.session.meta['backend']='api';self.session._provider=provider

    def test_all_31_pages_and_full_text_beyond_old_caps_survive_restore(self):
        row=self.source(False);self.assertEqual(len(row['pages']),31);self.assertEqual(row['end_page'],31)
        self.assertGreater(len(row['text'].encode()),18000);self.assertIn('[PDF page 31]',row['text'])
        validate_sources([row]);(self.root/'paper.pdf').unlink()
        restored=GeneralSession.restore(self.session.folder)
        self.assertEqual(load(restored)['evidence'][0],row)
        for name in ('html','markdown'):
            self.assertIn('PDF page 31',export_bundle(restored)[name].read_text(encoding='utf-8'))

    def test_explicit_range_and_start_to_end_still_work(self):
        row=select(self.session,{'path':'paper.pdf','start_page':13},1)
        self.assertEqual([r['page'] for r in row['pages']],list(range(13,32)))
        row=select(self.session,{'path':'paper.pdf','start_page':12,'end_page':14},1)
        self.assertEqual([r['page'] for r in row['pages']],[12,13,14])

    def test_chunks_cover_all_original_characters_including_oversized_unicode_page(self):
        source={'pages':[{'page':1,'text':'甲乙科研。'*18000},{'page':2,'text':''},{'page':3,'text':'final section'}]}
        batches=chunks(source)
        for batch in batches:
            self.assertLessEqual(sum(len(p['text'].encode()) for p in batch),CHUNK_BYTES)
        for page in source['pages']:
            self.assertEqual(''.join(p['text'] for batch in batches for p in batch if p['page']==page['page']),page['text'])

    def test_all_pages_sent_once_with_grounded_last_page_and_cached_result(self):
        row=self.source();provider=ChunkProvider();self.api(provider)
        out=self.session.message('/plan evidence understand '+row['id']);self.assertFalse(out.get('planning_error'),out)
        reading=load(self.session)['evidence'][0]['interpretation'];validate_reading(reading,row)
        sent=[p for c in provider.calls for p in json.loads(c['messages'][-1]['content'])['selected_pdf_pages']]
        self.assertEqual(sent,row['pages']);self.assertEqual(reading['coverage']['completed_chunks'],4)
        self.assertIn(31,[i['page'] for i in reading['items']]);before=len(provider.calls)
        self.session.message('/plan evidence understand '+row['id']);self.assertEqual(len(provider.calls),before)
        self.assertEqual(load(self.session)['facts'],{})

    def test_failed_later_chunk_keeps_explicit_partial_coverage_and_resumes(self):
        row=self.source();provider=ChunkProvider(fail_at=2);self.api(provider)
        out=self.session.message('/plan evidence understand '+row['id']);self.assertFalse(out.get('planning_error'),out)
        partial=load(self.session)['evidence'][0];self.assertEqual(partial['interpretation']['coverage']['completed_chunks'],1)
        self.assertEqual(model_text(partial),'');self.assertIn('尚未完成',out['answer'])
        provider.fail_at=None;self.session.message('/plan evidence understand '+row['id'])
        row=load(self.session)['evidence'][0];self.assertEqual(row['interpretation']['coverage']['completed_chunks'],4)
        self.assertEqual(len(provider.calls),5)
        resumed=json.loads(provider.calls[2]['messages'][-1]['content'])['selected_pdf_pages']
        self.assertEqual(resumed[0]['page'],9)

    def test_private_full_paper_never_calls_model(self):
        row=self.source(False);provider=ChunkProvider();self.api(provider)
        with self.assertRaises(ValueError):understand(self.session,row,2)
        self.assertEqual(provider.calls,[])

    def test_coverage_tampering_cannot_claim_complete_reading(self):
        row=self.source();self.api(ChunkProvider());reading=understand(self.session,row,2)
        reading['coverage']['chunk_sha256'][-1]='0'*64
        with self.assertRaises(ValueError):validate_reading(reading,row)

    def test_grounded_full_reading_invalidates_cached_fallback_and_can_generate_plan(self):
        self.session.message('/plan research_question: '+GOAL);row=self.source()
        self.api(NativePlans());out=self.session.message('/plan synthesize')
        self.assertEqual(out['planning']['plan_synthesis']['reason'],'paper_reading_required')
        old_basis=load(self.session)['plan_synthesis']['basis_hash']
        self.api(ChunkProvider());self.session.message('/plan evidence understand '+row['id'])
        self.api(NativePlans());out=self.session.message('/plan synthesize')
        self.assertFalse(out.get('planning_error'),out)
        current=load(self.session);self.assertEqual(synthesis.projection(current)['status'],'current')
        self.assertNotEqual(old_basis,current['plan_synthesis']['basis_hash'])
        data=json.loads(self.session._provider.calls[-1]['messages'][-1]['content'])
        evidence=next(r for r in data['sources'] if r['source']=='evidence')
        self.assertIn('PDF page 31',evidence['text']);self.assertIn('not the entire paper',evidence['representation'])

    def test_blank_physical_page_preserves_numbering(self):
        reader=PdfReader(self.root/'paper.pdf');writer=PdfWriter()
        writer.add_page(reader.pages[0]);writer.add_blank_page(width=600,height=800);writer.add_page(reader.pages[1])
        with (self.root/'paper.pdf').open('wb') as stream:writer.write(stream)
        row=self.source();self.assertEqual(row['pages'][1],{'page':2,'text':''});validate_sources([row])

    def test_plan_citations_align_whitespace_and_cannot_join_disjoint_excerpts(self):
        self.session.message('/plan research_question: '+GOAL);row=self.source();state=load(self.session)
        data={'sources':[{'source':'fact','key':'research_question','text':GOAL},
                         {'source':'evidence','key':row['id'],'text':row['text']}]}
        plan=fixture(state);quote='Both models evaluate the same 8 independent synthetic fields, with paired comparisons by field.'
        plan['references'].append({'source':'evidence','key':row['id'],'quote':quote})
        normalized=synthesis.validate_content(plan,state,data)
        self.assertIn('\n',normalized['references'][-1]['quote'])
        self.assertIn(normalized['references'][-1]['quote'],row['text'])
        self.assertEqual(plan['references'][-1]['quote'],quote)
        invented_join='Engineering fixture - synthetic paper\n\nA sample-size or power'
        data['sources'][-1]['text']=invented_join;plan['references'][-1]['quote']=invented_join
        with self.assertRaisesRegex(ValueError,'UngroundedPlanReference'):synthesis.validate_content(plan,state,data)

    def test_explicit_small_read_budget_is_respected(self):
        self.session.limits['read_bytes']=100
        with self.assertRaises(ValueError):select(self.session,{'path':'paper.pdf'},1)


class PDFOutputPolicyTests(unittest.TestCase):
    def test_document_only_redundant_closer_normalization_keeps_other_json_strict(self):
        from rut_science.science_bot.general.planning.paper_reading import READ_SPEC
        tools=[READ_SPEC.provider_schema()]
        good='{"items":[],"unanswered":[]}'
        invalid=[good+'}}',good+' {}','{"items":[],"items":[],"unanswered":[]}}',good[:-1]]
        def reply(arguments):
            call=native_call(arguments=arguments);call['function']['name']='interpret_selected_paper'
            return io.BytesIO(json.dumps(envelope(None,[call])).encode())
        with tempfile.TemporaryDirectory() as folder,patch('rut_science.science_bot.general.provider.load_api_config',return_value=CONFIG):
            provider=GeneralProvider(folder,max_tokens=300000)
            with patch('rut_science.science_bot.general.provider.urllib.request.urlopen',return_value=reply(good+'}')):
                result=provider.complete(MESSAGES,tools,role='paper_reading')
            self.assertEqual(result['tool_calls'][0]['arguments'],json.loads(good))
            saved=json.loads((Path(folder)/'model_calls/0001_request.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['argument_normalizations'][0]['type'],'removed_one_redundant_final_brace')
            for value in invalid:
                with patch('rut_science.science_bot.general.provider.urllib.request.urlopen',return_value=reply(value)):
                    with self.assertRaises(ValueError):provider.complete(MESSAGES,tools,role='paper_reading')
            with patch('rut_science.science_bot.general.provider.urllib.request.urlopen',return_value=reply(good+'}')):
                with self.assertRaises(ValueError):provider.complete(MESSAGES,tools,role='general')

    def test_task_specific_output_limits_and_user_override(self):
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(output_tokens('general'),1800)
            self.assertEqual(output_tokens('paper_reading'),8192)
            self.assertEqual(output_tokens('planning_synthesis'),8192)
        with patch.dict('os.environ',{'SCIENCE_BOT_PLAN_OUTPUT_TOKENS':'12000'}):
            self.assertEqual(output_tokens('planning_synthesis'),12000)
        with patch.dict('os.environ',{'SCIENCE_BOT_PAPER_OUTPUT_TOKENS':'0'}):
            with self.assertRaises(ValueError):output_tokens('paper_reading')

    def test_truncation_is_typed_before_json_parsing_and_usage_is_accounted(self):
        response=envelope(None,[native_call(arguments='{"broken":')],finish_reason='length')
        with tempfile.TemporaryDirectory() as folder,patch('rut_science.science_bot.general.provider.load_api_config',return_value=CONFIG):
            provider=GeneralProvider(folder)
            with patch('rut_science.science_bot.general.provider.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as request:
                with self.assertRaisesRegex(OutputTruncatedError,'长度上限'):
                    provider.complete(MESSAGES,TOOLS,role='planning_synthesis')
            self.assertEqual(json.loads(request.call_args.args[0].data)['max_tokens'],8192)
            self.assertEqual(provider.snapshot()['accounted_tokens'],150)
            self.assertEqual(provider.snapshot()['requests'],1)


if __name__=='__main__':unittest.main()
