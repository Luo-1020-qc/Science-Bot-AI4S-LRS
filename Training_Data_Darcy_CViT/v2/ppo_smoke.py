"""One fresh CPU rollout batch and clipped PPO update, solely integration verification."""
import json
import math
import random
import numpy as np
import torch
from torch import nn
from protocol import ROOT, VERSION, REWARD_VERSION, ACTION_IDS, FEATURE_NAMES, canonical, digest, read_tasks, verify_runtime, validate_observation, write
from environment import ToolEnvironment


class ActorCritic(nn.Module):
    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(len(FEATURE_NAMES), 64), nn.Tanh(), nn.Linear(64, 64), nn.Tanh())
        self.actor = nn.Linear(64, len(ACTION_IDS))
        self.critic = nn.Linear(64, 1)

    def forward(self, features, mask):
        context = self.body(features)
        logits = self.actor(context).masked_fill(~mask, -1e9)
        return torch.distributions.Categorical(logits=logits), self.critic(context).squeeze(-1)

    def value(self, features):
        return self.critic(self.body(features)).squeeze(-1)


def policy_value(model):
    return {"version": VERSION, "feature_names": list(FEATURE_NAMES), "action_ids": list(ACTION_IDS),
            "architecture": "32_feature_64_tanh_64_tanh_actor_critic_cpu", "parameters": {k: v.detach().cpu().tolist() for k, v in model.state_dict().items()}}


def load_policy(value):
    if value["version"] != VERSION or value["feature_names"] != list(FEATURE_NAMES) or value["action_ids"] != list(ACTION_IDS):
        raise ValueError("Policy protocol mismatch")
    model = ActorCritic()
    state = {k: torch.tensor(v, dtype=torch.float32) for k, v in value["parameters"].items()}
    if any(not torch.isfinite(v).all() for v in state.values()): raise ValueError("Nonfinite behavior policy")
    model.load_state_dict(state); model.eval()
    return model


def gae(rewards, values, next_values, terminated, truncated, gamma=.99, lam=.95):
    arrays = [np.asarray(x, dtype=np.float64) for x in (rewards, values, next_values, terminated, truncated)]
    if len({a.shape for a in arrays}) != 1 or any(not np.isfinite(a).all() for a in arrays):
        raise ValueError("Invalid GAE arrays")
    rewards, values, next_values, terminated, truncated = arrays
    advantages = np.zeros_like(rewards)
    running = 0.0
    for i in range(len(rewards)-1, -1, -1):
        delta = rewards[i]+gamma*next_values[i]*(1-terminated[i])-values[i]
        # External truncation bootstraps its final state, but the next reset
        # belongs to another episode and cannot enter the lambda recursion.
        running = delta+gamma*lam*(1-max(terminated[i], truncated[i]))*running
        advantages[i] = running
    return advantages, advantages+values


def verify_rollout(records, behavior, tasks=None):
    if not records: raise ValueError("Empty rollout is not a PPO sampling batch")
    model = load_policy(behavior)
    identity, catalog_hash = digest(behavior), verify_runtime()
    known_tasks = {task["task_id"]: task for task in (tasks if tasks is not None else read_tasks("train", purpose="ppo"))}
    previous = None
    for sampling_index, row in enumerate(records):
        validate_observation(row["observation"]); validate_observation(row["next_observation"])
        task = known_tasks.get(row["task_id"])
        if task is None or task["policy_split"] != "train" or digest(task) != row["task_hash"]:
            raise ValueError("Rollout task identity/hash is not an allowed training task")
        if row["sampling_index"] != sampling_index or type(row["episode_index"]) is not int:
            raise ValueError("Rollout sampling/episode order mismatch")
        if type(row["terminated"]) is not bool or type(row["truncated"]) is not bool:
            raise ValueError("Termination/truncation must be explicit booleans")
        if previous is not None:
            boundary = previous["terminated"] or previous["truncated"]
            if row["episode_index"] != previous["episode_index"]+int(boundary):
                raise ValueError("Rollout episode boundary is inconsistent")
            if not boundary and (row["task_id"] != previous["task_id"] or row["observation"] != previous["next_observation"]):
                raise ValueError("Rollout state chain is broken")
        if row["features"] != ToolEnvironment.features(None, row["observation"]) or row["next_features"] != ToolEnvironment.features(None, row["next_observation"]):
            raise ValueError("Features are not derived from the public observation")
        if row["source"] != "fresh_on_policy_cpu_smoke" or row["behavior_policy_hash"] != identity or row["tool_catalog_hash"] != catalog_hash:
            raise ValueError("Behavior policy/source/catalog mismatch")
        if row["policy_split"] != "train" or row["environment_version"] != VERSION or row["reward_version"] != REWARD_VERSION:
            raise ValueError("Rollout split/protocol mismatch")
        mask, index = row["action_mask"], row["action_index"]
        if mask != [candidate["available"] for candidate in row["observation"]["candidates"]] or any(type(v) is not bool for v in mask):
            raise ValueError("Recorded mask differs from public host permissions")
        if type(index) is not int or not 0 <= index < len(ACTION_IDS) or not mask[index] or row["action"] != row["observation"]["candidates"][index]:
            raise ValueError("Action not sampled from its recorded candidate mask")
        if any(type(row[k]) not in (int, float) or not math.isfinite(row[k]) for k in ("behavior_log_probability", "value_estimate", "next_value_estimate", "reward")):
            raise ValueError("PPO probabilities, values and rewards must be actual finite values")
        with torch.no_grad():
            dist, value = model(torch.tensor([row["features"]]), torch.tensor([mask], dtype=torch.bool))
            logp = float(dist.log_prob(torch.tensor([index])).item())
        if abs(logp-row["behavior_log_probability"]) > 1e-6 or abs(float(value.item())-row["value_estimate"]) > 1e-6:
            raise ValueError("Probability or value does not match the saved behavior policy")
        expected_next = 0.0 if row["terminated"] else float(model.value(torch.tensor([row["next_features"]])).item())
        if abs(expected_next-row["next_value_estimate"]) > 1e-6:
            raise ValueError("Wrong bootstrap at termination/truncation")
        if digest(row["observation"]) != row["observation_hash"] or digest(row["next_observation"]) != row["next_observation_hash"]:
            raise ValueError("Observation identity mismatch")
        previous = row
    return {"records": len(records), "all_behavior_log_probs_recomputed": True, "all_values_recomputed": True,
        "training_task_hashes_verified": True, "public_masks_verified": True, "state_chains_verified": True}


