"""Bounded scripted BC warm-start followed by fresh on-policy PPO over all 50 tasks."""
import argparse
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(HERE.parent))
import torch
from protocol import VERSION, REWARD_VERSION, digest, sha, rows, read_tasks, verify_runtime, write, expected_reward
from environment import ToolEnvironment
from ppo_smoke import ActorCritic, policy_value, load_policy, gae, verify_rollout


def load_batch():
    manifest=json.loads((HERE/'manifest.json').read_text(encoding='utf-8'))
    for name,h in manifest['artifact_sha256'].items():
        if sha(HERE/name)!=h: raise ValueError('Batch changed: '+name)
    wanted={t['task_id'] for t in rows(HERE/'tasks.jsonl')}
    loaded=read_tasks('train',purpose='ppo',extension=HERE/'tasks_imported.json')
    tasks=[t for t in loaded if t['task_id'] in wanted]
    if len(tasks)!=50 or len(wanted)!=50: raise ValueError('Exactly 50 declared batch tasks required')
    return tasks


def evaluate(model,tasks):
    records=[]
    model.eval()
    for i,task in enumerate(tasks):
        env=ToolEnvironment(task); obs,_=env.reset(); total=0; errors=0
        while not env.terminated and not env.truncated:
            with torch.no_grad():
                dist,_=model(torch.tensor([env.features(obs)]),torch.tensor([[c['available'] for c in obs['candidates']]],dtype=torch.bool))
            index=int(dist.probs.argmax(-1).item())
            obs,r,term,trunc,info=env.step(index); total+=r; errors+=bool(info['feedback']['error'])
        records.append({'task_id':task['task_id'],'classification':info['classification'],'success':info['success'],
                        'steps':env.steps,'return':total,'errors':errors})
        if (i+1)%10==0: print('training-task diagnostic evaluation',i+1,'/50',flush=True)
    return {'scope':'Greedy evaluation on the SAME 50 TRAINING tasks; not validation, blind testing or generalization evidence',
            'successes':sum(r['success'] for r in records),'tasks':len(records),'records':records}


