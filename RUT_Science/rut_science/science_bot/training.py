"""Small CPU masked PPO and behavioral cloning; fixed LLM is never updated.

Stores exact candidate/mask features, old probabilities and values per rollout.
All minibatches are fresh on-policy data. Finite budget exhaustion terminates;
collector window boundaries bootstrap from the still-live environment.
"""
import argparse
import copy
from dataclasses import replace
import json
import gzip
from pathlib import Path
import random
import time
import numpy as np
import torch
from .contracts import BudgetedResearchSpec, K_MAX, catalog
from .numerics import load_data, TOOL_VERSION
from .environment import BudgetedEnvironment
from .cache import OutcomeCache
from .policies import RulePolicy, encode, make_network, tensor_batch, FEATURE_VERSION
from ..darcy_workflow import file_hash
from ..util import digest, write_json


def run_episode(spec, policy, cache=None, collect=False):
    env = BudgetedEnvironment(spec, load_data(spec), cache=cache)
    rows, total = [], 0
    while not env.done:
        obs = env.observe()
        action = policy.choose(obs)
        if collect:
            rows.append((encode(obs), next(i for i, c in enumerate(obs["candidates"]) if c["id"] == action)))
        result = env.step_action(action, obs["observation_ref"], f"episode_{env.state['version']}")
        total += result["reward"]
    return env.state["report"], total, rows


def save_policy(network, folder, metadata):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    torch.save(network.state_dict(), folder/"weights.pt")
    sources = {p.name: file_hash(p) for p in Path(__file__).parent.glob("*.py")}
    write_json(folder/"manifest.json", {"feature_version": FEATURE_VERSION, "k_max": K_MAX,
        "weights_hash": file_hash(folder/"weights.pt"), "normalizer": "fixed_public_scales_no_test_fitting",
        "source_hashes": sources, "tool_version": TOOL_VERSION, "catalog_hash": digest(catalog()),
        "fixed_llm_updated": False, **metadata})


def train_bc(folder, cache, seed=11):
    torch.manual_seed(seed)
    dataset, records = [], []
    # Demonstrators are selected on training tasks only, not final-test oracles.
    for group in range(24):
        for instance in (11, 22, 33):
            for budget in (6, 10, 14):
                spec = BudgetedResearchSpec(group=group, task_seed=instance, compute_units=budget)
                candidates = [run_episode(spec, RulePolicy(mode, seed), cache, collect=True)
                              for mode in ("cheap", "dense", "adaptive", "search")]
                selected = max(range(len(candidates)), key=lambda i: candidates[i][1])
                dataset.extend(candidates[selected][2])
                records.append({"group": group, "instance": instance, "budget": budget,
                                "teacher": selected, "returns": [c[1] for c in candidates]})
    network = make_network()
    optimizer = torch.optim.Adam(network.parameters(), lr=3e-4)
    rng = np.random.default_rng(seed)
    losses = []
    for epoch in range(25):
        for start in range(0, len(dataset), 64):
            indices = rng.permutation(len(dataset))[start:start+64]
            batch = tensor_batch([dataset[i][0] for i in indices])
            actions = torch.tensor([dataset[i][1] for i in indices])
            distribution, _ = network(batch)
            loss = -distribution.log_prob(actions).mean()
            optimizer.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(network.parameters(), 0.5)
            optimizer.step()
        losses.append(float(loss.detach()))
    save_policy(network, folder, {"algorithm": "behavioral_cloning", "seed": seed, "examples": len(dataset),
                                  "training_groups": list(range(24)), "split": "train", "losses": losses,
                                  "teacher_protocol": "highest_training_return_of_four_public_rules"})
    write_json(Path(folder)/"demonstrations.json", records)
    return network


