"""Separate corrective trial. Preserves the first frozen experiment entirely.

Reference-state aggregation, observed-evidence rewards and KL-regularized PPO.
No real expert labels, CViT jobs or LLM updates; dev-only model selection.
"""
from copy import deepcopy
import json
import random
import numpy as np
import torch
from .guard import LAB, file_hash, write_json
from .contracts import digest
from .adapter_v3 import ACTIONS_V3, FEATURES_V3, SuiteEnvironment, SuiteRule, encode, evaluate, rollout
from .suite_tasks import load_split, cvit_task, tabular_task
from .ppo import setup_seed, ActorCritic, NeuralPolicy, tensors, policy_value, load_policy, gae, clipped_loss
from .training_v3 import reference_demonstrations, metric_key
from .reporting_v3 import stop_evidence

TRIAL = LAB/"experiments/feedback_v2"
TRIAL_CONFIG = {"version": "observed_feedback_kl_ppo_v2", "seeds": [21, 37, 59], "initial_bc_epochs": 600,
                "aggregation_rounds": 2, "aggregation_fit_epochs": 250, "aggregation_train_tasks": 80,
                "ppo_updates": 24, "rollout_steps": 512, "ppo_lr": .0001, "ppo_epochs": 4,
                "kl_reference_weight": .05, "entropy_weight": .005,
                "selection": "development success then fewer blocked attempts then fewer decisions"}


def build_trial_bank():
    path = TRIAL/"seal.json"
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if value["task_hash"] != file_hash(TRIAL/"heldout.jsonl"):
            raise ValueError("Feedback trial bank changed")
        return value
    tasks = []
    for i in range(48):
        if i % 4 == 0:
            task = tabular_task("pair_conflict_revoke_v3", "feedback_heldout", i, 7019)
            task["hidden"]["confirmation"] = "approve"
            task["hidden"]["inspection_mode"] = "transient_once"
            task["scenario"] = "paired_conflict_and_transient_new"
        elif i % 4 == 1:
            task = tabular_task("prediction_change_transient_v3", "feedback_heldout", i, 7019)
            task["hidden"]["confirmation"] = "deny"
            task["scenario"] = "prediction_change_transient_and_refusal_new"
        elif i % 4 == 2:
            task = cvit_task("pilot_oom", "feedback_heldout", i, 7051)
            task["hidden"]["facts"]["configuration"] = "full"
            if "configuration" in task["initial"]:
                task["initial"]["configuration"] = "full"
            task["scenario"] = "full_configuration_oom_new"
        else:
            task = cvit_task("full_data_change", "feedback_heldout", i, 7051)
            task["hidden"]["existing_job"] = "completed"
            task["scenario"] = "full_data_change_and_existing_completed_new"
        tasks.append(task)
    TRIAL.mkdir(parents=True, exist_ok=True)
    target = TRIAL/"heldout.jsonl"
    target.write_text("".join(json.dumps(t, ensure_ascii=False)+"\n" for t in tasks), encoding="utf-8")
    seal = {"date": "2026-10-26", "tasks": len(tasks), "task_hash": file_hash(target),
            "reason": "New fixed source groups and combinations for reward-correction trial; not first delivery's final tasks",
            "scope": "Synthetic combinations; primitive mechanisms still overlap training"}
    write_json(path, seal)
    write_json(TRIAL/"config.json", TRIAL_CONFIG)
    return seal


class FeedbackEnv(SuiteEnvironment):
    def step(self, action):
        if type(action) is int:
            action = ACTIONS_V3[action]
        before = self.wrap(self.inner.observe())
        after, _, done, info = super().step(action)
        b, a = before["observation"], after["observation"]
        reward = -.03
        question = action.split(":")[-1] if ":ask:" in action or action.startswith("ask:") else None
        if question:
            if question in b["facts"] or question in b["unknown"]:
                reward -= .25
            elif question in a["facts"] or question in a["unknown"]:
                reward += .1
            reward -= .05
        if action in {"inspect", "retry_inspect", "cvit:inspect", "resolve", "cvit:reconcile"}:
            reward += .05
        draft_key = "draft_valid" if self.domain == "tabular" else "draft_current"
        if action in {"draft", "cvit:draft"}:
            reward += .4 if a[draft_key] and not b[draft_key] else -.4
        if action in {"request_confirmation", "cvit:confirm"}:
            reward += .15 if a["confirmed_current"] and not b["confirmed_current"] else -.05
        if done:
            success = bool(info.get("success"))
            if action == "stop":
                success = success and stop_evidence(before)
                reward += 1. if success else -5.
            elif action in {"execute_mock", "cvit:poll_mock"}:
                reward += 8. if success else -5.
            elif action in {"draft", "cvit:draft"}:
                reward += 5. if success else -5.
            else:
                reward += 1.5 if success else -5.
            info["success"] = success
        return after, reward, done, info


