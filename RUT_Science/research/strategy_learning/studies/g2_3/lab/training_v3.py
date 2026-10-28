"""Fixed-budget BC, BC+PPO and scratch PPO; development-only model selection."""
from copy import deepcopy
import json
import random
import time
from pathlib import Path
import numpy as np
import torch

from .guard import LAB, file_hash, write_json
from .contracts import digest
from .suite_tasks import load_split, verify_bank
from .adapter_v3 import ACTIONS_V3, FEATURES_V3, SuiteEnvironment, SuiteRule, evaluate, encode
from .ppo import ActorCritic, NeuralPolicy, tensors, setup_seed, policy_value, load_policy, ppo_update

CONFIG = {"version": "g2_3_training_v1", "seeds": [21, 37, 59], "device": "cpu", "threads": 1,
          "bc_epochs": 100, "bc_lr": .001, "bc_evaluate_epochs": [20, 40, 60, 80, 100],
          "ppo_updates": 40, "rollout_steps": 512, "ppo_lr": .0003, "ppo_epochs": 4,
          "minibatch": 128, "gamma": .99, "gae_lambda": .95, "clip_epsilon": .2,
          "entropy_weight": .01, "critic_weight": .5, "max_gradient_norm": .5,
          "evaluate_updates": [0, 10, 20, 30, 40], "model_selection": "development success, then fewer blocked attempts, then fewer decisions",
          "source_labels": "scripted_reference_not_human_experts", "real_tools_connected": False}


def metric_key(report):
    return (report["success_rate"], -report["blocked_attempts"], -report["mean_decisions"])


def prepare_training():
    path = LAB/"evidence/training_config.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != CONFIG:
            raise ValueError("Fixed training configuration changed; create another isolated experiment")
    else:
        write_json(path, CONFIG)
    return CONFIG


def reference_demonstrations(tasks):
    rows = []
    rule = SuiteRule()
    for task in tasks:
        env = SuiteEnvironment(task)
        obs = env.reset()
        while not env.inner.done:
            action = rule.choose(obs)
            if not obs["mask"][ACTIONS_V3.index(action)]:
                raise ValueError("Reference action violates host mask: "+action)
            rows.append({"task_id": task["id"], "domain": task["domain"], "features": encode(obs), "mask": obs["mask"],
                         "action": ACTIONS_V3.index(action), "label_source": "scripted_reference_not_human_experts"})
            obs, _, _, _ = env.step(action)
    return rows


def _progress(**value):
    write_json(LAB/"evidence/progress.json", {"date": "2026-10-26", **value})


def train_bc(seed, tasks, development, rows):
    folder = LAB/"models"/f"seed_{seed}"/"bc"
    done = folder/"manifest.json"
    if done.exists():
        return json.loads(done.read_text(encoding="utf-8"))
    setup_seed(seed)
    network = ActorCritic()
    optimizer = torch.optim.Adam(network.parameters(), lr=CONFIG["bc_lr"])
    x = torch.tensor([row["features"] for row in rows], dtype=torch.float32)
    masks = torch.tensor([row["mask"] for row in rows], dtype=torch.bool)
    y = torch.tensor([row["action"] for row in rows], dtype=torch.long)
    best_key, selected_epoch = (-1, -1e9, -1e9), None
    curve, best = [], None
    started = time.perf_counter()
    for epoch in range(1, CONFIG["bc_epochs"]+1):
        distribution, _ = network(x, masks)
        loss = -distribution.log_prob(y).mean()
        optimizer.zero_grad(); loss.backward(); optimizer.step()
        if epoch in CONFIG["bc_evaluate_epochs"]:
            report, _ = evaluate(NeuralPolicy(network), development)
            key = metric_key(report)
            curve.append({"epoch": epoch, "loss": float(loss.detach()), "development": report})
            if key > best_key:
                best_key, best, selected_epoch = key, policy_value(network), epoch
            _progress(phase="bc", seed=seed, epoch=epoch, development_success=report["success_rate"])
    write_json(folder/"policy.json", best)
    manifest = {"algorithm": "behavior_cloning", "seed": seed, "selected_epoch": selected_epoch,
                "policy_hash": digest(best), "training_rows": len(rows), "train_tasks_hash": digest(tasks),
                "development_tasks_hash": digest(development), "human_expert_labels": 0, "heldout_used": False,
                "cpu_seconds": time.perf_counter()-started, "device": "cpu", "epochs": CONFIG["bc_epochs"]}
    write_json(folder/"curve.json", curve)
    write_json(done, manifest)
    return manifest


