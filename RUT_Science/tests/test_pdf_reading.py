"""Real PDF parsing, grounded native-call interpretation, persistence and privacy."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.evidence import select,citation,validate_sources
from rut_science.science_bot.general.planning.ledger import load,contract_hash,save
from rut_science.science_bot.general.planning.paper_reading import validate_reading
from rut_science.science_bot.presentation import session_view,export_bundle
import test_workbench_http as http_fixture

ROOT=Path(__file__).resolve().parents[2]


class Provider:
    def __init__(self,args):self.args=args;self.calls=[];self.marks=[]
    def complete(self,messages,tools=None,role=None):
        self.calls.append({'messages':messages,'role':role,'tools':tools})
        return {'content':None,'tool_calls':[{'name':'interpret_selected_paper','arguments':deepcopy(self.args)}]}
    def mark_validation(self,*args):self.marks.append(args)


class PDFReadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.local');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();shutil.copyfile(ROOT/'examples/papers/synthetic_paper.pdf',self.root/'paper.pdf')
        self.session=GeneralSession.create(self.root/'sessions',backend='offline',workspace=self.root)

    def add(self,share=False,start=1,end=2):
        result=self.session.message('/plan evidence add '+json.dumps({'path':'paper.pdf','start_page':start,'end_page':end,'share_with_model':share}))
        self.assertFalse(result.get('planning_error'),result);return load(self.session)['evidence'][0]

    def provider(self,row,bad=None):
        text=row['pages'][0]['text'];quote=text[text.index('Both models'):text.index('Training,')].strip()
        args={'items':[{'category':'methods','statement':'以独立场为单位进行配对比较，网格点不是独立实验单位。','page':1,'quote':quote}],
              'unanswered':['所选页未给出实测方差和置信区间。']}
        if bad:args['items'][0].update(bad)
        provider=Provider(args);self.session.meta['backend']='api';self.session._provider=provider
        return provider

    def test_real_page_extraction_and_physical_page_citations(self):
        row=self.add();self.assertEqual(row['page_count'],2);self.assertEqual([p['page'] for p in row['pages']],[1,2])
        self.assertIn('8 independent synthetic',row['text']);self.assertIn('0.12',row['pages'][1]['text'])
        self.assertIn(':P1-P2#',citation(row));self.assertFalse(row['share_with_model']);validate_sources([row])

    def test_only_selected_pages_and_no_source_reread_on_restore(self):
        row=self.add(start=1,end=1);self.assertNotIn('Illustrative mean relative errors',row['text'])
        (self.root/'paper.pdf').write_bytes(b'changed source')
        restored=GeneralSession.restore(self.session.folder)
        out=restored.message('/plan evidence show '+row['id'])
        self.assertIn('Both models',out['answer']);self.assertNotIn('changed source',out['answer'])

    def test_pdf_schema_requires_explicit_pages_and_valid_range(self):
        for args in [{'path':'paper.pdf','start_line':1,'end_line':3},
                     {'path':'paper.pdf','start_page':0,'end_page':2},
                     {'path':'paper.pdf','start_page':1,'end_page':13},
                     {'path':'paper.pdf','start_page':1,'end_page':3}]:
            with self.subTest(args=args),self.assertRaises(ValueError):select(self.session,args,1)

    def test_workspace_and_sensitive_file_policies_are_reused(self):
        args={'path':'paper.pdf','start_page':1,'end_page':1}
        self.session.workspace=None
        with self.assertRaises(ValueError):select(self.session,args,1)
        self.session=GeneralSession.restore(self.session.folder)
        shutil.copyfile(self.root/'paper.pdf',self.root/'.env.pdf')
        for path in ['../paper.pdf','.env.pdf']:
            with self.assertRaises(ValueError):select(self.session,{**args,'path':path},1)

    def test_share_required_before_any_llm_call(self):
        row=self.add();provider=self.provider(row)
        out=self.session.message('/plan evidence understand '+row['id'])
        self.assertTrue(out['planning_error']);self.assertEqual(provider.calls,[])
        self.assertNotIn('interpretation',load(self.session)['evidence'][0])

    def test_one_llm_call_cached_interpretation_and_no_automatic_facts(self):
        row=self.add(share=True);before=deepcopy(load(self.session)['facts']);provider=self.provider(row)
        out=self.session.message('/plan evidence understand '+row['id'])
        self.assertFalse(out.get('planning_error'),out);self.assertEqual(len(provider.calls),1)
        self.assertEqual(provider.calls[0]['role'],'paper_reading');self.assertIn('PDF第1页',out['answer'])
        self.assertEqual(load(self.session)['facts'],before)
        self.assertEqual(load(self.session)['evidence'][0]['interpretation']['status'],'model_interpretation_not_verified')
        self.session.message('/plan evidence understand '+row['id']);self.assertEqual(len(provider.calls),1)

    def test_fabricated_quote_page_and_numbers_are_rejected_atomically(self):
        for bad in [{'quote':'this quotation does not appear anywhere'}, {'page':99}, {'statement':'实验使用128个样本。'}]:
            row=self.add(share=True);provider=self.provider(row,bad);before=load(self.session)
            out=self.session.message('/plan evidence understand '+row['id'])
            self.assertTrue(out['planning_error']);self.assertEqual(load(self.session),before)
            self.assertTrue(any(m[0]=='rejected' for m in provider.marks));self.session.meta['backend']='offline'

    def test_whitespace_alignment_keeps_original_quotes_and_filters_only_bad_points(self):
        row=self.add(share=True);provider=self.provider(row)
        provider.args['items'][0]['quote']=' '.join(provider.args['items'][0]['quote'].split())
        bad=deepcopy(provider.args['items'][0]);bad['statement']='本实验使用128个样本。'
        provider.args['items'].append(bad)
        out=self.session.message('/plan evidence understand '+row['id'])
        self.assertFalse(out.get('planning_error'),out)
        reading=load(self.session)['evidence'][0]['interpretation']
        self.assertEqual(len(reading['items']),1);self.assertEqual(len(reading['rejected_items']),1)
        self.assertIn(reading['items'][0]['quote'],row['pages'][0]['text'])
        self.assertNotIn('128',out['answer']);self.assertIn(('needs_input',),provider.marks)

    def test_item_schema_error_does_not_discard_other_grounded_points(self):
        row=self.add(share=True);provider=self.provider(row)
        bad=deepcopy(provider.args['items'][0]);bad['category_note']='unregistered field'
        provider.args['items'].append(bad)
        out=self.session.message('/plan evidence understand '+row['id'])
        self.assertFalse(out.get('planning_error'),out)
        reading=load(self.session)['evidence'][0]['interpretation']
        self.assertEqual(len(reading['items']),1);self.assertEqual(len(reading['rejected_items']),1)

    def test_no_network_or_fake_interpretation_in_offline_mode(self):
        row=self.add(share=True)
        with patch.object(self.session,'provider',side_effect=AssertionError('offline must not call')):
            out=self.session.message('/plan evidence understand '+row['id'])
        self.assertTrue(out['planning_error']);self.assertNotIn('interpretation',load(self.session)['evidence'][0])

    def test_tampered_page_snapshot_and_reading_are_rejected(self):
        row=self.add(share=True);bad=deepcopy(row);bad['pages'][0]['text']='forged'
        with self.assertRaises(ValueError):validate_sources([bad])
        self.provider(row);self.session.message('/plan evidence understand '+row['id'])
        row=load(self.session)['evidence'][0];row['interpretation']['source_sha256']='0'*64
        with self.assertRaises(ValueError):validate_sources([row])

    def test_scanned_encrypted_corrupt_and_budget_failures_do_not_mutate_plan(self):
        row=self.add();before=load(self.session)
        writer=PdfWriter();writer.add_blank_page(width=100,height=100)
        for encrypted in [False,True]:
            if encrypted:writer.encrypt('password')
            with (self.root/'paper.pdf').open('wb') as stream:writer.write(stream)
            out=self.session.message('/plan evidence add {"path":"paper.pdf","start_page":1,"end_page":1}')
            self.assertTrue(out['planning_error']);self.assertEqual(load(self.session),before)
        (self.root/'paper.pdf').write_bytes(b'%PDF-1.7\nmalformed')
        self.assertTrue(self.session.message('/plan evidence add {"path":"paper.pdf","start_page":1,"end_page":1}')['planning_error'])
        shutil.copyfile(ROOT/'examples/papers/synthetic_paper.pdf',self.root/'paper.pdf')
        self.session.limits['read_bytes']=10
        self.assertTrue(self.session.message('/plan evidence add {"path":"paper.pdf","start_page":1,"end_page":1}')['planning_error'])

    def test_parser_timeout_is_typed_and_leaves_snapshot_unchanged(self):
        self.add();before=load(self.session)
        with patch('rut_science.science_bot.general.planning.pdf_document.subprocess.run',side_effect=subprocess.TimeoutExpired('parser',20)):
            out=self.session.message('/plan evidence add {"path":"paper.pdf","start_page":1,"end_page":1}')
        self.assertTrue(out['planning_error']);self.assertEqual(load(self.session),before)

    def test_reading_changes_contract_and_is_exported_as_unverified(self):
        row=self.add(share=True);state=load(self.session);identity=contract_hash(state)
        state['approval']={'contract_hash':identity,'scope':'planning_contract_only'};save(self.session,state)
        self.provider(row);self.session.message('/plan evidence understand '+row['id'])
        state=load(self.session);self.assertIsNone(state['approval']);self.assertNotEqual(contract_hash(state),identity)
        restored=GeneralSession.restore(self.session.folder);bundle=export_bundle(restored)
        for key in ('html','markdown'):
            text=bundle[key].read_text(encoding='utf-8');self.assertIn('PDF',text);self.assertIn('模型',text);self.assertIn('配对',text)
        view=session_view(restored);self.assertNotIn('pages',view['planning']['evidence'][0])

    def test_pdf_original_and_interpretation_do_not_enter_ordinary_chat_history(self):
        row=self.add(share=True);self.provider(row);self.session.message('/plan evidence understand '+row['id'])
        history=json.dumps(self.session.meta['messages'],ensure_ascii=False)
        self.assertNotIn('Grid points within',history);self.assertNotIn('以独立场为单位',history)

    def test_understanding_does_not_share_other_selected_or_unselected_pages(self):
        row=self.add(share=True,start=1,end=1);self.add(share=False,start=2,end=2)
        provider=self.provider(row)
        out=self.session.message('/plan evidence understand '+row['id'])
        self.assertFalse(out.get('planning_error'),out)
        sent=json.dumps(provider.calls,ensure_ascii=False)
        self.assertIn('8 independent synthetic',sent)
        self.assertNotIn('Illustrative mean relative errors',sent)


class PDFHTTPTests(unittest.TestCase):
    setUp=http_fixture.WorkbenchHTTPTests.setUp
    tearDown=http_fixture.WorkbenchHTTPTests.tearDown
    call=http_fixture.WorkbenchHTTPTests.call
    json=http_fixture.WorkbenchHTTPTests.json
    provider=PDFReadingTests.provider

    def test_existing_http_route_reads_pdf_and_returns_grounded_interpretation(self):
        root=Path(self.tmp.name).resolve();shutil.copyfile(ROOT/'examples/papers/synthetic_paper.pdf',root/'paper.pdf')
        self.session=GeneralSession.create(self.server.service.folder,backend='offline',workspace=root)
        identity=self.session.meta['id'];self.server.service.sessions[identity]=self.session
        endpoint='/v1/sessions/'+identity+'/messages'
        status,result=self.json(endpoint,{'text':'/plan evidence add {"path":"paper.pdf","start_page":1,"end_page":2,"share_with_model":true}'})
        self.assertEqual(status,200,result);self.assertFalse(result.get('planning_error'))
        row=load(self.session)['evidence'][0];provider=self.provider(row)
        status,result=self.json(endpoint,{'text':'/plan evidence understand '+row['id']})
        self.assertEqual(status,200,result);self.assertFalse(result.get('planning_error'),result)
        _,view=self.json('/ui/sessions/'+identity)
        source=view['planning']['evidence'][0]
        self.assertEqual(source['start_page'],1);self.assertEqual(len(source['interpretation']['items']),1)
        self.assertNotIn('pages',source);self.assertEqual(len(provider.calls),1)


if __name__=='__main__':unittest.main()