def _fit(network, rows, epochs):
    optimizer = torch.optim.Adam(network.parameters(), lr=.001)
    x = torch.tensor([row["features"] for row in rows], dtype=torch.float32)
    mask = torch.tensor([row["mask"] for row in rows], dtype=torch.bool)
    y = torch.tensor([row["action"] for row in rows], dtype=torch.long)
    for _ in range(epochs):
        dist, _ = network(x, mask)
        loss = -dist.log_prob(y).mean()
        optimizer.zero_grad(); loss.backward(); optimizer.step()
    return float(loss.detach())


def aggregated_baseline(seed, train, development):
    folder = TRIAL/"models"/f"seed_{seed}"
    if (folder/"baseline.json").exists():
        return json.loads((folder/"baseline.json").read_text(encoding="utf-8"))
    setup_seed(seed)
    network = ActorCritic()
    rows = reference_demonstrations(train)
    _fit(network, rows, TRIAL_CONFIG["initial_bc_epochs"])
    reference = SuiteRule()
    curve, best, best_key = [], None, (-1., -1e9, -1e9)
    for stage in range(3):
        report, _ = evaluate(NeuralPolicy(network), development)
        curve.append({"stage": stage, "rows": len(rows), "development": report})
        if metric_key(report) > best_key:
            best, best_key = policy_value(network), metric_key(report)
        if stage == 2:
            break
        policy = NeuralPolicy(network)
        for task in random.Random(seed+stage).sample(train, TRIAL_CONFIG["aggregation_train_tasks"]):
            env = SuiteEnvironment(task)
            obs = env.reset()
            while not env.inner.done:
                label = reference.choose(obs)
                if obs["mask"][ACTIONS_V3.index(label)]:
                    rows.append({"features": encode(obs), "mask": obs["mask"], "action": ACTIONS_V3.index(label)})
                obs, _, _, _ = env.step(policy.choose(obs))
        _fit(network, rows, TRIAL_CONFIG["aggregation_fit_epochs"])
    write_json(folder/"baseline.json", best)
    write_json(folder/"baseline_manifest.json", {"seed": seed, "reference_rows": len(rows), "human_expert_labels": 0,
               "policy_hash": digest(best), "curve": curve, "selection": "development_only", "algorithm": "BC_plus_reference_state_aggregation"})
    return best


def collect_feedback(network, tasks, seed, update):
    rng = random.Random(seed*1000+update)
    task = rng.choice(tasks); env = FeedbackEnv(task); obs = env.reset()
    batch = {name: [] for name in ("observations", "actions", "logp", "values", "next_values", "rewards", "dones")}
    for _ in range(TRIAL_CONFIG["rollout_steps"]):
        with torch.no_grad():
            dist, value = network(*tensors([obs])); action = dist.sample(); logp = dist.log_prob(action)
        next_obs, reward, done, _ = env.step(int(action.item()))
        with torch.no_grad():
            next_value = 0. if done else float(network(*tensors([next_obs]))[1].item())
        for key, item in (("observations", obs), ("actions", int(action.item())), ("logp", float(logp.item())),
                          ("values", float(value.item())), ("next_values", next_value), ("rewards", reward), ("dones", float(done))):
            batch[key].append(item)
        obs = next_obs
        if done:
            task = rng.choice(tasks); env = FeedbackEnv(task); obs = env.reset()
    return batch


def update_kl(network, reference, optimizer, batch):
    advantages, returns = gae(batch["rewards"], batch["values"], batch["next_values"], batch["dones"])
    adv = torch.tensor((advantages-advantages.mean())/(advantages.std()+1e-8))
    ret = torch.tensor(returns)
    x, mask = tensors(batch["observations"])
    acts, old = torch.tensor(batch["actions"]), torch.tensor(batch["logp"])
    losses = []
    for _ in range(TRIAL_CONFIG["ppo_epochs"]):
        for idx in torch.randperm(len(acts)).split(128):
            dist, value = network(x[idx], mask[idx])
            with torch.no_grad():
                ref, _ = reference(x[idx], mask[idx])
            kl = torch.distributions.kl_divergence(ref, dist).mean()
            loss = (clipped_loss(dist.log_prob(acts[idx]), old[idx], adv[idx])+.25*(value-ret[idx]).square().mean()
                    -.005*dist.entropy().mean()+TRIAL_CONFIG["kl_reference_weight"]*kl)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite feedback PPO loss")
            optimizer.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(network.parameters(), .5); optimizer.step()
            losses.append(float(loss.detach()))
    return float(np.mean(losses))