def train_ppo(folder, cache, seed=11, steps=20000, warm=None, fault_training=True, ablation=None):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    network = make_network()
    if warm:
        network.load_state_dict(torch.load(Path(warm)/"weights.pt", weights_only=True))
    optimizer = torch.optim.Adam(network.parameters(), lr=3e-4)
    folder = Path(folder)
    (folder/"rollouts").mkdir(parents=True, exist_ok=True)
    records, episodes, env, seen, updates = [], [], None, 0, 0
    best_state, best_dev, best_step = None, -float("inf"), 0
    before_weights = digest({k: v.detach().tolist() for k, v in network.state_dict().items()})
    started = time.perf_counter()
    while seen < steps:
        rollout, episode_reward = [], 0
        for _ in range(min(512, steps-seen)):
            if env is None or env.done:
                spec = BudgetedResearchSpec(group=int(rng.integers(24)), task_seed=int(rng.integers(1, 100000)),
                    compute_units=int(rng.choice([6, 10, 14])), fault_rate=0.10 if fault_training else 0)
                env = BudgetedEnvironment(spec, load_data(spec), cache=cache)
            public = env.observe(permutation=rng.permutation(18).tolist())
            if ablation == "no_diagnostics":
                for i, c in enumerate(public["candidates"]):
                    if c["kind"] in {"diagnose_inputs", "diagnose_residuals"}:
                        c["legal"] = False; public["mask"][i] = False
            encoded = encode(public, ablation)
            with torch.no_grad():
                distribution, value = network(tensor_batch([encoded]))
                action = distribution.sample()
                old_lp = distribution.log_prob(action)
            chosen = public["candidates"][int(action)]["id"]
            result = env.step_action(chosen, public["observation_ref"], f"train_{env.state['version']}")
            rollout.append({"observation": encoded, "action": int(action), "old_log_prob": float(old_lp),
                            "old_value": float(value), "reward": result["reward"], "terminated": result["terminated"],
                            "truncated": False, "policy_version": updates, "env_version": TOOL_VERSION,
                            "data_identity": env.data.identity, "spec_hash": digest(spec.to_dict()),
                            "ledger": {k: env.state[k] for k in ("cu", "attempts", "requests", "tokens")},
                            "candidate_snapshot": public["candidates"], "observation_ref": public["observation_ref"]})
            seen += 1
            episode_reward += result["reward"]
            if env.done:
                episodes.append({"step": seen, "success": env.state["report"]["scientific_success"],
                                 "cost": env.cost(), "sealed_error": env.state["report"]["sealed_error"]})
        with torch.no_grad():
            next_value = 0.0 if env.done else float(network(tensor_batch([encode(env.observe(), ablation)]))[1])
        advantage, advantages = 0.0, []
        for t in reversed(rollout):
            keep = 0.0 if t["terminated"] else 1.0
            delta = t["reward"] + keep*next_value - t["old_value"]
            advantage = delta + keep*0.95*advantage
            advantages.append(advantage)
            next_value = t["old_value"]
        advantages = torch.tensor(list(reversed(advantages)), dtype=torch.float32)
        values = torch.tensor([t["old_value"] for t in rollout])
        returns = advantages+values
        advantages = (advantages-advantages.mean())/(advantages.std()+1e-8)
        batch = tensor_batch([t["observation"] for t in rollout])
        actions = torch.tensor([t["action"] for t in rollout])
        old_lp = torch.tensor([t["old_log_prob"] for t in rollout])
        rollout_path = folder/"rollouts"/f"{updates:04d}"
        np.savez_compressed(str(rollout_path)+".npz", **{k: v.numpy() for k, v in batch.items()},
                            actions=actions.numpy(), old_log_prob=old_lp.numpy(), values=values.numpy(),
                            returns=returns.numpy(), rewards=np.asarray([t["reward"] for t in rollout]),
                            terminated=np.asarray([t["terminated"] for t in rollout]))
        with gzip.open(str(rollout_path)+".json.gz", "wt", encoding="utf-8") as stream:
            json.dump([{k: v for k, v in t.items() if k != "observation"} for t in rollout], stream)
        torch.save(network.state_dict(), folder/"last_rollout_policy.pt")
        with torch.no_grad():
            initial_lp = network(batch)[0].log_prob(actions)
            consistency = float((initial_lp-old_lp).abs().max())
            if consistency > 1e-5:
                raise RuntimeError("Old policy log probability mismatch")
        max_kl = 0.0
        for epoch in range(4):
            permutation = rng.permutation(len(rollout))
            for start in range(0, len(rollout), 64):
                idx = torch.tensor(permutation[start:start+64])
                distribution, value = network({k: v[idx] for k, v in batch.items()})
                lp = distribution.log_prob(actions[idx])
                ratio = torch.exp(lp-old_lp[idx])
                pg = -torch.minimum(ratio*advantages[idx], ratio.clamp(0.8, 1.2)*advantages[idx]).mean()
                loss = pg + 0.5*(value-returns[idx]).square().mean() - 0.01*distribution.entropy().mean()
                if not torch.isfinite(loss):
                    raise RuntimeError("Nonfinite PPO objective")
                optimizer.zero_grad(); loss.backward()
                grad = torch.nn.utils.clip_grad_norm_(network.parameters(), 0.5)
                if not torch.isfinite(grad):
                    raise RuntimeError("Nonfinite PPO gradient")
                optimizer.step()
                kl = float(((ratio-1)-(lp-old_lp[idx])).mean().detach())
                max_kl = max(max_kl, kl)
            if max_kl > 0.03:
                break
        updates += 1
        recent = episodes[-100:]
        record = {"steps": seen, "updates": updates, "loss": float(loss.detach()), "kl": max_kl,
                  "old_log_prob_max_error": consistency, "success_last_100": np.mean([e["success"] for e in recent]).item(),
                  "cost_last_100": np.mean([e["cost"] for e in recent]).item()}
        records.append(record)
        if updates % 10 == 0 or seen == steps:
            class CurrentPolicy:
                def choose(self, observation):
                    if ablation == "no_diagnostics":
                        observation = copy.deepcopy(observation)
                        for i, c in enumerate(observation["candidates"]):
                            if c["kind"] in {"diagnose_inputs", "diagnose_residuals"}:
                                c["legal"] = False; observation["mask"][i] = False
                    with torch.no_grad():
                        dist, _ = network(tensor_batch([encode(observation, ablation)]))
                    return observation["candidates"][int(dist.logits.argmax(-1))]["id"]
            dev_rows = [run_episode(BudgetedResearchSpec(split="dev", group=g, compute_units=b), CurrentPolicy(), cache)
                        for g in range(8) for b in (6, 10, 14)]
            dev_score = float(np.mean([row[1] for row in dev_rows]))
            record["dev_return"] = dev_score
            record["dev_success"] = float(np.mean([row[0]["scientific_success"] for row in dev_rows]))
            if dev_score > best_dev:
                best_dev, best_step = dev_score, seen
                best_state = copy.deepcopy(network.state_dict())
            print(json.dumps({"seed": seed, "warm": bool(warm), **record}), flush=True)
    network.load_state_dict(best_state)
    after_weights = digest({k: v.detach().tolist() for k, v in network.state_dict().items()})
    if before_weights == after_weights:
        raise RuntimeError("PPO did not update parameters")
    metadata = {"algorithm": "bc_masked_ppo" if warm else "masked_ppo_scratch", "seed": seed,
                "actual_transitions": seen, "updates": updates, "training_groups": list(range(24)),
                "split": "train", "weights_changed": True, "initial_hash": before_weights,
                "final_hash": after_weights, "fault_training": fault_training, "gamma": 1.0,
                "ablation": ablation, "reward_shaping": False,
                "checkpoint_steps": best_step, "selected_on_meta_dev": True, "dev_return": best_dev,
                "rollout_storage": "all_transitions_npz_plus_frozen_candidate_mapping_gzip",
                "elapsed_seconds": time.perf_counter()-started, "batch_size": 512, "minibatch_size": 64,
                "epochs": 4, "learning_rate": 3e-4, "clip_range": 0.2, "gae_lambda": 0.95}
    save_policy(network, folder, metadata)
    write_json(Path(folder)/"learning_curve.json", records)
    write_json(Path(folder)/"episodes.json", episodes)
    # Exact final rollout for independent probability / mapping checks.
    serializable = [{**{k: v for k, v in t.items() if k != "observation"},
                     "observation": {k: v.tolist() for k, v in t["observation"].items()}} for t in rollout]
    write_json(Path(folder)/"last_rollout.json", serializable)
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models/planner/v1"))
    parser.add_argument("--steps", type=int, default=20000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[11, 22, 33, 44, 55])
    args = parser.parse_args(argv)
    if args.steps < 512:
        parser.error("At least one complete pilot rollout (512 transitions) required")
    torch.set_num_threads(1)
    cache = OutcomeCache()
    train_bc(args.output/"bc", cache)
    for seed in args.seeds:
        for name, warm in (("ppo_scratch", None), ("bc_ppo", args.output/"bc")):
            train_ppo(args.output/f"{name}_{seed}", cache, seed, args.steps, warm)
        cache.memory.clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
