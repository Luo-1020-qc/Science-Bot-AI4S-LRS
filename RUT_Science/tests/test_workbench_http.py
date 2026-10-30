"""Workbench authorization, same-origin boundary and actual plan/export flow."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from rut_science.science_bot.workbench import make_workbench
from rut_science.science_bot.interface_demo import PILOT_ANSWER


class WorkbenchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.server=make_workbench(Path(self.tmp.name)/'sessions',port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.serial=0

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)

    def call(self,path,body=None,*,auth=True,key=None,extra=None):
        self.serial+=1
        headers={'Authorization':'Bearer '+self.server.service.token} if auth else {}
        if body is not None:
            headers.update({'Content-Type':'application/json','Idempotency-Key':key or 'workbench_'+str(self.serial)})
        headers.update(extra or {})
        data=json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None
        request=Request(self.url+path,data=data,headers=headers)
        try:
            with urlopen(request,timeout=5) as response:
                return response.status,response.headers,response.read()
        except HTTPError as response:
            return response.code,response.headers,response.read()

    def json(self,path,body=None,**kwargs):
        status,_,raw=self.call(path,body,**kwargs)
        return status,json.loads(raw)

    def example(self):
        status,result=self.json('/ui/example',{})
        self.assertEqual(status,200,result)
        return result

    def test_public_example_and_assets_do_not_expose_local_token_or_private_sessions(self):
        for path in ('/','/app.js','/styles.css','/demo.json','/terminal','/demo-delivery.html'):
            with self.subTest(path=path):
                status,headers,raw=self.call(path,auth=False)
                self.assertEqual(status,200);self.assertNotIn(self.server.service.token.encode(),raw)
                self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.json('/ui/sessions',auth=False)[0],401)
        self.assertEqual(self.json('/ui/example',{},auth=False)[0],401)

    def test_cross_site_and_foreign_host_blocked_on_api_and_view(self):
        for path in ('/','/ui/sessions','/v1/sessions/'+'e'*32):
            for headers in ({'Origin':'https://example.invalid'}, {'Host':'attacker.invalid'}, {'Sec-Fetch-Site':'cross-site'}):
                self.assertEqual(self.call(path,extra=headers)[0],403)
        with self.assertRaises(ValueError):make_workbench(Path(self.tmp.name)/'other',host='0.0.0.0',port=0)

    def test_example_creation_idempotent_and_does_not_load_model_credentials(self):
        with patch('rut_science.science_bot.general.provider.load_api_config',side_effect=AssertionError('implicit model')):
            status,first=self.json('/ui/example',{},key='same-example')
            _,again=self.json('/ui/example',{},key='same-example')
        self.assertEqual(status,200);self.assertEqual(first,again)
        self.assertTrue(first['example']);self.assertEqual(first['backend'],'offline')
        self.assertEqual(first['resources']['llm_requests'],0)
        self.assertEqual(first['resources']['tool_attempts'],0)
        self.assertEqual(len(self.server.service.sessions),1)
        self.assertEqual(self.json('/ui/example',{'backend':'api'})[0],409)

    def test_read_only_status_restore_does_not_add_snapshot(self):
        example=self.example();identity=example['id'];session=self.server.service.sessions[identity]
        revision=session_view_revision=example['planning']['revision']
        self.server.service.sessions.clear()
        status,restored=self.json('/ui/sessions/'+identity)
        self.assertEqual(status,200);self.assertEqual(restored['planning']['revision'],revision)
        self.assertEqual(restored['planning']['hash'],example['planning']['hash'])
        _,listing=self.json('/ui/sessions');self.assertEqual(listing['sessions'][0]['id'],identity)

    def test_draft_confirm_export_and_revision_keep_version_and_execution_boundary(self):
        identity=self.example()['id'];base='/v1/sessions/'+identity
        self.assertEqual(self.call('/ui/sessions/'+identity+'/delivery.html')[0],409)
        _,denied=self.json(base+'/messages',{'text':'/plan approve '+('a'*64)})
        self.assertTrue(denied['planning_error'])
        for text in ('/plan accept hypothesis','/plan sampling: '+PILOT_ANSWER):
            _,result=self.json(base+'/messages',{'text':text});self.assertFalse(result.get('planning_error'))
        _,view=self.json('/ui/sessions/'+identity)
        self.assertTrue(view['planning']['ready'])
        readout=view['planning']['design_readout']
        self.assertTrue(readout['ready']);self.assertEqual(readout['hash'],view['planning']['hash'])
        self.assertEqual(len(readout['sections']),6)
        self.assertIn('experimental_unit',{item['field'] for section in readout['sections'] for item in section['items']})
        identity_hash=view['planning']['hash']
        _,result=self.json(base+'/messages',{'text':'/plan approve '+identity_hash})
        self.assertTrue(result['planning']['approved']);self.assertFalse(result['execution_authorized'])
        self.assertEqual(self.json(base+'/confirm',{'draft_hash':identity_hash})[0],409)
        self.json(base+'/messages',{'text':'/plan export'})
        for suffix in ('html','md','json'):
            status,headers,raw=self.call('/ui/sessions/'+identity+'/delivery.'+suffix)
            self.assertEqual(status,200);self.assertIn('attachment;',headers['Content-Disposition'])
            if suffix=='html':self.assertIn('规划已确认',raw.decode('utf-8'))
        self.json(base+'/messages',{'text':'/plan revise resources: 示例最多4次运行，1小时上限'})
        _,view=self.json('/ui/sessions/'+identity)
        self.assertFalse(view['planning']['approved']);self.assertFalse(view['planning']['export_current'])
        self.assertEqual(view['resources']['llm_requests'],0)

    def test_path_traversal_and_unknown_delivery_types_rejected(self):
        identity=self.example()['id']
        for path in ('/ui/sessions/../.local_token','/ui/sessions/'+identity+'/delivery.py',
                     '/ui/sessions/'+identity+'/../../session.json','/ui/sessions/'+identity+'/delivery.html/extra'):
            self.assertEqual(self.call(path)[0],409)


if __name__=='__main__':unittest.main()
