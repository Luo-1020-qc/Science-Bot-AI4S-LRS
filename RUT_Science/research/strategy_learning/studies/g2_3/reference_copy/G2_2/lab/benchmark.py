"""Frozen task/rubric comparison. Reference BC labels are not human experts."""
from collections import defaultdict
from copy import deepcopy
import json
from .guard import LAB, write_json, file_hash
from .contracts import ACTIONS, FEATURE_NAMES, VERSION, digest
from .environment import DesignEnvironment
from .policies import RuleV2, SlotRule, RandomLegal, BCPolicy, encode
from .tasks import load_split, verify_bank


def rollout(policy, task):
    env = DesignEnvironment(task)
    obs = env.reset()
    total = 0
    while not env.done:
        action = policy.choose(obs)
        obs, reward, _, info = env.step(action)
        total += reward
    return {"task_id": task["id"], "root_group": task["root_group"], "scenario": task["scenario"], "family": task["family"],
            "success": info["success"], "design_correct": info["design_correct"], "appropriate_stop": info["appropriate_stop"],
            "missed_execution": info["missed_execution"], "blocked_execution_attempts": info["execution_attempts_blocked"],
            "simulated_executions": info["simulated_executions"], "real_executions": 0, "real_model_calls": 0,
            "questions": sum(env.state["asked"].values()), "redundant_questions": env.state["redundant_questions"],
            "unanswerable_questions": env.state["unanswerable_questions"], "decisions": env.state["turn"],
            "mock_calls": env.state["mock_calls"], "rejected_designs": env.state["rejected_designs"],
            "return": total, "trace": env.state["history"]}


def summarize(rows):
    n = len(rows)
    metrics = {"tasks": n, "success_rate": sum(row["success"] for row in rows)/n,
               "design_correct_rate": sum(row["design_correct"] for row in rows)/n,
               "appropriate_stop_rate": sum(row["appropriate_stop"] for row in rows)/n,
               "missed_execution_count": sum(row["missed_execution"] for row in rows),
               "blocked_execution_attempts": sum(row["blocked_execution_attempts"] for row in rows),
               "real_execution_count": 0, "real_model_calls": 0}
    for name in ("questions", "redundant_questions", "unanswerable_questions", "decisions", "mock_calls", "rejected_designs", "return"):
        metrics["mean_"+name] = sum(row[name] for row in rows)/n
    groups = defaultdict(list)
    for row in rows:
        groups[row["scenario"]].append(row)
    metrics["by_scenario"] = {key: {"tasks": len(values), "successes": sum(v["success"] for v in values),
                                    "mean_questions": sum(v["questions"] for v in values)/len(values)} for key, values in groups.items()}
    metrics["interpretation"] = "Synthetic task episodes and reused templates; descriptive pilot, not a population-generalization estimate"
    return metrics


def evaluate(policy, tasks):
    rows = [rollout(policy, task) for task in tasks]
    return summarize(rows), rows


def reference_rows(tasks):
    rows = []
    for task in tasks:
        result = rollout(RuleV2(), task)
        for i, step in enumerate(result["trace"]):
            if step["action"] in ACTIONS and step["observation"]["mask"][ACTIONS.index(step["action"])]:
                rows.append({"task_id": task["id"], "split": task["split"], "decision_index": i,
                             "observation": step["observation"], "action": step["action"],
                             "label_source": "synthetic_reference_rule_not_human_expert"})
    return rows


def train_bc(train, development, seed, *, reviewed_rows=(), output_folder=None):
    import numpy as np
    rows = reference_rows(train)
    replacements = {(row["task_id"], digest(row["observation"])): row for row in reviewed_rows}
    used = set()
    for row in rows:
        key = (row["task_id"], digest(row["observation"]))
        if key in replacements:
            replacement = replacements[key]
            if replacement.get("split") != "train" or not row["observation"]["mask"][ACTIONS.index(replacement["action"])]:
                raise ValueError("Reviewed action is not a legal training decision")
            row["action"], row["label_source"] = replacement["action"], replacement["label_source"]
            used.add(key)
    if used != set(replacements):
        raise ValueError("Reviewed records must match the frozen training trajectories; no dev/heldout contamination")
    x = np.asarray([encode(row["observation"]) for row in rows])
    y = np.asarray([ACTIONS.index(row["action"]) for row in rows])
    mask = np.asarray([row["observation"]["mask"] for row in rows])
    rng = np.random.default_rng(seed)
    weights = rng.normal(0, .01, (len(FEATURE_NAMES), len(ACTIONS)))
    best, best_key, chosen = None, (-1, -1, -1), 0
    curve = []
    for epoch in range(1, 241):
        logits = np.where(mask, x@weights, -1e9)
        logits -= logits.max(axis=1, keepdims=True)
        prob = np.exp(logits); prob /= prob.sum(axis=1, keepdims=True)
        loss = float(-np.log(np.maximum(prob[np.arange(len(y)), y], 1e-12)).mean())
        prob[np.arange(len(y)), y] -= 1
        weights -= .25*(x.T@prob/len(y)+1e-4*weights)
        if epoch in {20, 60, 120, 180, 240}:
            value = {"version": VERSION, "actions": list(ACTIONS), "features": list(FEATURE_NAMES), "weights": weights.tolist()}
            report, _ = evaluate(BCPolicy(value), development)
            key = (report["success_rate"], -report["blocked_execution_attempts"], -report["mean_decisions"])
            curve.append({"epoch": epoch, "train_loss": loss, "development": report})
            if key > best_key:
                best_key, best, chosen = key, deepcopy(value), epoch
    folder = output_folder or LAB/"models"/f"bc_seed_{seed}"
    if (folder/"manifest.json").exists():
        raise ValueError("Choose a new model folder; never replace a selected policy")
    write_json(folder/"policy.json", best)
    write_json(folder/"manifest.json", {"algorithm": "masked_softmax_behavior_cloning", "seed": seed,
               "selected_epoch": chosen, "selected_using": "development_success_then_blocked_attempts_then_decisions",
               "policy_hash": digest(best), "training_rows": len(rows), "human_expert_labels": 0,
               "externally_claimed_reviewed_labels": len(used), "ppo_trained": False,
               "train_tasks_hash": digest(train), "development_tasks_hash": digest(development), "heldout_loaded": False})
    write_json(folder/"curve.json", curve)
    return best, rows


