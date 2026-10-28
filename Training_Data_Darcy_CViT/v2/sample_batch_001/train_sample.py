"""Sample only this batch's tasks and perform one bounded CPU PPO update."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE.parent))
import torch
from protocol import VERSION, REWARD_VERSION, digest, read_tasks, rows, verify_runtime, write
from environment import ToolEnvironment
from ppo_smoke import ActorCritic, policy_value, verify_rollout, gae
from preflight import preflight


def train(output):
    if (output/"behavior_policy.json").exists(): raise ValueError("Use a new output directory; preserve existing sampling evidence")
    if not preflight(HERE/"tasks_imported.json")["passed"]: raise ValueError("Sample task preflight failed")
    wanted = {task["task_id"] for task in rows(HERE/"tasks.jsonl")}
    tasks = [task for task in read_tasks("train", purpose="ppo", extension=HERE/"tasks_imported.json") if task["task_id"] in wanted]
    if len(tasks) != 3 or {t["task_id"] for t in tasks} != wanted: raise ValueError("Sample task selection mismatch")
    torch.set_num_threads(1); torch.manual_seed(2102801)
    model = ActorCritic().cpu()
    behavior = policy_value(model); identity = digest(behavior); catalog_hash = verify_runtime()
    write(output/"behavior_policy.json", behavior, fresh=True)
    records, episode_index = [], 0
    # Each case receives 32 actual policy samples. A collection-chunk limit is
    # external truncation, distinct from the task's own decision-budget terminal.
    for task in tasks:
        env = ToolEnvironment(task); obs, _ = env.reset()
        for local_index in range(32):
            features = env.features(obs); mask = [c["available"] for c in obs["candidates"]]
            with torch.no_grad():
                dist, value = model(torch.tensor([features]), torch.tensor([mask], dtype=torch.bool))
                action = dist.sample(); logp = dist.log_prob(action)
            index = int(action.item())
            after, reward, term, trunc, info = env.step(index)
            if local_index == 31 and not term and not trunc:
                after = env.truncate(); trunc = True
            next_features = env.features(after)
            with torch.no_grad(): next_value = 0.0 if term else float(model.value(torch.tensor([next_features])).item())
            records.append({"schema_version": "ppo_transition_v2", "source": "fresh_on_policy_cpu_smoke", "policy_split": "train",
                "task_id": task["task_id"], "task_hash": digest(task), "episode_index": episode_index, "sampling_index": len(records),
                "environment_version": VERSION, "reward_version": REWARD_VERSION, "tool_catalog_hash": catalog_hash,
                "behavior_policy_hash": identity, "observation": obs, "observation_hash": digest(obs), "features": features,
                "action_mask": mask, "action_index": index, "action": obs["candidates"][index],
                "behavior_log_probability": float(logp.item()), "value_estimate": float(value.item()), "reward": reward,
                "next_observation": after, "next_observation_hash": digest(after), "next_features": next_features,
                "next_value_estimate": next_value, "terminated": term, "truncated": trunc, "classification": info["classification"]})
            obs = after
            if term or trunc:
                episode_index += 1
                if local_index < 31: env = ToolEnvironment(task); obs, _ = env.reset()
    verified = verify_rollout(records, behavior, tasks=tasks)
    write(output/"rollout.jsonl", records, lines=True, fresh=True)
    advantages, returns = gae(*[[r[k] for r in records] for k in ("reward", "value_estimate", "next_value_estimate", "terminated", "truncated")])
    x = torch.tensor([r["features"] for r in records]); masks = torch.tensor([r["action_mask"] for r in records], dtype=torch.bool)
    actions = torch.tensor([r["action_index"] for r in records]); old = torch.tensor([r["behavior_log_probability"] for r in records])
    adv = torch.tensor((advantages-advantages.mean())/(advantages.std()+1e-8), dtype=torch.float32)
    targets = torch.tensor(returns, dtype=torch.float32)
    optimizer = torch.optim.Adam(model.parameters(), lr=.0003); losses = []
    for _ in range(2):
        for batch in torch.randperm(len(records)).split(32):
            dist, value = model(x[batch], masks[batch]); ratio = (dist.log_prob(actions[batch])-old[batch]).exp()
            loss = -torch.minimum(ratio*adv[batch], ratio.clamp(.8, 1.2)*adv[batch]).mean()+.25*(value-targets[batch]).square().mean()-.01*dist.entropy().mean()
            if not torch.isfinite(loss): raise ValueError("Nonfinite PPO loss")
            optimizer.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), .5); optimizer.step()
            losses.append(float(loss.detach()))
    updated = policy_value(model); write(output/"updated_policy.json", updated, fresh=True)
    result = {"passed": digest(updated) != identity, "task_sample_counts": {t: sum(r["task_id"] == t for r in records) for t in wanted},
        "sampled_transitions": len(records), "ppo_batch_updates": 1, "gradient_steps": len(losses), "losses": losses,
        "behavior_policy_hash": identity, "updated_policy_hash": digest(updated), "probabilities_and_values": verified,
        "terminal_transitions": sum(r["terminated"] for r in records), "external_truncations": sum(r["truncated"] for r in records),
        "human_expert_labels": 0, "real_scientific_executions": 0, "model_api_requests": 0,
        "default_policy_promoted": False, "scope": "Synthetic bounded candidate-policy training compatibility only; no efficacy or generalization claim"}
    write(output/"verification.json", result, fresh=True)
    print(json.dumps(result, ensure_ascii=False))
    if not result["passed"]: raise ValueError("PPO parameters did not change")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE/"ppo_run_001")
    args = parser.parse_args()
    train(args.output if args.output.is_absolute() else HERE/args.output)
