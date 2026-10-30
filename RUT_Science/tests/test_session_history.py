"""Actual HTTP deletion, cache privacy, busy requests and path boundaries."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_workbench_http as http_fixture
from rut_science.science_bot.api import LocalService
from rut_science.science_bot import session_history
from rut_science.planning_agent import session_lock


class SessionHistoryTests(unittest.TestCase):
    setUp=http_fixture.WorkbenchHTTPTests.setUp
    tearDown=http_fixture.WorkbenchHTTPTests.tearDown
    call=http_fixture.WorkbenchHTTPTests.call
    json=http_fixture.WorkbenchHTTPTests.json
    example=http_fixture.WorkbenchHTTPTests.example

    def remove(self,identity,**kwargs):
        return self.json('/ui/sessions/'+identity+'/delete',{'confirm':identity},**kwargs)

    def test_delete_removes_all_session_artifacts_preserving_other_sessions_and_token(self):
        first=self.example()['id'];other=self.example()['id'];service=self.server.service
        folder=service.folder/first;token=(service.folder/'.local_token').read_bytes()
        self.json('/v1/sessions/'+first+'/messages',{'text':'我想比较两模型，PRIVATE_DELETE_SENTINEL'})
        self.json('/v1/sessions/'+first+'/messages',{'text':'/plan export'})
        self.assertTrue((folder/'planning').exists())
        status,result=self.remove(first)
        self.assertEqual(status,200,result);self.assertEqual(result['deleted'],first)
        self.assertFalse(folder.exists());self.assertNotIn(first,service.sessions)
        self.assertTrue((service.folder/other/'session.json').is_file())
        self.assertEqual((service.folder/'.local_token').read_bytes(),token)
        self.assertNotIn('PRIVATE_DELETE_SENTINEL',service.requests_path.read_text(encoding='utf-8'))
        _,listing=self.json('/ui/sessions');self.assertEqual([r['id'] for r in listing['sessions']],[other])
        self.assertEqual(self.call('/ui/sessions/'+first)[0],409)
        self.assertEqual(self.call('/ui/sessions/'+first+'/delivery.json')[0],409)

    def test_auth_origin_and_explicit_confirmation_required(self):
        identity=self.example()['id'];path='/ui/sessions/'+identity+'/delete'
        self.assertEqual(self.remove(identity,auth=False)[0],401)
        self.assertEqual(self.remove(identity,extra={'Origin':'https://example.invalid'})[0],403)
        for body in ({},{'confirm':'a'*32},{'confirm':identity,'path':'../outside'}):
            self.assertEqual(self.json(path,body)[0],409)
        self.assertTrue((self.server.service.folder/identity/'session.json').exists())

    def test_deleted_session_cannot_restore_or_replay_cached_create_and_messages(self):
        _,created=self.json('/ui/example',{},key='create-to-delete');identity=created['id']
        endpoint='/v1/sessions/'+identity+'/messages'
        body={'text':'我想比较模型，待删除历史内容'}
        self.json(endpoint,body,key='message-to-delete')
        self.assertEqual(self.remove(identity)[0],200)
        self.assertEqual(self.json('/ui/example',{},key='create-to-delete')[0],410)
        self.assertEqual(self.json(endpoint,body,key='message-to-delete')[0],409)
        restored=LocalService(self.server.service.folder)
        with self.assertRaises(ValueError):restored.session(identity)
        self.assertEqual(self.remove(identity)[0],200)
        self.assertFalse((restored.folder/identity).exists())

    def test_busy_request_refuses_delete_but_status_and_cancel_remain_available(self):
        identity=self.example()['id'];service=self.server.service
        with service.session_access(identity):
            self.assertEqual(self.remove(identity)[0],409)
            self.assertEqual(self.call('/v1/sessions/'+identity)[0],200)
            self.assertEqual(self.json('/v1/sessions/'+identity+'/cancel',{})[0],200)
        self.assertEqual(self.remove(identity)[0],200)

    def test_running_worker_and_process_lock_refuse_delete_without_losing_records(self):
        identity=self.example()['id'];service=self.server.service
        service.workers[identity]=SimpleNamespace(is_alive=lambda:True)
        self.assertEqual(self.remove(identity)[0],409)
        service.workers.pop(identity)
        with session_lock(service.folder/identity):
            self.assertEqual(self.remove(identity)[0],409)
        self.assertNotIn(identity,service.deleted_sessions)
        self.assertTrue((service.folder/identity/'session.json').is_file())

    def test_links_and_traversal_are_refused_before_recursive_removal(self):
        identity=self.example()['id'];folder=self.server.service.folder/identity
        (folder/'nested').mkdir()
        with patch.object(session_history,'_reparse',side_effect=lambda p:p.name=='nested'):
            self.assertEqual(self.remove(identity)[0],409)
        self.assertTrue((folder/'session.json').is_file())
        for identity in ('../outside','a'*31,'A'*32,'a'*32+'/../outside'):
            with self.assertRaises(ValueError):self.server.service.delete_session(identity)
        self.assertEqual(self.remove('a'*32)[0],409)

    def test_interrupted_cleanup_is_tombstoned_and_can_be_retried(self):
        identity=self.example()['id'];service=self.server.service
        with patch.object(session_history.shutil,'rmtree',side_effect=PermissionError('File is in use')):
            self.assertEqual(self.remove(identity)[0],409)
        self.assertIn(identity,service.deleted_sessions)
        self.assertEqual(self.call('/ui/sessions/'+identity)[0],409)
        _,listing=self.json('/ui/sessions')
        self.assertTrue(listing['sessions'][0]['deletion_pending'])
        self.assertEqual(self.remove(identity)[0],200)
        self.assertFalse((service.folder/identity).exists())

    def test_scoped_other_cache_preserved_and_legacy_unscoped_payload_scrubbed(self):
        first=self.example()['id'];other=self.example()['id'];service=self.server.service
        service.requests['legacy']={'hash':'a'*64,'result':{'answer':'LEGACY_PRIVATE_PAYLOAD'},'status':'complete'}
        service.requests['other']={'hash':'b'*64,'session_id':other,'result':{'answer':'OTHER_PAYLOAD'},'status':'complete'}
        self.remove(first)
        self.assertNotIn('LEGACY_PRIVATE_PAYLOAD',json.dumps(service.requests))
        self.assertEqual(service.requests['legacy']['http_status'],410)
        self.assertEqual(service.requests['other']['result']['answer'],'OTHER_PAYLOAD')

    def test_plain_chat_title_identifies_the_history_to_delete(self):
        _,created=self.json('/v1/sessions',{'backend':'offline'})
        self.json('/v1/sessions/'+created['id']+'/messages',{'text':'你好，讨论本周安排'})
        _,listing=self.json('/ui/sessions')
        self.assertEqual(listing['sessions'][0]['title'],'你好，讨论本周安排')

    def test_unowned_directory_with_valid_looking_id_is_preserved(self):
        identity='f'*32;folder=self.server.service.folder/identity;folder.mkdir()
        (folder/'important.txt').write_text('not a session',encoding='utf-8')
        self.assertEqual(self.remove(identity)[0],409)
        self.assertEqual((folder/'important.txt').read_text(encoding='utf-8'),'not a session')


if __name__=='__main__':unittest.main()
