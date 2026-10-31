"""Real binary HTTP uploads and library-backed evidence with no workspace."""
import io
import json
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request,urlopen

from pypdf import PdfReader,PdfWriter
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.evidence import validate_sources
from rut_science.science_bot.general.planning.ledger import load
from rut_science.science_bot.paper_library import root_for,receive,listing
from rut_science.science_bot.presentation import export_bundle
import test_pdf_reading as pdf_fixture
import test_workbench_http as http_fixture

ROOT=Path(__file__).resolve().parents[2]
RAW=(ROOT/'examples/papers/synthetic_paper.pdf').read_bytes()


class PaperUploadTests(unittest.TestCase):
    setUp=http_fixture.WorkbenchHTTPTests.setUp
    tearDown=http_fixture.WorkbenchHTTPTests.tearDown
    call=http_fixture.WorkbenchHTTPTests.call
    json=http_fixture.WorkbenchHTTPTests.json
    provider=pdf_fixture.PDFReadingTests.provider

    def upload(self,raw=RAW,name='研究论文.pdf',key=None,auth=True,extra=None):
        self.serial+=1;headers={'Content-Type':'application/pdf','X-File-Name':quote(name),
                               'Idempotency-Key':key or 'upload_'+str(self.serial)}
        if auth:headers['Authorization']='Bearer '+self.server.service.token
        headers.update(extra or {})
        request=Request(self.url+'/ui/papers',data=raw,headers=headers)
        try:
            with urlopen(request,timeout=15) as response:return response.status,json.loads(response.read())
        except HTTPError as response:return response.code,json.loads(response.read())

    def new(self):
        status,result=self.json('/v1/sessions',{'backend':'offline'});self.assertEqual(status,200,result)
        return result['id']

    def attach(self,identity,paper,share=False,**ranges):
        return self.json('/v1/sessions/'+identity+'/messages',{'text':'/plan evidence add '+json.dumps(
            {'paper_id':paper['id'],'share_with_model':share,**ranges})})

    def test_upload_select_understand_restore_and_export_without_workspace(self):
        identity=self.new();self.session=self.server.service.session(identity)
        self.assertIsNone(self.session.workspace)
        with patch('rut_science.science_bot.general.provider.GeneralProvider.complete',side_effect=AssertionError('upload must stay local')):
            status,uploaded=self.upload();self.assertEqual(status,200,uploaded)
            self.assertFalse(uploaded['shared_with_model'])
            status,result=self.attach(identity,uploaded['paper']);self.assertEqual(status,200,result)
            self.assertFalse(result.get('planning_error'),result)
        row=load(self.session)['evidence'][0];validate_sources([row])
        self.assertEqual(row['original_filename'],'研究论文.pdf');self.assertFalse(row['share_with_model'])
        self.assertEqual(row['page_count'],2);self.assertIsNone(self.session.workspace)
        status,result=self.attach(identity,uploaded['paper'],True);self.assertFalse(result.get('planning_error'),result)
        row=load(self.session)['evidence'][0];self.provider(row)
        status,result=self.json('/v1/sessions/'+identity+'/messages',{'text':'/plan evidence understand '+row['id']})
        self.assertEqual(status,200,result);self.assertFalse(result.get('planning_error'),result)
        restored=GeneralSession.restore(self.session.folder);self.assertIsNone(restored.workspace)
        self.assertEqual(load(restored)['evidence'][0]['original_filename'],'研究论文.pdf')
        bundle=export_bundle(restored);self.assertIn('研究论文.pdf',bundle['html'].read_text(encoding='utf-8'))
        self.assertEqual(load(restored)['facts'],{})

    def test_binary_pdf_larger_than_json_request_cap_is_supported(self):
        reader=PdfReader(io.BytesIO(RAW));writer=PdfWriter()
        for p in reader.pages:writer.add_page(p)
        writer.add_metadata({'/EngineeringUploadPadding':'x'*70000});stream=io.BytesIO();writer.write(stream)
        raw=stream.getvalue();self.assertGreater(len(raw),65536)
        status,result=self.upload(raw,name='large.pdf');self.assertEqual(status,200,result)
        saved=root_for(self.server.service.folder)/(result['paper']['id']+'.pdf')
        self.assertEqual(saved.read_bytes(),raw)

    def test_library_list_is_authenticated_and_upload_is_same_origin(self):
        self.assertEqual(self.json('/ui/papers',auth=False)[0],401)
        self.assertEqual(self.upload(auth=False)[0],401)
        self.assertEqual(self.upload(extra={'Origin':'https://outside.invalid'})[0],403)
        self.assertEqual(self.json('/ui/papers')[1]['papers'],[])

    def test_deduplication_replay_and_conflicting_replay(self):
        status,first=self.upload(key='stable');self.assertEqual(status,200,first)
        status,replay=self.upload(key='stable');self.assertEqual(replay,first)
        status,again=self.upload(name='another.pdf');self.assertEqual(status,200,again);self.assertTrue(again['duplicate'])
        self.assertEqual(first['paper']['id'],again['paper']['id'])
        self.assertEqual(len(self.json('/ui/papers')[1]['papers']),1)
        self.assertEqual(self.upload(raw=RAW+b'\n',key='stable')[0],409)

    def test_bad_name_type_and_malformed_pdf_are_rejected_without_blobs(self):
        for name,raw,extra in [('../escape.pdf',RAW,{}),('note.txt',RAW,{}),('fake.pdf',b'%PDF-1.7\nbroken',{}),
                               ('fake.pdf',b'not a pdf',{}),('type.pdf',RAW,{'Content-Type':'application/json'})]:
            with self.subTest(name=name,extra=extra):self.assertEqual(self.upload(raw,name,extra=extra)[0],409)
        root=root_for(self.server.service.folder)
        self.assertEqual(list(root.glob('*.pdf')),[])
        self.assertEqual(self.json('/ui/papers')[1]['papers'],[])

    def test_encrypted_pdf_is_rejected_but_blank_pdf_can_be_stored_for_later_ocr(self):
        writer=PdfWriter();writer.add_blank_page(width=600,height=800);writer.encrypt('secret')
        stream=io.BytesIO();writer.write(stream);self.assertEqual(self.upload(stream.getvalue())[0],409)
        writer=PdfWriter();writer.add_blank_page(width=600,height=800);stream=io.BytesIO();writer.write(stream)
        status,result=self.upload(stream.getvalue());self.assertEqual(status,200,result)
        identity=self.new();_,attached=self.attach(identity,result['paper'])
        self.assertTrue(attached.get('planning_error'));self.assertIsNone(load(self.server.service.session(identity)))

    def test_uploaded_pdf_can_be_reused_after_deleting_its_first_conversation(self):
        _,uploaded=self.upload();first=self.new();self.attach(first,uploaded['paper'])
        self.assertEqual(self.json('/ui/sessions/'+first+'/delete',{'confirm':first})[0],200)
        self.assertEqual(len(self.json('/ui/papers')[1]['papers']),1)
        second=self.new();_,result=self.attach(second,uploaded['paper'])
        self.assertFalse(result.get('planning_error'),result)
        self.assertEqual(load(self.server.service.session(second))['evidence'][0]['library_id'],uploaded['paper']['id'])

    def test_unknown_id_mixed_paths_and_file_tampering_leave_evidence_unchanged(self):
        identity=self.new();session=self.server.service.session(identity)
        _,result=self.attach(identity,{'id':'f'*64});self.assertTrue(result.get('planning_error'))
        _,uploaded=self.upload();self.attach(identity,uploaded['paper']);before=load(session)
        body={'paper_id':uploaded['paper']['id'],'path':'outside.pdf'}
        _,result=self.json('/v1/sessions/'+identity+'/messages',{'text':'/plan evidence add '+json.dumps(body)})
        self.assertTrue(result.get('planning_error'));self.assertEqual(load(session),before)
        target=root_for(self.server.service.folder)/(uploaded['paper']['id']+'.pdf');target.write_bytes(RAW+b'\n')
        _,result=self.attach(identity,uploaded['paper']);self.assertTrue(result.get('planning_error'))
        self.assertEqual(load(session),before)

    def test_upload_caps_short_stream_and_quota_cleanup(self):
        service=self.server.service
        for length,stream in [(64*1024*1024+1,io.BytesIO()),(100,io.BytesIO(b'partial'))]:
            with self.assertRaises(ValueError):receive(service,'paper.pdf',length,stream,'unit_cap')
        with patch('rut_science.science_bot.paper_library.MAX_PAPERS',0):
            with self.assertRaises(ValueError):receive(service,'paper.pdf',len(RAW),io.BytesIO(RAW),'quota')
        self.assertEqual(list(root_for(service.folder).glob('*.pdf')),[])

    def test_page_range_and_restored_service_reuse_library(self):
        _,uploaded=self.upload();identity=self.new();_,result=self.attach(identity,uploaded['paper'],start_page=2,end_page=2)
        self.assertFalse(result.get('planning_error'),result)
        session=self.server.service.session(identity);self.assertEqual(load(session)['evidence'][0]['start_page'],2)
        from rut_science.science_bot.api import LocalService
        restored=LocalService(self.server.service.folder)
        self.assertEqual(listing(restored.folder)['papers'][0]['id'],uploaded['paper']['id'])

    def test_upload_does_not_rebind_an_existing_research_workspace(self):
        project=Path(self.tmp.name)/'project';project.mkdir();(project/'model.py').write_text('width = 32\n',encoding='utf-8')
        session=GeneralSession.create(self.server.service.folder,backend='offline',workspace=project)
        self.server.service.sessions[session.meta['id']]=session
        _,uploaded=self.upload();_,result=self.attach(session.meta['id'],uploaded['paper'])
        self.assertFalse(result.get('planning_error'),result);self.assertEqual(session.workspace.root,project.resolve())
        self.assertIn('width = 32',session.message('读取 model.py')['answer'])

    def test_concurrent_uploads_of_one_pdf_create_one_blob(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda key:self.upload(key=key),['parallel_a','parallel_b']))
        self.assertEqual([r[0] for r in results],[200,200])
        self.assertEqual(results[0][1]['paper']['id'],results[1][1]['paper']['id'])
        self.assertEqual(len(list(root_for(self.server.service.folder).glob('*.pdf'))),1)
        self.assertEqual(len(self.json('/ui/papers')[1]['papers']),1)


if __name__=='__main__':unittest.main()