def train_reviewed(source, output):
    from .guard import ensure_local
    from .review import load_reviewed_labels
    if source is None or output is None:
        raise ValueError("Select --input imported label set and --output a new model folder")
    source, output = ensure_local(source), ensure_local(output)
    if output.exists():
        raise ValueError("Reviewed training output must be a new folder")
    reviewed = load_reviewed_labels(source)
    train = load_split("train", purpose="training")
    development = load_split("development", purpose="development")
    value, _ = train_bc(train, development, 83, reviewed_rows=reviewed, output_folder=output)
    metrics, _ = evaluate(BCPolicy(value), development)
    write_json(output/"reviewed_training.json", {"input_hash": file_hash(source), "development": metrics,
               "heldout_used": False, "deployed": False})
    return {"reviewed_rows": len(reviewed), "development": metrics, "heldout_used": False, "deployed": False}


def _read_policy(seed):
    folder = LAB/"models"/f"bc_seed_{seed}"
    value = json.loads((folder/"policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if manifest["policy_hash"] != digest(value):
        raise ValueError("Policy hash mismatch")
    return value


def benchmark():
    report_path = LAB/"evidence/benchmark.json"
    if report_path.exists():
        verify_freeze()
        saved = json.loads(report_path.read_text(encoding="utf-8"))
        return {"reused_saved_evaluation": True, "heldout": saved["heldout"], "real_tools_connected": False}
    verify_bank()
    train = load_split("train", purpose="training")
    development = load_split("development", purpose="development")
    reference = None
    models = {}
    for seed in (21, 37, 59):
        models[seed], rows = train_bc(train, development, seed)
        reference = rows
    ref_path = LAB/"training/reference_train.jsonl"
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in reference), encoding="utf-8")
    freeze = {"date": "2026-10-26", "stage": "models_selected_before_final_heldout_loading",
              "seeds_fixed_in_advance": [21, 37, 59], "bank_seal_hash": file_hash(LAB/"bank/seal.json"),
              "control_files": {f"lab/{name}.py": file_hash(LAB/"lab"/(name+".py")) for name in ("verifier", "environment", "contracts", "tasks", "policies", "benchmark")},
              "policy_hashes": {str(seed): digest(value) for seed, value in models.items()}}
    write_json(LAB/"evidence/freeze.json", freeze)
    heldout = load_split("heldout", purpose="final_evaluation")
    policies = [("context_rule_v2", RuleV2()), ("slot_order_ablation", SlotRule()), ("random_legal", RandomLegal(41))]
    policies += [(f"bc_seed_{seed}", BCPolicy(value)) for seed, value in models.items()]
    reports = {}
    traces = []
    for name, policy in policies:
        report, rows = evaluate(policy, heldout)
        reports[name] = report
        for row in rows:
            row["policy"] = name
            traces.append(row)
    trace_path = LAB/"evidence/heldout_rollouts.jsonl"
    trace_path.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in traces), encoding="utf-8")
    report = {"version": "g2_2_benchmark_v1", "heldout": reports, "models_selected_on": "development_only",
              "freeze_hash": digest(freeze), "training_reference_rows": len(reference), "human_expert_labels": 0,
              "real_tools_connected": False, "real_model_calls": 0, "real_executions": 0, "ppo_trained": False,
              "heldout_record_load_stage": "after_models_frozen", "no_promotion_to_live_agent": True,
              "limitations": ["Synthetic scenario templates and scripted users", "BC imitates reference rules, not human-reviewed scientific judgment",
                              "No statistical or training tools executed; metrics concern behavior only", "One frozen task bank, three training seeds; no broad generalization claim"]}
    write_json(report_path, report)
    return {"heldout": reports, "real_tools_connected": False}


def verify_freeze():
    freeze = json.loads((LAB/"evidence/freeze.json").read_text(encoding="utf-8"))
    if file_hash(LAB/"bank/seal.json") != freeze["bank_seal_hash"]:
        raise ValueError("Task bank seal changed")
    for ref, expected in freeze["control_files"].items():
        if file_hash(LAB/ref) != expected:
            raise ValueError("Frozen control plane changed: "+ref)
    for seed, expected in freeze["policy_hashes"].items():
        if digest(_read_policy(int(seed))) != expected:
            raise ValueError("Frozen policy changed")
    verify_bank()
    return True


def demo():
    tasks = load_split("development", purpose="development")
    task = next(task for task in tasks if task["scenario"] == "conflicting_response")
    row = rollout(RuleV2(), task)
    write_json(LAB/"evidence/demo.json", row)
    return {"scenario": row["scenario"], "actions": [step["action"] for step in row["trace"]],
            "success": row["success"], "real_tools_connected": False, "real_executions": 0}