def collect(network, tasks, seed, update, steps):
    rng = random.Random(seed*10000+update)
    task = rng.choice(tasks)
    env = SuiteEnvironment(task)
    obs = env.reset()
    batch = {key: [] for key in ("observations", "actions", "logp", "values", "next_values", "rewards", "dones", "task_ids")}
    completed = 0
    for _ in range(steps):
        with torch.no_grad():
            distribution, value = network(*tensors([obs]))
            action = distribution.sample()
            logp = distribution.log_prob(action)
        next_obs, reward, done, info = env.step(int(action.item()))
        if done:
            next_value = 0.
        else:
            with torch.no_grad():
                _, result = network(*tensors([next_obs]))
                next_value = float(result.item())
        for key, item in (("observations", obs), ("actions", int(action.item())), ("logp", float(logp.item())),
                          ("values", float(value.item())), ("next_values", next_value), ("rewards", float(reward)),
                          ("dones", float(done)), ("task_ids", task["id"])):
            batch[key].append(item)
        obs = next_obs
        if done:
            completed += 1
            task = rng.choice(tasks)
            env = SuiteEnvironment(task)
            obs = env.reset()
    batch["completed_episodes"] = completed
    return batch


def _save_checkpoint(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+".tmp")
    # A model checkpoint is a local artifact, not a delivery ZIP package.
    torch.save(value, temporary, _use_new_zipfile_serialization=False)
    temporary.replace(path)


def train_ppo(seed, algorithm, tasks, development):
    if algorithm not in {"bc_ppo", "ppo_scratch"}:
        raise ValueError("Unknown training algorithm")
    folder = LAB/"models"/f"seed_{seed}"/algorithm
    if (folder/"manifest.json").exists():
        return json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    setup_seed(seed+1000)
    bc_folder = LAB/"models"/f"seed_{seed}"/"bc"
    initial = json.loads((bc_folder/"policy.json").read_text(encoding="utf-8")) if algorithm == "bc_ppo" else policy_value(ActorCritic())
    network = load_policy(initial)
    network.train()
    optimizer = torch.optim.Adam(network.parameters(), lr=CONFIG["ppo_lr"])
    checkpoint = folder/"trainer_state.pt"
    config_hash = digest([CONFIG, digest(tasks), digest(development), digest(initial), algorithm, seed])
    if checkpoint.exists():
        saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
        if saved["config_hash"] != config_hash:
            raise ValueError("Cannot resume changed training/data/initial policy")
        network.load_state_dict(saved["network"]); optimizer.load_state_dict(saved["optimizer"])
        torch.set_rng_state(saved["torch_rng"])
        completed_update, transitions, curve = saved["update"], saved["transitions"], saved["curve"]
        best, best_key, selected = saved["best"], tuple(saved["best_key"]), saved["selected"]
    else:
        report, _ = evaluate(NeuralPolicy(network), development)
        completed_update, transitions = 0, 0
        best, best_key, selected = policy_value(network), metric_key(report), 0
        curve = [{"update": 0, "transitions": 0, "development": report}]
    started = time.perf_counter()
    for update in range(completed_update+1, CONFIG["ppo_updates"]+1):
        batch = collect(network, tasks, seed, update, CONFIG["rollout_steps"])
        stats = ppo_update(network, optimizer, batch, epochs=CONFIG["ppo_epochs"], minibatch=CONFIG["minibatch"])
        transitions += len(batch["actions"])
        # Full transition evidence: only public features/masks are policy inputs.
        trace_path = LAB/"training_rollouts"/f"seed_{seed}"/algorithm/f"update_{update:03d}.jsonl"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        records = [{"task_id": batch["task_ids"][i], "features": encode(obs), "mask": obs["mask"],
                    "action": batch["actions"][i], "old_logp": batch["logp"][i], "value": batch["values"][i],
                    "next_value": batch["next_values"][i], "reward": batch["rewards"][i], "done": batch["dones"][i]} for i, obs in enumerate(batch["observations"])]
        trace_path.write_text("".join(json.dumps(row, separators=(",", ":"))+"\n" for row in records), encoding="utf-8")
        entry = {"update": update, "transitions": transitions, "episodes": batch["completed_episodes"], **stats}
        if update in CONFIG["evaluate_updates"]:
            report, _ = evaluate(NeuralPolicy(network), development)
            entry["development"] = report
            key = metric_key(report)
            if key > best_key:
                best, best_key, selected = policy_value(network), key, update
        curve.append(entry)
        _save_checkpoint(checkpoint, {"network": network.state_dict(), "optimizer": optimizer.state_dict(), "torch_rng": torch.get_rng_state(),
            "config_hash": config_hash, "update": update, "transitions": transitions, "curve": curve,
            "best": best, "best_key": best_key, "selected": selected})
        _progress(phase=algorithm, seed=seed, update=update, transitions=transitions,
                  selected_update=selected, best_development_success=best_key[0])
    write_json(folder/"policy.json", best)
    write_json(folder/"curve.json", curve)
    manifest = {"algorithm": algorithm, "seed": seed, "ppo_updates": CONFIG["ppo_updates"], "transitions": transitions,
                "selected_update": selected, "selected_by": CONFIG["model_selection"], "policy_hash": digest(best),
                "initial_policy_hash": digest(initial), "initialization": "selected_bc" if algorithm == "bc_ppo" else "random_same_architecture",
                "initial_policy_retained": selected == 0, "train_tasks_hash": digest(tasks), "development_tasks_hash": digest(development),
                "config_hash": config_hash, "heldout_used": False, "device": "cpu", "real_cvit_jobs": 0,
                "cpu_seconds_this_invocation": time.perf_counter()-started}
    write_json(folder/"manifest.json", manifest)
    return manifest


