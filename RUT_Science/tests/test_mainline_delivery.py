"""Plan readout retains uncertainty and cannot change approvals or execution."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from rut_science.science_bot.general.planning.delivery import design_readout, render_design
from rut_science.science_bot.general.planning.ledger import load, contract_hash
from rut_science.science_bot.interface_demo import create_example, PILOT_ANSWER
from rut_science.science_bot.presentation import plan_view

ROOT=Path(__file__).resolve().parents[2]


class MainlineDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.local');self.addCleanup(self.tmp.cleanup)
        self.session=create_example(Path(self.tmp.name))

    def test_readout_is_read_only_and_matches_current_contract(self):
        state=load(self.session); before=deepcopy(state)
        view=design_readout(state)
        self.assertEqual(state,before)
        self.assertEqual(view['hash'],contract_hash(state))
        self.assertFalse(view['ready']);self.assertFalse(view['execution_authorized'])
        items={i['field']:i for s in view['sections'] for i in s['items']}
        self.assertEqual(items['sampling']['status'],'unknown')
        self.assertEqual(items['hypothesis']['status'],'proposed')
        self.assertIn('未知',render_design(state));self.assertIn('待确认提议',render_design(state))

    def test_ready_reply_directly_contains_the_experimental_design(self):
        self.session.message('/plan accept hypothesis')
        result=self.session.message('/plan sampling: '+PILOT_ANSWER)
        self.assertTrue(result['planning']['review']['ready'])
        for content in ['实验设计草案','因素与对比','实验与推断单位','指标与分析','验收、阴性结果与停止','人类职责']:
            self.assertIn(content,result['answer'])
        self.assertFalse(result['question_form'])
        self.assertFalse(result['planning']['approved'])
        self.assertEqual(self.session.resources()['llm_requests'],0)

    def test_conflict_and_staleness_are_visible_in_every_projection(self):
        self.session.message('/plan resources: 预算最多3次运行、1小时上限')
        state=load(self.session)
        view=plan_view(state)['design_readout']
        resource=next(i for s in view['sections'] for i in s['items'] if i['field']=='resources')
        self.assertEqual(resource['status'],'conflict')
        self.assertNotIn('最多6次',resource['value'])
        self.session.message('/plan revise resources: 预算最多3次运行、1小时上限')
        state=load(self.session)
        design=next(i for s in design_readout(state)['sections'] for i in s['items'] if i['field']=='design')
        self.assertEqual(design['status'],'stale')
        self.assertFalse(plan_view(state)['ready'])

    def test_blocked_draft_keeps_acquisition_separate_from_facts(self):
        self.session.message('/plan accept hypothesis')
        self.session.message('/plan sampling: 未知')
        self.session.message('先找先导记录并交由导师复核，不填入未知方差。')
        state=load(self.session)
        self.assertNotIn('sampling',state['facts'])
        self.assertIn('sampling',state['unknown'])
        self.assertIn('拟议步骤',render_design(state))
        self.assertFalse(design_readout(state)['ready'])
        result=self.session.message('/plan approve '+contract_hash(state))
        self.assertTrue(result['planning_error'])

    def test_goal_and_design_change_recheck_the_unit_and_baseline(self):
        self.session.message('/plan accept hypothesis')
        self.session.message('/plan sampling: '+PILOT_ANSWER)
        self.session.message('/plan approve '+contract_hash(load(self.session)))
        self.session.message('/plan revise objective_type: prediction\ndesign: prediction')
        state=load(self.session)
        self.assertIsNone(state['approval'])
        self.assertIn('experimental_unit',state['stale'])
        self.assertIn('baseline',state['stale'])
        self.assertFalse(design_readout(state)['ready'])


if __name__=='__main__':unittest.main()
