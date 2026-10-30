"""Posthoc action-trace diagnostics; does not train or select another checkpoint."""
from collections import Counter
from pathlib import Path
import json
import sys

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(BATCH));sys.path.insert(0,str(BATCH.parent))
import torch
from protocol import write,digest
from environment import ToolEnvironment
from ppo_smoke import load_policy
from train import load_batch


def main():
    torch.set_num_threads(1)
    results=json.loads((HERE/'evaluation_details.json').read_text(encoding='utf-8'))
    failed={r['task_id'] for r in results['ppo']['train'] if not r['success']}
    model=load_policy(json.loads((BATCH/'training_run_002/updated_policy.json').read_text(encoding='utf-8')))
    traces=[];frequent=Counter()
    for task in load_batch():
        if task['task_id'] not in failed:continue
        env=ToolEnvironment(task);obs,_=env.reset();steps=[];actions=Counter()
        while not env.terminated and not env.truncated:
            features=env.features(obs)
            with torch.no_grad():
                dist,_=model(torch.tensor([features]),torch.tensor([[c['available'] for c in obs['candidates']]],dtype=torch.bool))
            index=int(dist.probs.argmax(-1).item());candidate=obs['candidates'][index]
            top=torch.topk(dist.probs[0],3)
            after,reward,_,_,info=env.step(index);actions[candidate['action_id']]+=1
            steps.append({'step':env.steps,'action':candidate['action_id'],'reward':reward,
                'error':info['feedback']['error'],'features_hash':digest(features),
                'top_actions':[{'action':obs['candidates'][int(j)]['action_id'],'probability':float(p)} for p,j in zip(top.values,top.indices)]})
            obs=after
        frequent.update(actions)
        traces.append({'task_id':task['task_id'],'domain':task['public']['domain'],'family':task['public']['family'],
            'initial_fault':task['simulator']['initial_fault'],'classification':info['classification'],'action_counts':dict(actions),'steps':steps})
    result={'failed_tasks':len(failed),'traces':traces,'aggregate_actions':dict(frequent),
        'scope':'Posthoc greedy final-checkpoint diagnosis only; no causal attribution, retuning or checkpoint replacement'}
    write(HERE/'failure_analysis.json',result,fresh=True)
    print(json.dumps({'failed_tasks':len(failed),'aggregate_actions':dict(frequent),'task_summaries':[{k:v for k,v in t.items() if k!='steps'} for t in traces]}),flush=True)


if __name__=='__main__':main()