def smoke(steps=64, output=None, extension=None):
    if not 8 <= steps <= 256:
        raise ValueError("Smoke verification is bounded to 8..256 steps, not a research training run")
    folder = output or ROOT/"ppo_smoke"
    if (folder/"behavior_policy.json").exists():
        raise ValueError("Sampling batch exists; use verification or a new explicit output directory")
    torch.set_num_threads(1)
    torch.manual_seed(21028)
    rng = random.Random(21028)
    tasks = read_tasks("train", purpose="ppo", extension=extension)
    model = ActorCritic().cpu()
    behavior = policy_value(model)
    identity, catalog_hash = digest(behavior), verify_runtime()
    write(folder/"behavior_policy.json", behavior, fresh=True)
    records, ep_index = [], 0
    task = rng.choice(tasks); env = ToolEnvironment(task); observation, _ = env.reset()
    for i in range(steps):
        features = env.features(observation)
        mask = [row["available"] for row in observation["candidates"]]
        with torch.no_grad():
            distribution, value = model(torch.tensor([features]), torch.tensor([mask], dtype=torch.bool))
            action = distribution.sample(); logp = distribution.log_prob(action)
        index = int(action.item())
        after, reward, terminated, truncated, info = env.step(index)
        next_features = env.features(after)
        with torch.no_grad():
            next_value = 0.0 if terminated else float(model.value(torch.tensor([next_features])).item())
        records.append({"schema_version": "ppo_transition_v2", "source": "fresh_on_policy_cpu_smoke", "policy_split": "train",
            "task_id": task["task_id"], "task_hash": digest(task), "episode_index": ep_index, "sampling_index": i,
            "environment_version": VERSION, "reward_version": REWARD_VERSION, "tool_catalog_hash": catalog_hash,
            "behavior_policy_hash": identity, "observation": observation, "observation_hash": digest(observation),
            "features": features, "action_mask": mask, "action_index": index, "action": observation["candidates"][index],
            "behavior_log_probability": float(logp.item()), "value_estimate": float(value.item()),
            "reward": reward, "next_observation": after, "next_observation_hash": digest(after), "next_features": next_features,
            "next_value_estimate": next_value, "terminated": terminated, "truncated": truncated, "classification": info["classification"]})
        observation = after
        if terminated or truncated:
            ep_index += 1; task = rng.choice(tasks); env = ToolEnvironment(task); observation, _ = env.reset()
    verified = verify_rollout(records, behavior, tasks=tasks)
    write(folder/"rollout.jsonl", records, lines=True, fresh=True)
    advantages, returns = gae([r["reward"] for r in records], [r["value_estimate"] for r in records], [r["next_value_estimate"] for r in records],
                             [r["terminated"] for r in records], [r["truncated"] for r in records])
    x = torch.tensor([r["features"] for r in records]); masks = torch.tensor([r["action_mask"] for r in records], dtype=torch.bool)
    actions = torch.tensor([r["action_index"] for r in records]); old_logp = torch.tensor([r["behavior_log_probability"] for r in records])
    adv = torch.tensor((advantages-advantages.mean())/(advantages.std()+1e-8), dtype=torch.float32)
    target = torch.tensor(returns, dtype=torch.float32)
    optimizer = torch.optim.Adam(model.parameters(), lr=.0003)
    losses = []
    for _ in range(2):
        for indices in torch.randperm(len(records)).split(32):
            distribution, value = model(x[indices], masks[indices])
            ratio = (distribution.log_prob(actions[indices])-old_logp[indices]).exp()
            clipped = ratio.clamp(.8, 1.2)
            actor = -torch.minimum(ratio*adv[indices], clipped*adv[indices]).mean()
            critic = .5*(value-target[indices]).square().mean()
            loss = actor+.5*critic-.01*distribution.entropy().mean()
            if not torch.isfinite(loss): raise ValueError("Nonfinite PPO loss")
            optimizer.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), .5); optimizer.step()
            losses.append(float(loss.detach()))
    updated = policy_value(model)
    write(folder/"updated_policy.json", updated, fresh=True)
    result = {"version": VERSION, "passed": digest(updated) != identity, "sampled_transitions": len(records), "ppo_batch_updates": 1,
        "minibatch_gradient_steps": len(losses), "losses": losses, "behavior_policy_hash": identity,
        "updated_policy_hash": digest(updated), "parameters_changed": digest(updated) != identity,
        "verification": verified, "terminated_episodes": sum(r["terminated"] for r in records),
        "scope": "Mechanical CPU integration smoke, no efficacy or generalization claim", "real_scientific_executions": 0,
        "real_model_api_requests": 0, "formal_research_training_transitions": 0, "smoke_training_transitions_separately_recorded": len(records)}
    write(folder/"verification.json", result, fresh=True)
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=64)
    parser.add_argument("--output", type=__import__("pathlib").Path)
    parser.add_argument("--extension", type=__import__("pathlib").Path)
    args = parser.parse_args()
    smoke(args.steps, args.output, args.extension)
