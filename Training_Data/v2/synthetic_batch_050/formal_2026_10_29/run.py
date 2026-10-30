"""Prespecified single-seed multi-batch candidate-policy experiment; offline CPU only."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import Counter
import json
import os
import platform
import sys
import time

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
V2=BATCH.parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(V2))
sys.path.insert(0,str(BATCH))
import torch
import train as training
from protocol import write,rows,sha,digest,read_tasks
from ppo_smoke import load_policy
from environment import ToolEnvironment,reference_action


def now(): return datetime.now(timezone(timedelta(hours=8))).isoformat()


def evaluate(tasks,model=None):
    records=[]
    for i,task in enumerate(tasks):
        env=ToolEnvironment(task);obs,_=env.reset();total=0.0;errors=0;actions=Counter()
        while not env.terminated and not env.truncated:
            if model is None: index=reference_action(obs)
            else:
                with torch.no_grad():
                    distribution,_=model(torch.tensor([env.features(obs)]),torch.tensor([[c['available'] for c in obs['candidates']]],dtype=torch.bool))
                index=int(distribution.probs.argmax(-1).item())
            actions[obs['candidates'][index]['action_id']]+=1
            obs,reward,_,_,info=env.step(index);total+=reward;errors+=bool(info['feedback']['error'])
        expected='justified_stop' if task['public']['sigma'] is None or (task['simulator']['job_failure'] and not task['simulator']['existing_job']) else 'completed_mock_research_loop'
        records.append({'task_id':task['task_id'],'classification':info['classification'],'expected_classification':expected,
            'success':info['success'] and info['classification']==expected,'steps':env.steps,'return':total,'errors':errors,'action_counts':dict(actions)})
        if len(tasks)>10 and (i+1)%10==0: print('baseline evaluation',i+1,'/',len(tasks),flush=True)
    return records


def aggregate(records):
    n=len(records)
    return {'successes':sum(r['success'] for r in records),'tasks':n,'success_rate':sum(r['success'] for r in records)/n,
        'mean_decisions':sum(r['steps'] for r in records)/n,'mean_return':sum(r['return'] for r in records)/n,
        'total_errors':sum(r['errors'] for r in records),'terminal_counts':dict(Counter(r['classification'] for r in records))}


def main():
    if (HERE/'plan.json').exists(): raise ValueError('Experiment already started; preserve plan and prior checkpoints')
    start=time.monotonic();torch.set_num_threads(1)
    tasks=training.load_batch()
    seal=json.loads((BATCH/'release_manifest.json').read_text(encoding='utf-8'))
    assert all(sha(BATCH/name)==h for name,h in seal['sha256'].items())
    output=BATCH/'training_run_002'
    if output.exists(): raise ValueError('Fresh output directory required')
    config={'experiment':'single_seed_multibatch_synthetic_candidate_policy','started_at':now(),'seed':20261029,
        'bc_epochs':300,'ppo_iterations':5,'steps_per_task_per_iteration':32,'training_tasks':50,
        'planned_transitions':8000,'ppo_epochs_per_batch':4,'minibatch_size':64,'learning_rate':.0003,
        'gamma':.99,'gae_lambda':.95,'clip_ratio':.2,'entropy_coefficient':.01,'gradient_norm_limit':.5,
        'initialization':'Fresh scripted BC; not resuming training_run_001',
        'checkpoint_rule':'Report final fixed-budget checkpoint; no selection using public evaluation tasks',
        'training_task_hashes':{t['task_id']:digest(t) for t in tasks},
        'source_sha256':{'train.py':sha(BATCH/'train.py'),'environment.py':sha(V2/'environment.py'),'protocol.py':sha(V2/'protocol.py'),'ppo_smoke.py':sha(V2/'ppo_smoke.py')},
        'python':platform.python_version(),'torch':torch.__version__,'torch_threads':1,'logical_cpus':os.cpu_count(),
        'human_expert_labels':0,'independent_blind_tasks':0,'real_scientific_execution':False,'model_api_requests':0,
        'evaluation_scope':'Training 50 + published development 2 + published evaluation examples 2; shared synthetic mechanism, NOT independent blinded generalization'}
    write(HERE/'plan.json',config,fresh=True)
    training.train(output,iterations=5,steps_per_task=32,bc_epochs=300,seed=20261029)
    # Evaluation starts only AFTER all fixed-budget training updates finish.
    bc=load_policy(json.loads((output/'bc_policy.json').read_text(encoding='utf-8')))
    ppo=load_policy(json.loads((output/'updated_policy.json').read_text(encoding='utf-8')))
    summaries={};details={}
    reference=rows(BATCH/'reference_episodes.jsonl')
    rule_train=[{'task_id':ep['task_id'],'classification':ep['classification'],'success':True,
        'steps':len(ep['steps']),'return':sum(s['reward'] for s in ep['steps']),
        'errors':sum(bool(s['feedback']['error']) for s in ep['steps'])} for ep in reference]
    expected={s['task_id']:s['expected_classification'] for s in json.loads((BATCH/'scenarios.json').read_text(encoding='utf-8'))}
    ppo_train=json.loads((output/'training_task_evaluation.json').read_text(encoding='utf-8'))['records']
    for r in ppo_train:r['success']=r['success'] and r['classification']==expected[r['task_id']]
    bc_train=evaluate(tasks,bc)
    for policy,records in [('rule',rule_train),('bc',bc_train),('ppo',ppo_train)]:
        details[policy]={'train':records};summaries[policy]={'train':aggregate(records)}
    for split in ('development','evaluation_example'):
        public_tasks=read_tasks(split,purpose='verification')
        for name,model in [('rule',None),('bc',bc),('ppo',ppo)]:
            print('public nontraining diagnostics',split,name,flush=True)
            records=evaluate(public_tasks,model)
            details[name][split]=records;summaries[name][split]=aggregate(records)
    write(HERE/'evaluation_details.json',details,fresh=True)
    iterations=[]
    for i in range(1,6):
        proof=json.loads((output/f'iteration_{i:03d}/verification.json').read_text(encoding='utf-8'))
        iterations.append({'batch':i,'transitions':proof['sampling']['records'],'gradient_steps':proof['gradient_steps'],
            'successful_episode_ends':proof['successful_episode_ends'],'external_truncations':proof['external_truncations'],
            'behavior_hash':proof['behavior_hash'],'updated_hash':proof['updated_hash']})
    result={'completed_at':now(),'elapsed_seconds':time.monotonic()-start,'training':json.loads((output/'verification.json').read_text(encoding='utf-8')),
        'summaries':summaries,'iterations':iterations,'human_expert_labels':0,'default_policy_promoted':False,
        'rule_train_evidence':'Previously executed sealed reference_episodes.jsonl; not re-generated or claimed as a fresh benchmark',
        'interpretation':'Single-seed bounded candidate-policy training; comparison is descriptive, not a test of generalization or PPO superiority'}
    write(HERE/'results.json',result,fresh=True)
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