def run_trial():
    build_trial_bank()
    frozen = TRIAL/"selection.json"
    if frozen.exists():
        return {"already_selected": True, "no_retraining": True}
    train, development = load_split("train", "training"), load_split("development", "development")
    selected = {}
    for seed in TRIAL_CONFIG["seeds"]:
        folder = TRIAL/"models"/f"seed_{seed}"
        baseline = aggregated_baseline(seed, train, development)
        setup_seed(seed+5000)
        network, reference = load_policy(baseline), load_policy(baseline)
        optimizer = torch.optim.Adam(network.parameters(), lr=TRIAL_CONFIG["ppo_lr"])
        initial, _ = evaluate(NeuralPolicy(network), development)
        best, best_key, step = baseline, metric_key(initial), 0
        curve = [{"update": 0, "development": initial}]
        for update in range(1, TRIAL_CONFIG["ppo_updates"]+1):
            batch = collect_feedback(network, train, seed, update)
            loss = update_kl(network, reference, optimizer, batch)
            path = folder/"rollouts"/f"update_{update:03d}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            records = [{"features": encode(obs), "mask": obs["mask"], "action": batch["actions"][i],
                        "old_logp": batch["logp"][i], "value": batch["values"][i], "next_value": batch["next_values"][i],
                        "reward": batch["rewards"][i], "done": batch["dones"][i]} for i, obs in enumerate(batch["observations"])]
            path.write_text("".join(json.dumps(row, separators=(",", ":"))+"\n" for row in records), encoding="utf-8")
            entry = {"update": update, "loss": loss}
            if update % 6 == 0:
                report, _ = evaluate(NeuralPolicy(network), development)
                entry["development"] = report
                if metric_key(report) > best_key:
                    best, best_key, step = policy_value(network), metric_key(report), update
            curve.append(entry)
            write_json(TRIAL/"progress.json", {"seed": seed, "update": update, "best_development_success": best_key[0]})
        write_json(folder/"ppo.json", best)
        write_json(folder/"last_policy.json", policy_value(network))
        write_json(folder/"curve.json", curve)
        write_json(folder/"manifest.json", {"seed": seed, "ppo_transitions": 12288, "selected_update": step,
                   "baseline_hash": digest(baseline), "selected_ppo_hash": digest(best), "initial_retained": step == 0,
                   "parameter_updates_occurred": digest(policy_value(network)) != digest(baseline), "final_tasks_used": False})
        selected[f"seed_{seed}/baseline"] = digest(baseline)
        selected[f"seed_{seed}/ppo"] = digest(best)
    write_json(frozen, {"stage": "selected_before_loading_trial_final", "policies": selected,
               "config_hash": digest(TRIAL_CONFIG), "bank_hash": file_hash(TRIAL/"heldout.jsonl"),
               "source_hash": file_hash(LAB/"lab/feedback_trial.py"), "total_ppo_transitions": 36864,
               "reward_version": "public_evidence_and_completion_weighted_v2", "first_experiment_preserved": True})
    return {"selected": 6, "additional_ppo_transitions": 36864, "final_tasks_used": False}


def evaluate_trial():
    seal = build_trial_bank()
    selection = json.loads((TRIAL/"selection.json").read_text(encoding="utf-8"))
    if selection["source_hash"] != file_hash(LAB/"lab/feedback_trial.py") or selection["bank_hash"] != file_hash(TRIAL/"heldout.jsonl"):
        raise ValueError("Feedback trial selection identity changed")
    if (TRIAL/"final.json").exists():
        return json.loads((TRIAL/"final.json").read_text(encoding="utf-8"))["summary"]
    tasks = [json.loads(line) for line in (TRIAL/"heldout.jsonl").read_text(encoding="utf-8").splitlines() if line]
    reports, all_rows = {}, []
    policies = {"context_rule": SuiteRule()}
    for name, checksum in selection["policies"].items():
        value = json.loads((TRIAL/"models"/(name+".json")).read_text(encoding="utf-8"))
        if digest(value) != checksum:
            raise ValueError("Trial policy changed")
        policies[name] = NeuralPolicy(load_policy(value))
    for name, policy in policies.items():
        rows = [rollout(policy, task, record=True) for task in tasks]
        strict = [bool(row["success"] and (row["trace"][-1]["action"] != "stop" or stop_evidence(row["trace"][-1]["observation"]))) for row in rows]
        reports[name] = {"tasks": len(rows), "strict_successes": sum(strict), "strict_success_rate": sum(strict)/len(rows),
                         "mean_decisions": sum(row["decisions"] for row in rows)/len(rows),
                         "by_domain": {domain: {"tasks": sum(row["domain"] == domain for row in rows),
                                               "successes": sum(ok and row["domain"] == domain for ok, row in zip(strict, rows))} for domain in ("tabular", "cvit")}}
        all_rows += [{"policy": name, "strict_success": ok, **row} for ok, row in zip(strict, rows)]
    summary = {"baseline_mean": sum(v["strict_success_rate"] for k, v in reports.items() if k.endswith("baseline"))/3,
               "feedback_ppo_mean": sum(v["strict_success_rate"] for k, v in reports.items() if k.endswith("ppo"))/3,
               "rule_success": reports["context_rule"]["strict_success_rate"], "tasks": 48,
               "limitations": "Corrective exploratory trial with fresh combinations; not a replacement for the original preregistered comparison"}
    write_json(TRIAL/"final.json", {"reports": reports, "summary": summary, "selection_hash": digest(selection), "real_gpu_jobs": 0})
    (TRIAL/"final_episodes.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in all_rows), encoding="utf-8")
    return summary
