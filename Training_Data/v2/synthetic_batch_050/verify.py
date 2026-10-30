"""Recompute synthetic batch identities, reference rewards and sampled PPO evidence."""
import argparse
import ast
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(HERE.parent))
from protocol import rows,sha,digest,expected_reward,validate_observation,write
from ppo_smoke import verify_rollout,load_policy
from train import load_batch
from validate import validate_data
from environment import ToolEnvironment


def main(run):
    seal=HERE/'release_manifest.json'
    if seal.exists():
        for name,h in json.loads(seal.read_text(encoding='utf-8'))['sha256'].items():
            if sha(HERE/name)!=h: raise ValueError('Sealed release artifact changed: '+name)
    tasks=load_batch();wanted={t['task_id'] for t in tasks}
    scenarios={s['task_id']:s for s in json.loads((HERE/'scenarios.json').read_text(encoding='utf-8'))}
    assert set(scenarios)==wanted
    assert len({digest({'public':{k:v for k,v in t['public'].items() if k!='user_request'},'simulator':t['simulator']}) for t in tasks})==50
    assert all(not any(w in t['public']['user_request'] for w in ('OOM','零效应模拟结果','如实报告反向结果','outcome_scenario')) for t in tasks)
    # Counterfactual fixture test: hidden future outcomes/failures must not alter
    # the initial full observation, not merely its 32-dimensional projection.
    base=deepcopy(tasks[0]);initial_observation=ToolEnvironment(base).reset()[0]
    private_checks=0
    for scenario,failure in [('benefit',None),('harm',None),('null','mock_oom')]:
        counterfactual=deepcopy(base)
        counterfactual['simulator'].update(outcome_scenario=scenario,job_failure=failure)
        assert ToolEnvironment(counterfactual).reset()[0]==initial_observation
        private_checks+=1
    annotated=next(HERE.glob('*.jsonc')).read_text(encoding='utf-8')
    assert json.loads('\n'.join(l for l in annotated.splitlines() if not l.lstrip().startswith('//')))==rows(HERE/'tasks.jsonl')
    references=rows(HERE/'reference_episodes.jsonl');decisions=0;terminal_counts=Counter()
    assert {ep['task_id'] for ep in references}==wanted and len(references)==50
    for ep in references:
        assert ep['classification']==scenarios[ep['task_id']]['expected_classification']
        assert ep['ppo_eligible'] is False
        milestones=set();previous=None
        for i,s in enumerate(ep['steps']):
            validate_observation(s['observation']);validate_observation(s['next_observation'])
            assert s['decision_index']==i and (previous is None or previous==s['observation'])
            assert digest(s['observation'])==s['observation_hash'] and digest(s['next_observation'])==s['next_observation_hash']
            assert s['behavior_log_probability'] is None and s['value_estimate'] is None
            assert abs(expected_reward(s,milestones)-s['reward'])<1e-9
            previous=s['next_observation'];decisions+=1
        terminal_counts[ep['classification']]+=1
    labels=rows(HERE/'bc_reference.jsonl')
    assert len(labels)==decisions and all(r['source']=='scripted_reference_not_expert' and r['human_review_status']=='pending' and not r['ppo_eligible'] for r in labels)
    proof=json.loads((run/'verification.json').read_text(encoding='utf-8'))
    bc=json.loads((run/'bc_policy.json').read_text(encoding='utf-8'));load_policy(bc)
    expected_behavior=digest(bc);total=0;counts=Counter();reward_count=0
    for i in range(proof['ppo_iterations']):
        folder=run/f'iteration_{i+1:03d}'
        behavior=json.loads((folder/'behavior_policy.json').read_text(encoding='utf-8'))
        updated=json.loads((folder/'updated_policy.json').read_text(encoding='utf-8'));load_policy(updated)
        assert digest(behavior)==expected_behavior and digest(updated)!=expected_behavior
        records=rows(folder/'rollout.jsonl');verify_rollout(records,behavior,tasks=tasks)
        previous=None;milestones=set()
        for row in records:
            if previous is None or previous['terminated'] or previous['truncated']: milestones=set()
            before=row['observation'];after=row['next_observation']
            # Independently recover public tool feedback, not the trainer's reward proof.
            added=after['evidence'][len(before['evidence']):]
            public_results=[e['value']['result'] for e in added if e['kind']=='tool_result']
            result=public_results[-1] if public_results else {}
            check={'action':row['action'],'observation':before,'classification':row['classification'],
                'feedback':{'error':after['last_call_failed'],'result':result}}
            assert abs(expected_reward(check,milestones)-row['reward'])<1e-9
            previous=row;reward_count+=1
        per_task=Counter(r['task_id'] for r in records)
        assert set(per_task)==wanted and set(per_task.values())=={proof['steps_per_task_per_iteration']}
        counts.update(per_task);total+=len(records);expected_behavior=digest(updated)
    final=json.loads((run/'updated_policy.json').read_text(encoding='utf-8'))
    assert digest(final)==expected_behavior and total==proof['transitions']
    sys.path.insert(0,str(HERE.parents[2]/'scripts'))
    from integrity import check_project
    protected=check_project();base=validate_data()
    for p in HERE.glob('*.py'): ast.parse(p.read_text(encoding='utf-8'))
    report={'passed':True,'tasks':50,'structurally_distinct_tasks':50,'reference_decisions':decisions,
        'public_request_private_hint_checks':50,'counterfactual_hidden_fixture_tests':private_checks,
        'reference_terminal_counts':dict(terminal_counts),'scripted_bc_labels':len(labels),'ppo_transitions':total,
        'all_50_tasks_sampled':set(counts)==wanted,'ppo_rewards_independently_recomputed':reward_count,
        'behavior_probabilities_and_values_recomputed':True,'baseline_v2_valid':base['passed'],
        'protected_previous_files':protected,'human_expert_labels':0,'new_independent_sources':0,
        'real_scientific_executions':0,'default_policy_promoted':False,
        'runtime_hashes':{name:sha(HERE.parent/name) for name in ['environment.py','protocol.py','ppo_smoke.py']}}
    write(run/'independent_verification.json',report)
    if not (HERE/'verification.json').exists(): write(HERE/'verification.json',report)
    # New batch only: pin code, data and training evidence without rewriting frozen baselines.
    release={p.relative_to(HERE).as_posix():sha(p) for p in HERE.rglob('*') if p.is_file() and p.name!='release_manifest.json' and '__pycache__' not in p.parts}
    if not seal.exists(): write(seal,{'sha256':release,'scope':'Synthetic batch and its bounded training evidence; future runs do not rewrite this seal'})
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,default=HERE/'training_run_001')
    main(p.parse_args().run)
