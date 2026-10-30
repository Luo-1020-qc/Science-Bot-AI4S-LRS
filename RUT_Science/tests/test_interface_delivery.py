"""Shared examples, version-bound delivery and real terminal command routes."""
import asyncio
from contextlib import nullcontext
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from rich.console import Console
from rut_science.science_bot import terminal
from rut_science.science_bot.interface_demo import create_example,PILOT_ANSWER
from rut_science.science_bot.presentation import session_view,export_bundle,export_plan,delivery_html,terminal_preview_html,browser_preview_html
from rut_science.science_bot.general.planning.ledger import load,contract_hash

ROOT=Path(__file__).resolve().parents[2]


class InterfaceDeliveryTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.local');self.addCleanup(self.tmp.cleanup)
        self.session=create_example(Path(self.tmp.name))

    def fill(self):
        self.session.message('/plan accept hypothesis')
        self.session.message('/plan sampling: '+PILOT_ANSWER)

    def test_example_is_explicitly_synthetic_offline_and_no_execution(self):
        view=session_view(self.session)
        self.assertTrue(view['example']);self.assertEqual(view['backend'],'offline')
        self.assertIn('sampling',[f['field'] for f in view['planning']['unknown']])
        self.assertFalse(view['planning']['approved']);self.assertFalse(view['planning']['execution_authorized'])
        self.assertEqual(view['resources']['llm_requests'],0);self.assertEqual(view['resources']['tool_attempts'],0)

    def test_view_is_read_only_and_shows_old_export_status_after_revision(self):
        before=deepcopy(load(self.session));session_view(self.session);self.assertEqual(load(self.session),before)
        export_bundle(self.session)
        self.assertTrue(session_view(self.session)['planning']['export_current'])
        self.session.message('/plan revise resources: 演示预算最多4次运行，1小时上限')
        self.assertFalse(session_view(self.session)['planning']['export_current'])

    def test_draft_export_contains_three_formats_and_keeps_unknown(self):
        bundle=export_bundle(self.session)
        self.assertEqual(set(bundle),{'html','markdown','json','hash'})
        text=bundle['html'].read_text(encoding='utf-8')
        self.assertIn('规划草案',text);self.assertIn('尚未执行',text);self.assertIn('样本与重复依据',text)
        self.assertIn('规划确认不等于真实执行授权',text)
        self.assertEqual(self.session.resources()['llm_requests'],0)

    def test_confirmed_export_and_revision_do_not_authorize_experiment(self):
        self.fill();identity=contract_hash(load(self.session))
        result=self.session.message('/plan approve '+identity)
        self.assertTrue(result['planning']['approved'])
        bundle=export_bundle(self.session)
        self.assertIn('规划已确认',bundle['html'].read_text(encoding='utf-8'))
        self.session.message('/plan revise resources: 演示预算最多4次运行，1小时上限')
        self.assertFalse(session_view(self.session)['planning']['approved'])
        _,old,_=export_plan(self.session)
        self.assertEqual(old['contract_hash'],identity)
        self.assertFalse(self.session.status()['confirmed'])

    def test_export_tampering_rejected_even_with_original_contract_hash(self):
        bundle=export_bundle(self.session)
        plan=json.loads(bundle['json'].read_text(encoding='utf-8'))
        plan['nodes'][0]['purpose']='forged description'
        bundle['json'].write_text(json.dumps(plan),encoding='utf-8')
        with self.assertRaises(ValueError):export_plan(self.session)

    def test_delivery_html_escapes_model_markup(self):
        export_bundle(self.session);_,plan,_=export_plan(self.session)
        plan['fact_sources']['scope']['value']='<script>alert(1)</script><img src=x onerror=alert(2)>'
        html=delivery_html(plan)
        self.assertNotIn('<script>alert',html);self.assertNotIn('<img src=x',html)
        self.assertIn('&lt;script&gt;',html)

    def test_tampering_old_snapshot_cannot_forge_human_approval(self):
        from rut_science.science_bot.general.planning.runtime import _plan
        bundle=export_bundle(self.session);state=load(self.session)
        snapshot=self.session.folder/'planning'/state['id']/'snapshots'/(bundle['json'].stem+'.json')
        old=json.loads(snapshot.read_text(encoding='utf-8'))
        old['approval']={'contract_hash':bundle['hash'],'turn':999,'scope':'planning_contract_only'}
        snapshot.write_text(json.dumps(old),encoding='utf-8')
        bundle['json'].write_text(json.dumps(_plan(old)),encoding='utf-8')
        with self.assertRaises(ValueError):export_plan(self.session)

    def test_examples_have_no_remote_assets_or_api_credentials(self):
        browser=browser_preview_html();console=terminal_preview_html()
        self.assertIn('__SCIENCE_BOT_DEMO__',browser)
        self.assertNotIn('<script src=',browser);self.assertNotIn('href="/styles.css"',browser)
        self.assertIn('合成界面',browser);self.assertIn('Science Bot',console)
        self.assertNotIn('API_key_Agent.json',browser)

    def test_actual_terminal_home_report_and_deliver_share_session(self):
        lines=iter(['/home','/report','/deliver','/exit'])
        async def prompt(*args,**kwargs):return next(lines)
        stream=io.StringIO();console=Console(file=stream,width=125,force_terminal=False,highlight=False)
        with patch.object(terminal,'open_session',return_value=self.session), \
             patch.object(terminal,'Console',return_value=console), \
             patch.object(terminal,'PromptSession',return_value=SimpleNamespace(prompt_async=prompt)), \
             patch.object(terminal,'patch_stdout',return_value=nullcontext()):
            self.assertEqual(asyncio.run(terminal.interactive(SimpleNamespace())),0)
        output=stream.getvalue()
        self.assertIn('交付已生成',output);self.assertIn('HTML',output);self.assertIn('JSON',output)
        self.assertNotIn('NameError',output);self.assertNotIn('TypeError',output)


if __name__=='__main__':unittest.main()
