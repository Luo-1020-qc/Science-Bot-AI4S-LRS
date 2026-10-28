"""Bounded decision simulator and a reproducible imitation-learning baseline.

Synthetic users, rule-reference labels, no human-expert or PPO training claims.
Gym-style reset/step semantics; policies receive public observations only.
"""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np

from ....util import digest, write_json
from .state import new_state, apply_fields, contract_hash
from .validation import verify, make_spec
from .policy import ACTIONS, FEATURE_NAMES, FEATURE_VERSION, observe, RuleInterviewPolicy, BCInterviewPolicy, RandomInterviewPolicy

REWARD_VERSION = "design_reward_v1"


def make_tasks(split, count, seed):
    if split not in {"train", "development", "heldout"} or not 1 <= count <= 2000:
        raise ValueError("Invalid task split or count")
    rng = np.random.default_rng(seed)
    tasks = []
    for i in range(count):
        # All paired tasks are held out from BC training and model selection.
        design = "paired" if split == "heldout" else ["independent", "prediction"][i % 2]
        label = f"{split}_{seed}_{i}"
        names = {"unit": f"unit_{i}", "response": f"response_{i}", "factor": f"condition_{i}"}
        truth = {"data_path": label+".csv", "research_question": "比较或预测当前独立任务的响应", "design": design,
                 "unit_structure": "paired_units" if design == "paired" else "independent_rows",
                 "provenance": "synthetic", "sampling_note": "现有模拟样本，探索性演示", **names}
        if design == "prediction":
            truth.pop("factor")
            truth["features"] = [f"x_{i}"]
        else:
            truth["levels"] = ["control", "treatment"]
        initial = {key: value for key, value in truth.items() if rng.random() < .35}
        unknown = ["sampling_note"] if i % 11 == 0 else []
        if unknown:
            initial.pop("sampling_note", None)
        tasks.append({"id": label, "split": split, "family": design, "truth": truth, "initial": initial,
                      "unknown_fields": unknown, "conflict": i % 13 == 0})
    return tasks


class DesignDecisionEnv:
    def __init__(self, task):
        self._task = deepcopy(task)
        self.done = False

    def reset(self, seed=None, options=None):
        self.state = new_state()
        self.state["id"] = digest(self._task["id"])[:32]
        apply_fields(self.state, self._task["initial"], turn=0, quote="synthetic initial declaration")
        if self._task.get("conflict"):
            self.state["fields"]["response"] = "obsolete_column"
            self.state["sources"]["response"] = {"kind": "user_structured", "turn": 0, "quote": "synthetic conflict"}
            apply_fields(self.state, {"response": self._task["truth"]["response"]}, turn=0, quote="synthetic correction")
        self.state["validation"] = verify(self.state)
        self.done, self.steps = False, 0
        return observe(self.state), {"task_id": self._task["id"], "simulated": True}

    def step(self, action):
        if self.done:
            raise ValueError("Episode already finished")
        if type(action) is int and 0 <= action < len(ACTIONS):
            action = ACTIONS[action]
        obs = observe(self.state)
        if action not in ACTIONS or not obs["mask"][ACTIONS.index(action)]:
            self.done = True
            return obs, -5.0, True, False, {"invalid_action": True, "success": False, "execution_authorized": False}
        self.steps += 1
        self.state["turns"] += 1
        reward, info = -.1, {"execution_authorized": False, "simulated": True}
        if action.startswith("ask:") or action == "options:design":
            field = action.split(":", 1)[1]
            if field in self._task["unknown_fields"]:
                apply_fields(self.state, {}, turn=self.steps, quote="不知道", unknown=[field])
                reward -= .2
            else:
                value = self._task["truth"].get(field)
                if value is None:
                    raise ValueError("Simulator task lacks the requested field")
                apply_fields(self.state, {field: value}, turn=self.steps, quote="synthetic user response")
                reward += .25
        elif action == "resolve":
            apply_fields(self.state, {field: self._task["truth"][field] for field in self.state["conflicts"]},
                         turn=self.steps, quote="synthetic explicit resolution", resolve=True)
            reward += .25
        elif action == "prepare":
            valid = verify(self.state)["ready"]
            if valid:
                make_spec(self.state)
            self.done = True
            info.update(success=valid, appropriate_stop=False)
            reward += 3 if valid else -5
        elif action == "stop":
            appropriate = bool(self.state["unknown"]) or self.steps >= 24
            self.done = True
            info.update(success=False, appropriate_stop=appropriate)
            reward += 1 if appropriate else -2
        self.state["validation"] = verify(self.state)
        if self.steps >= 24 and not self.done:
            self.done = True
            info.update(success=False, appropriate_stop=False, budget_exhausted=True)
        return observe(self.state), reward, self.done, False, info


def demonstrations(tasks):
    rows = []
    teacher = RuleInterviewPolicy()
    for task in tasks:
        env = DesignDecisionEnv(task)
        obs, _ = env.reset()
        while not env.done:
            action = teacher.choose(obs)
            next_obs, reward, _, _, info = env.step(action)
            rows.append({"task_id": task["id"], "family": task["family"], "split": task["split"],
                         "observation": obs, "expert_action": action, "label_source": "rule_reference_not_human_expert",
                         "reward": reward, "next_observation": next_obs, "terminal": env.done,
                         "execution_authorized": info["execution_authorized"]})
            obs = next_obs
    return rows