def train(output,iterations=1,steps_per_task=16,bc_epochs=300,seed=281050):
    output=output.absolute()
    if output.exists(): raise ValueError('Use a new output directory; never overwrite previous weights')
    if not output.is_relative_to(HERE) or output.resolve()!=output: raise ValueError('Output must be a non-redirected new child of this batch')
    if not 1<=iterations<=20 or not 8<=steps_per_task<=80 or not 1<=bc_epochs<=2000: raise ValueError('Bounded training limits exceeded')
    tasks=load_batch()
    torch.set_num_threads(1);torch.manual_seed(seed)
    model=ActorCritic().cpu()
    initial=policy_value(model);write(output/'initial_policy.json',initial,fresh=True)
    labels=rows(HERE/'bc_reference.jsonl')
    x=torch.tensor([r['features'] for r in labels]); masks=torch.tensor([r['action_mask'] for r in labels],dtype=torch.bool)
    targets=torch.tensor([r['target_action_index'] for r in labels])
    optimizer=torch.optim.Adam(model.parameters(),lr=.003)
    bc_losses=[]
    for epoch in range(bc_epochs):
        dist,_=model(x,masks);loss=-dist.log_prob(targets).mean()
        optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);optimizer.step()
        bc_losses.append(float(loss.detach()))
    with torch.no_grad():
        d,_=model(x,masks); accuracy=float((d.probs.argmax(-1)==targets).float().mean())
    bc=policy_value(model);write(output/'bc_policy.json',bc,fresh=True)
    write(output/'bc_verification.json',{'source':'scripted_reference_not_expert','human_labels':0,'epochs':bc_epochs,
        'decisions':len(labels),'training_action_accuracy':accuracy,'first_loss':bc_losses[0],'last_loss':bc_losses[-1],
        'initial_hash':digest(initial),'bc_hash':digest(bc)},fresh=True)
    print('BC warm-start accuracy',accuracy,flush=True)
    optimizer=torch.optim.Adam(model.parameters(),lr=.0003)
    catalog_hash=verify_runtime();iterations_report=[]
    for iteration in range(iterations):
        folder=output/f'iteration_{iteration+1:03d}'
        behavior=policy_value(model);identity=digest(behavior)
        write(folder/'behavior_policy.json',behavior,fresh=True)
        records=[];episode_index=0;milestones=set();reward_recomputations=0
        for task_index,task in enumerate(tasks):
            env=ToolEnvironment(task);obs,_=env.reset();milestones=set()
            for local_index in range(steps_per_task):
                features=env.features(obs);mask=[c['available'] for c in obs['candidates']]
                with torch.no_grad():
                    dist,value=model(torch.tensor([features]),torch.tensor([mask],dtype=torch.bool))
                    action=dist.sample();logp=dist.log_prob(action)
                index=int(action.item());after,reward,term,trunc,info=env.step(index)
                reward_row={'action':obs['candidates'][index],'observation':obs,'feedback':info['feedback'],'classification':info['classification']}
                if abs(expected_reward(reward_row,milestones)-reward)>1e-9: raise ValueError('Actual environment reward mismatch')
                reward_recomputations+=1
                if local_index==steps_per_task-1 and not term and not trunc: after=env.truncate();trunc=True
                next_features=env.features(after)
                with torch.no_grad(): next_value=0.0 if term else float(model.value(torch.tensor([next_features])).item())
                records.append({'schema_version':'ppo_transition_v2','source':'fresh_on_policy_cpu_smoke','policy_split':'train',
                    'task_id':task['task_id'],'task_hash':digest(task),'episode_index':episode_index,'sampling_index':len(records),
                    'environment_version':VERSION,'reward_version':REWARD_VERSION,'tool_catalog_hash':catalog_hash,
                    'behavior_policy_hash':identity,'observation':obs,'observation_hash':digest(obs),'features':features,
                    'action_mask':mask,'action_index':index,'action':obs['candidates'][index],
                    'behavior_log_probability':float(logp.item()),'value_estimate':float(value.item()),'reward':reward,
                    'next_observation':after,'next_observation_hash':digest(after),'next_features':next_features,
                    'next_value_estimate':next_value,'terminated':term,'truncated':trunc,'classification':info['classification']})
                obs=after
                if term or trunc:
                    episode_index+=1
                    if local_index<steps_per_task-1: env=ToolEnvironment(task);obs,_=env.reset();milestones=set()
            if (task_index+1)%10==0: print('PPO iteration',iteration+1,'sampled tasks',task_index+1,'/50',flush=True)
        verified=verify_rollout(records,behavior,tasks=tasks)
        write(folder/'rollout.jsonl',records,lines=True,fresh=True)
        advantages,returns=gae(*[[r[k] for r in records] for k in ('reward','value_estimate','next_value_estimate','terminated','truncated')])
        x=torch.tensor([r['features'] for r in records]);mask=torch.tensor([r['action_mask'] for r in records],dtype=torch.bool)
        actions=torch.tensor([r['action_index'] for r in records]);old=torch.tensor([r['behavior_log_probability'] for r in records])
        adv=torch.tensor((advantages-advantages.mean())/(advantages.std()+1e-8),dtype=torch.float32);returns=torch.tensor(returns,dtype=torch.float32)
        losses=[]
        for epoch in range(4):
            for indices in torch.randperm(len(records)).split(64):
                dist,value=model(x[indices],mask[indices]);ratio=(dist.log_prob(actions[indices])-old[indices]).exp()
                loss=-torch.minimum(ratio*adv[indices],ratio.clamp(.8,1.2)*adv[indices]).mean()+.25*(value-returns[indices]).square().mean()-.01*dist.entropy().mean()
                if not torch.isfinite(loss): raise ValueError('Nonfinite training loss')
                optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);optimizer.step()
                losses.append(float(loss.detach()))
        updated=policy_value(model);write(folder/'updated_policy.json',updated,fresh=True)
        proof={'passed':digest(updated)!=identity,'sampling':verified,'reward_recomputations':reward_recomputations,
            'task_sample_counts':{t['task_id']:sum(r['task_id']==t['task_id'] for r in records) for t in tasks},
            'behavior_hash':identity,'updated_hash':digest(updated),'gradient_steps':len(losses),'losses':losses,
            'successful_episode_ends':sum(r['classification'] in {'completed_mock_research_loop','justified_stop'} for r in records),
            'external_truncations':sum(r['truncated'] for r in records)}
        if not proof['passed']: raise ValueError('PPO parameters did not change')
        write(folder/'verification.json',proof,fresh=True);iterations_report.append(proof)
    write(output/'updated_policy.json',policy_value(model),fresh=True)
    final_eval=evaluate(model,tasks);write(output/'training_task_evaluation.json',final_eval,fresh=True)
    result={'passed':all(r['passed'] for r in iterations_report),'training_tasks':50,'bc_epochs':bc_epochs,
        'ppo_iterations':iterations,'transitions':iterations*50*steps_per_task,'gradient_steps':sum(r['gradient_steps'] for r in iterations_report),
        'steps_per_task_per_iteration':steps_per_task,'seed':seed,'training_task_successes':final_eval['successes'],
        'human_expert_labels':0,'new_independent_sources':0,'real_scientific_executions':0,'model_api_requests':0,
        'default_policy_promoted':False,'frozen_environment_and_reward_unchanged':True,
        'rollout_source_note':'fresh_on_policy_cpu_smoke is the pinned v2 schema tag; this is bounded synthetic candidate-policy training, not a proven production strategy',
        'efficacy_claim':'No independent held-out evaluation; no claimed improvement over rules or generalization'}
    write(output/'verification.json',result,fresh=True);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=HERE/'training_run_001')
    p.add_argument('--iterations',type=int,default=1);p.add_argument('--steps-per-task',type=int,default=16)
    p.add_argument('--bc-epochs',type=int,default=300);p.add_argument('--seed',type=int,default=281050)
    a=p.parse_args();train(a.output if a.output.is_absolute() else HERE/a.output,a.iterations,a.steps_per_task,a.bc_epochs,a.seed)
