"""CPU actor-critic with masked PPO clipping and terminal-aware GAE.

No language-model weights or CViT weights are loaded. The trainable parameters
belong only to the small decision policy in this isolated laboratory.
"""
import random
import numpy as np
import torch
from torch import nn
from .adapter_v3 import ACTIONS_V3, FEATURES_V3, VERSION_V3, encode
from .contracts import digest


def setup_seed(seed):
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)


class ActorCritic(nn.Module):
    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(len(FEATURES_V3), 96), nn.Tanh(), nn.Linear(96, 96), nn.Tanh())
        self.actor = nn.Linear(96, len(ACTIONS_V3))
        self.critic = nn.Linear(96, 1)

    def forward(self, features, masks):
        context = self.body(features)
        logits = self.actor(context).masked_fill(~masks, -1e9)
        return torch.distributions.Categorical(logits=logits), self.critic(context).squeeze(-1)


def tensors(observations):
    return (torch.tensor([encode(obs) for obs in observations], dtype=torch.float32, device="cpu"),
            torch.tensor([obs["mask"] for obs in observations], dtype=torch.bool, device="cpu"))


class NeuralPolicy:
    def __init__(self, network):
        self.network = network
    def choose(self, obs):
        with torch.no_grad():
            distribution, _ = self.network(*tensors([obs]))
            return ACTIONS_V3[int(distribution.logits.argmax(-1).item())]


def policy_value(network):
    return {"version": VERSION_V3, "actions": list(ACTIONS_V3), "features": list(FEATURES_V3), "architecture": "96_tanh_96_tanh_actor_critic",
            "parameters": {key: value.detach().cpu().tolist() for key, value in network.state_dict().items()}, "device": "cpu"}


def load_policy(value):
    if value.get("version") != VERSION_V3 or value.get("actions") != list(ACTIONS_V3) or value.get("features") != list(FEATURES_V3):
        raise ValueError("Incompatible policy artifact")
    network = ActorCritic()
    state = {key: torch.tensor(item, dtype=torch.float32) for key, item in value["parameters"].items()}
    if any(not torch.isfinite(t).all() for t in state.values()):
        raise ValueError("Nonfinite policy")
    network.load_state_dict(state)
    network.eval()
    return network


def gae(rewards, values, next_values, dones, *, gamma=.99, lam=.95):
    rewards, values, next_values, dones = [np.asarray(v, dtype=np.float32) for v in (rewards, values, next_values, dones)]
    if not (rewards.shape == values.shape == next_values.shape == dones.shape):
        raise ValueError("GAE arrays must have the same shape")
    advantages = np.zeros_like(rewards)
    running = 0.
    for i in range(len(rewards)-1, -1, -1):
        continuation = 1.-dones[i]
        delta = rewards[i]+gamma*next_values[i]*continuation-values[i]
        running = delta+gamma*lam*continuation*running
        advantages[i] = running
    return advantages, advantages+values


def clipped_loss(logp, old_logp, advantages, epsilon=.2):
    ratio = (logp-old_logp).exp()
    return -torch.minimum(ratio*advantages, ratio.clamp(1-epsilon, 1+epsilon)*advantages).mean()


def ppo_update(network, optimizer, batch, *, epochs=4, minibatch=128):
    advantages, returns = gae(batch["rewards"], batch["values"], batch["next_values"], batch["dones"])
    adv = torch.tensor((advantages-advantages.mean())/(advantages.std()+1e-8), dtype=torch.float32)
    target = torch.tensor(returns)
    features, masks = tensors(batch["observations"])
    actions = torch.tensor(batch["actions"], dtype=torch.long)
    old_logp = torch.tensor(batch["logp"])
    stats = []
    for _ in range(epochs):
        for idx in torch.randperm(len(actions)).split(minibatch):
            distribution, value = network(features[idx], masks[idx])
            logp = distribution.log_prob(actions[idx])
            actor = clipped_loss(logp, old_logp[idx], adv[idx])
            critic = .5*(value-target[idx]).square().mean()
            entropy = distribution.entropy().mean()
            loss = actor+.5*critic-.01*entropy
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite PPO loss")
            optimizer.zero_grad(); loss.backward()
            norm = nn.utils.clip_grad_norm_(network.parameters(), .5)
            optimizer.step()
            stats.append([float(actor.detach()), float(critic.detach()), float(entropy.detach()), float(norm)])
    return {"policy_loss": float(np.mean([s[0] for s in stats])), "value_loss": float(np.mean([s[1] for s in stats])),
            "entropy": float(np.mean([s[2] for s in stats])), "gradient_norm": float(np.mean([s[3] for s in stats]))}