def evaluate(policy, tasks):
    teacher = RuleInterviewPolicy()
    total_reward = correct = decisions = success = stopped = invalid = 0
    for task in tasks:
        env = DesignDecisionEnv(task)
        obs, _ = env.reset()
        while not env.done:
            action = policy.choose(obs)
            correct += action == teacher.choose(obs)
            decisions += 1
            obs, reward, _, _, info = env.step(action)
            total_reward += reward
            invalid += info.get("invalid_action", False)
        success += info.get("success", False)
        stopped += info.get("appropriate_stop", False)
    return {"tasks": len(tasks), "design_ready_rate": success/len(tasks), "appropriate_stop_rate": stopped/len(tasks),
            "resolved_or_stopped_rate": (success+stopped)/len(tasks), "invalid_actions": invalid,
            "mean_decisions": decisions/len(tasks), "mean_reward": total_reward/len(tasks),
            "rule_action_agreement": correct/max(1, decisions), "model_calls": 0,
            "scope": "synthetic decision simulator; no numerical experiments or human-user benchmark"}


def train_baseline(output, *, seed=21, train_count=240, development_count=60, heldout_count=90, epochs=240):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    tasks = {split: make_tasks(split, count, seed+offset) for offset, (split, count) in enumerate(
        (("train", train_count), ("development", development_count), ("heldout", heldout_count)))}
    ids = [set(t["id"] for t in values) for values in tasks.values()]
    assert not (ids[0]&ids[1] or ids[0]&ids[2] or ids[1]&ids[2])
    train = demonstrations(tasks["train"])
    development = demonstrations(tasks["development"])
    for split, rows in (("train", train), ("development", development)):
        (output/f"{split}_demonstrations.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")
    x = np.asarray([row["observation"]["features"] for row in train])
    mask = np.asarray([row["observation"]["mask"] for row in train])
    y = np.asarray([ACTIONS.index(row["expert_action"]) for row in train])
    dx = np.asarray([row["observation"]["features"] for row in development])
    dm = np.asarray([row["observation"]["mask"] for row in development])
    dy = np.asarray([ACTIONS.index(row["expert_action"]) for row in development])
    weights = np.random.default_rng(seed).normal(0, .01, (len(FEATURE_NAMES), len(ACTIONS)))
    best, best_accuracy, best_epoch = weights.copy(), -1., 0
    curve = []
    for epoch in range(epochs):
        logits = np.where(mask, x@weights, -1e9)
        logits -= logits.max(axis=1, keepdims=True)
        probability = np.exp(logits)
        probability /= probability.sum(axis=1, keepdims=True)
        loss = float(-np.log(np.maximum(probability[np.arange(len(y)), y], 1e-12)).mean())
        gradient = probability
        gradient[np.arange(len(y)), y] -= 1
        weights -= .3*(x.T@gradient/len(y)+1e-4*weights)
        accuracy = float((np.argmax(np.where(dm, dx@weights, -1e9), axis=1) == dy).mean())
        if accuracy > best_accuracy:
            best_accuracy, best, best_epoch = accuracy, weights.copy(), epoch+1
        if epoch % 20 == 0 or epoch == epochs-1:
            curve.append({"epoch": epoch+1, "train_loss": loss, "development_agreement": accuracy})
    value = {"feature_version": FEATURE_VERSION, "actions": list(ACTIONS), "features": list(FEATURE_NAMES), "weights": best.tolist()}
    write_json(output/"policy.json", value)
    manifest = {"schema_version": "interview_bc_manifest_v1", "policy_hash": digest(value), "feature_version": FEATURE_VERSION,
                "algorithm": "masked_softmax_behavior_cloning", "seed": seed, "epochs": epochs, "selected_epoch": best_epoch,
                "selection": "development_rule_action_agreement_only", "label_source": "rule_reference_not_human_expert",
                "training_rows": len(train), "development_rows": len(development), "reward_version": REWARD_VERSION,
                "task_hashes": {split: digest(values) for split, values in tasks.items()},
                "train_families": ["independent", "prediction"], "heldout_families": ["paired"],
                "llm_weights_updated": False, "ppo_trained": False}
    write_json(output/"manifest.json", manifest)
    write_json(output/"training_curve.json", curve)
    write_json(output/"task_manifest.json", tasks)
    learned = BCInterviewPolicy(output)
    results = {split: {"rule": evaluate(RuleInterviewPolicy(), values), "bc": evaluate(learned, values),
                      "random_legal": evaluate(RandomInterviewPolicy(seed), values)} for split, values in tasks.items()}
    write_json(output/"evaluation.json", results)
    return {"manifest": manifest, "evaluation": results}


def export_review_queue(session_folder, output):
    """Export observed decisions for external expert annotation, never auto-label."""
    session_folder, output = Path(session_folder).resolve(), Path(output)
    rows = []
    for path in sorted((session_folder/"design_interviews").glob("*/turns/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("observation"):
            rows.append({"trace_ref": path.relative_to(session_folder).as_posix(), "trace_hash": digest(record),
                         "observation": record["observation"], "selected_action": record["selected_action"],
                         "expert_action": None, "expert_reason": None, "reviewer": None, "status": "awaiting_expert_review"})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")
    return len(rows)
