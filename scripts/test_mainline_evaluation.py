"""Audit task lineage, private-input boundary and honest failure scoring."""
from copy import deepcopy
import unittest
import evaluate_planning_mainline as evaluation
from rut_science.science_bot.general.planning.ledger import new_state, apply


class MainlineEvaluationTests(unittest.TestCase):
    def setUp(self):self.data=evaluation.load_cases()

    def test_ten_cases_cover_five_mechanisms_in_two_source_groups(self):
        cases=self.data['cases']
        self.assertEqual(len(cases),10)
        self.assertEqual(len({c['root_group'] for c in cases}),2)
        self.assertEqual(len({c['mechanism'] for c in cases}),5)
        self.assertEqual(self.data['provenance']['human_participants'],0)
        self.assertFalse(self.data['provenance']['expert_approved'])

    def test_agent_start_does_not_read_answers_or_expected_labels(self):
        for case in self.data['cases']:
            public={'initial_input':case['initial_input']}
            self.assertEqual(evaluation.public_start(public),case['initial_input'])
            altered=deepcopy(case);altered['private']={'answers':'SECRET_SENTINEL'};altered['expected']={}
            self.assertEqual(evaluation.public_start(altered),case['initial_input'])

    def test_blocked_handoff_with_wrong_critical_answer_does_not_pass(self):
        case=next(c for c in self.data['cases'] if c['id']=='models_unknown')
        state=new_state();values=case['private']['answers']
        apply(state,{'updates':{f:{'value':v,'quote':v,'status':'declared'} for f,v in values.items() if v!='未知'},'unknown':['sampling']},1)
        state['evidence_actions']={'sampling':{'text':'先核实先导记录','turn':2,'status':'user_proposed_step_not_evidence'}}
        state['facts']['scope']['value']='被错误改成其他领域'
        metrics=evaluation.score(case,state,[],{'nodes':[]})
        self.assertFalse(metrics['expected_outcome_met'])
        self.assertIn('scope',metrics['answer_mismatches'])

    def test_only_terminal_punctuation_is_ignored_not_different_values(self):
        case=self.data['cases'][0];state=new_state()
        apply(state,{'updates':{f:{'value':v.rstrip('。'),'quote':v,'status':'declared'} for f,v in case['private']['answers'].items()},'unknown':[]},1)
        self.assertEqual(evaluation.score(case,state,[],{'nodes':[]})['answer_mismatches'],[])
        state['facts']['resources']['value']='扩大到600次运行'
        self.assertIn('resources',evaluation.score(case,state,[],{'nodes':[]})['answer_mismatches'])


if __name__=='__main__':unittest.main()