def train_all():
    prepare_training()
    verify_bank()
    freeze_path = LAB/"evidence/selection_freeze.json"
    if freeze_path.exists():
        return {"already_selected": True, "freeze": str(freeze_path), "no_retraining": True}
    tasks = load_split("train", "training")
    development = load_split("development", "development")
    rows = reference_demonstrations(tasks)
    write_json(LAB/"training/reference_manifest.json", {"rows": len(rows), "tasks": len(tasks), "label_source": CONFIG["source_labels"],
               "train_hash": digest(tasks), "development_hash": digest(development)})
    manifests = {}
    for seed in CONFIG["seeds"]:
        manifests[f"seed_{seed}/bc"] = train_bc(seed, tasks, development, rows)
        for algorithm in ("bc_ppo", "ppo_scratch"):
            manifests[f"seed_{seed}/{algorithm}"] = train_ppo(seed, algorithm, tasks, development)
    files = ("contracts", "environment", "verifier", "mock_tools", "policies", "tasks", "cvit_mock", "suite_tasks", "adapter_v3", "ppo", "training_v3", "evaluation_v3")
    freeze = {"stage": "all_policies_selected_before_final_tasks_loaded", "date": "2026-10-26",
              "training_config_hash": digest(CONFIG), "bank_seal_hash": file_hash(LAB/"bank_v3/seal.json"),
              "source_hashes": {f"lab/{name}.py": file_hash(LAB/"lab"/(name+".py")) for name in files},
              "policies": {key: value["policy_hash"] for key, value in manifests.items()},
              "final_tasks_loaded": False, "model_selection": "development_only", "real_tools_connected": False}
    write_json(freeze_path, freeze)
    write_json(LAB/"evidence/training_summary.json", {"manifests": manifests,
               "total_ppo_transitions": sum(v.get("transitions", 0) for v in manifests.values()),
               "reference_labels": len(rows), "llm_weights_updated": False, "cvit_weights_trained": False})
    _progress(phase="all_selected", selected_policies=len(manifests), total_ppo_transitions=sum(v.get("transitions", 0) for v in manifests.values()))
    return {"selected_policies": len(manifests), "ppo_transitions": sum(v.get("transitions", 0) for v in manifests.values()), "final_tasks_loaded": False}
