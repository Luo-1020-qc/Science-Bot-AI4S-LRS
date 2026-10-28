"""Final evaluation uses frozen selections; no final-score-driven training."""
import json
import random
from collections import defaultdict
from .guard import LAB, file_hash, write_json
from .contracts import digest
from .suite_tasks import load_split, verify_bank
from .adapter_v3 import ACTIONS_V3, SuiteRule, evaluate
from .ppo import load_policy, NeuralPolicy, setup_seed
from .cvit_mock import CViTMockEnvironment, CViTRule


def check_selection():
    freeze = json.loads((LAB/"evidence/selection_freeze.json").read_text(encoding="utf-8"))
    if freeze["stage"] != "all_policies_selected_before_final_tasks_loaded":
        raise ValueError("Invalid selection stage")
    if file_hash(LAB/"bank_v3/seal.json") != freeze["bank_seal_hash"]:
        raise ValueError("Bank identity changed")
    for ref, checksum in freeze["source_hashes"].items():
        if file_hash(LAB/ref) != checksum:
            raise ValueError("Frozen training/evaluation control changed: "+ref)
    for key, checksum in freeze["policies"].items():
        policy = json.loads((LAB/"models"/key/"policy.json").read_text(encoding="utf-8"))
        if digest(policy) != checksum:
            raise ValueError("Selected policy changed")
    verify_bank()
    return freeze


class RandomPolicy:
    def __init__(self):
        self.rng = random.Random(71)
    def choose(self, obs):
        return self.rng.choice([action for action, legal in zip(ACTIONS_V3, obs["mask"]) if legal])


def final_evaluation():
    setup_seed(17)
    freeze = check_selection()
    path = LAB/"evidence/final_evaluation.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        return {"reused": True, "aggregates": saved["aggregates"], "no_new_training": True}
    tasks = load_split("heldout", "final_evaluation")
    policies = {"context_rule": SuiteRule(), "random_legal": RandomPolicy()}
    for key in freeze["policies"]:
        policy = json.loads((LAB/"models"/key/"policy.json").read_text(encoding="utf-8"))
        policies[key] = NeuralPolicy(load_policy(policy))
    reports, rows = {}, []
    for name, policy in policies.items():
        report, trajectories = evaluate(policy, tasks)
        reports[name] = report
        for row in trajectories:
            rows.append({"policy": name, **row})
    aggregates = {}
    for algorithm in ("bc", "bc_ppo", "ppo_scratch"):
        values = [report for name, report in reports.items() if name.endswith("/"+algorithm)]
        aggregates[algorithm] = {"training_seeds": len(values),
            "mean_success_rate": sum(v["success_rate"] for v in values)/len(values),
            "min_success_rate": min(v["success_rate"] for v in values), "max_success_rate": max(v["success_rate"] for v in values),
            "mean_decisions": sum(v["mean_decisions"] for v in values)/len(values),
            "by_domain": {domain: {"mean_success_rate": sum(v["by_domain"][domain]["success_rate"] for v in values)/len(values),
                                   "min_success_rate": min(v["by_domain"][domain]["success_rate"] for v in values),
                                   "max_success_rate": max(v["by_domain"][domain]["success_rate"] for v in values)} for domain in ("tabular", "cvit")}}
    result = {"version": "g2_3_final_v1", "reports": reports, "aggregates": aggregates,
              "selection_freeze_hash": digest(freeze), "final_tasks_hash": digest(tasks),
              "note": "Three training seeds, reused scripted scenario templates; descriptive result, not a population-generalization estimate",
              "real_model_calls": 0, "real_tool_executions": 0, "real_gpu_jobs": 0,
              "cvit_metrics": None, "ppo_trained": True, "live_policy_promoted": False}
    write_json(path, result)
    target = LAB/"evidence/final_episode_results.jsonl"
    target.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")
    return {"aggregates": aggregates, "rule_success": reports["context_rule"]["success_rate"], "real_gpu_jobs": 0}


def cvit_demo():
    tasks = load_split("development", "development")
    task = next(task for task in tasks if task["domain"] == "cvit" and task["scenario"] == "existing_running")
    env = CViTMockEnvironment(task)
    obs = env.reset()
    actions = []
    while not env.done:
        action = CViTRule().choose(obs)
        obs, _, done, info = env.step(action)
        actions.append(action)
        if env.state["reconciled"] and not done:
            snapshot = env.snapshot()
            write_json(LAB/"cvit_mock/evidence/paused_job.json", snapshot)
            env = CViTMockEnvironment.restore(snapshot)
            obs = env.observe()
    result = {"scenario": task["scenario"], "actions": actions, "success": info["success"],
              "mock_launches": env.state["launches"], "existing_job_reused": env.state["launches"] == 0,
              "real_gpu_jobs": 0, "metric": None, "restored_from_saved_state": True}
    write_json(LAB/"cvit_mock/evidence/demo.json", result)
    return result
