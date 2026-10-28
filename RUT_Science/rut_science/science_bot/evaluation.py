"""Frozen paired evaluation and environment admission audit; never tune on test."""
import argparse
from dataclasses import replace
import itertools
import json
from pathlib import Path
import time
import numpy as np
import torch
from .contracts import BudgetedResearchSpec, catalog
from .cache import OutcomeCache
from .environment import BudgetedEnvironment
from .numerics import load_data, predict, errors, execute
from .policies import RulePolicy, LearnedPolicy
from .training import run_episode
from ..util import write_json, digest


def environment_audit(output):
    """E0 enumerates all affordable subsets of three real fits (no sealed teaching).

    Oracle uses training-task sealed results solely for auditing the environment.
    Its computations are explicitly outside online comparison budgets.
    """
    cache, records, checks = OutcomeCache(), [], []
    initial_time = time.perf_counter()
    e0_ids = ["mean", "ridge_half_3_1", "ridge_full_5_1"]
    for group in range(12):
        for budget in (1, 6):
            spec = BudgetedResearchSpec(group=group, compute_units=budget)
            data = load_data(spec)
            candidates = [c for c in catalog() if c["id"] in e0_ids]
            outcomes = {c["id"]: execute(data, c) for c in candidates}
            reachable = []
            for size in range(1, 4):
                for subset in itertools.combinations(candidates, size):
                    cost = sum(c["cost"] for c in subset)
                    if cost > budget:
                        continue
                    winner = min(subset, key=lambda c: (outcomes[c["id"]]["validation_mean"], c["id"]))
                    sealed = float(errors(predict(outcomes[winner["id"]]["model"], data.sealed_x), data.sealed_y).mean())
                    utility = float(sealed <= spec.quality_threshold)-0.05*(0.70*(cost+2)/(budget+2)+0.15*(size+2)/14)
                    reachable.append({"subset": [c["id"] for c in subset], "selected": winner["id"],
                                      "sealed_error": sealed, "utility": utility, "cu": cost})
            records.append({"group": group, "budget": budget, "reachable": reachable,
                            "oracle": max(reachable, key=lambda r: r["utility"])})
    # Actual evidence-responsive rules, evaluated on the same train tasks and costs.
    paired = []
    for group in range(24):
        for budget in (6, 10, 14):
            row = {"group": group, "budget": budget}
            for mode in ("cheap", "dense", "adaptive", "random", "search"):
                report, reward, _ = run_episode(BudgetedResearchSpec(group=group, compute_units=budget), RulePolicy(mode, 11), cache)
                row[mode] = {"reward": reward, "success": report["scientific_success"], "cu": report["resources"]["search_cu"]}
            paired.append(row)
    cheap_wins = sum(r["cheap"]["reward"] > r["dense"]["reward"]+1e-6 for r in paired)
    dense_wins = sum(r["dense"]["reward"] > r["cheap"]["reward"]+1e-6 for r in paired)
    diagnostic_wins = sum(r["adaptive"]["reward"] > r["cheap"]["reward"]+1e-6 for r in paired)
    diagnostic_loses = sum(r["adaptive"]["reward"] < r["cheap"]["reward"]-1e-6 for r in paired)
    # Cache vs real verification on 39 legitimate pairs, including predictions.
    for group in range(3):
        data = load_data(BudgetedResearchSpec(group=group))
        for c in catalog():
            hot, _ = cache.get(data, c)
            cold = execute(data, c)
            checks.append(digest(hot) == digest(cold))
    budget_changes = sum(records[i]["oracle"]["subset"] != records[i+1]["oracle"]["subset"]
                         for i in range(0, len(records), 2))
    evidence_better_than_random = np.mean([r["adaptive"]["reward"] for r in paired]) > np.mean([r["random"]["reward"] for r in paired])
    gates = {"complementary_reasonable_rules": cheap_wins > 0 and dense_wins > 0,
             "diagnostics_conditional_net_value": diagnostic_wins > 0 and diagnostic_loses > 0,
             "evidence_rule_beats_random": bool(evidence_better_than_random),
             "budget_changes_oracle_choices": budget_changes > 0, "cache_matches_real": all(checks)}
    result = {"gates": gates, "admitted": all(gates.values()), "cheap_wins": cheap_wins,
              "dense_wins": dense_wins, "diagnostic_wins": diagnostic_wins, "diagnostic_loses": diagnostic_loses,
              "cache_checks": len(checks), "e0": records, "paired_training_rules": paired,
              "oracle_cost_scope": "separate_offline_environment_audit_not_online_policy",
              "elapsed_seconds": time.perf_counter()-initial_time}
    write_json(Path(output), result)
    return result


def paired_interval(rows, policy, reference, field="success", seed=2026):
    # Cluster all budget/instance copies by their root mechanism group.
    roots = sorted({r["root"] for r in rows})
    diffs = []
    for root in roots:
        group = [r for r in rows if r["root"] == root]
        p = [r[field] for r in group if r["policy"] == policy]
        q = [r[field] for r in group if r["policy"] == reference]
        if p and q:
            diffs.append(float(np.mean(p)-np.mean(q)))
    if not diffs:
        return None
    rng = np.random.default_rng(seed)
    boot = np.mean(rng.choice(diffs, size=(2000, len(diffs))), axis=1)
    return {"difference": float(np.mean(diffs)), "ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
            "independent_root_groups": len(diffs), "method": "paired_root_cluster_bootstrap"}


def evaluate(models, output):
    models, output = Path(models), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output/"final_test.json").exists():
        raise ValueError("Final test output already exists; preserve frozen evaluation")
    seeds = [11, 22, 33, 44, 55]
    available = [seed for seed in seeds if (models/f"bc_ppo_{seed}"/"manifest.json").exists()]
    cache = OutcomeCache()
    dev = []
    for kind in ("bc_ppo", "ppo_scratch"):
        for seed in available:
            policy = LearnedPolicy(models/f"{kind}_{seed}")
            for group in range(8):
                for budget in (6, 10, 14):
                    report, reward, _ = run_episode(BudgetedResearchSpec(split="dev", group=group, compute_units=budget), policy, cache)
                    dev.append({"kind": kind, "seed": seed, "group": group, "budget": budget,
                                "success": report["scientific_success"], "return": reward})
    # Only dev selects deployment policy. All seeds remain in the final comparison.
    scores = {(kind, seed): np.mean([r["return"] for r in dev if r["kind"] == kind and r["seed"] == seed])
              for kind in ("bc_ppo", "ppo_scratch") for seed in available}
    selected = max(scores, key=scores.get)
    import shutil
    destination = models/"selected"
    if destination.exists():
        raise ValueError("Deployment checkpoint already exists; refuse to overwrite")
    shutil.copytree(models/f"{selected[0]}_{selected[1]}", destination)
    write_json(output/"development_selection.json", {"rows": dev, "selected": list(selected),
                                                    "selection_metric": "mean_dev_return", "test_used": False})
    manifest = {"schema": "benchmark_manifest_v1", "train": {"groups": list(range(24)), "offset": 0},
                "dev": {"groups": list(range(8)), "offset": 10000},
                "test": {"groups": list(range(8)), "offset": 20000}, "instances": [11, 22, 33],
                "budgets": [6, 10, 14], "fault_rates": [0, 0.1], "quality_threshold": 0.20,
                "engineering_threshold_not_domain_standard": True, "trained_seeds": available,
                "interpretation": "controlled_generated_regression_only", "frozen_before_final_test": True}
    write_json(output/"benchmark_manifest.json", manifest)
    policies = {f"rule_{name}": RulePolicy(name, 11) for name in ("random", "cheap", "dense", "adaptive", "search")}
    policies["bc"] = LearnedPolicy(models/"bc")
    for seed in available:
        for kind in ("bc_ppo", "ppo_scratch"):
            policies[f"{kind}_{seed}"] = LearnedPolicy(models/f"{kind}_{seed}")
    for ablation in ("no_budget", "no_history", "no_diagnostics", "no_fault_training"):
        if not (models/ablation/"manifest.json").exists():
            raise ValueError(f"Missing trained ablation: {ablation}")
        policies[ablation] = LearnedPolicy(models/ablation)
    rows = []
    for group in range(8):
        for instance in manifest["instances"]:
            for budget in manifest["budgets"]:
                for faults in manifest["fault_rates"]:
                    spec = BudgetedResearchSpec(split="test", group=group, task_seed=instance,
                                               compute_units=budget, fault_rate=faults)
                    for name, policy in policies.items():
                        report, reward, _ = run_episode(spec, policy, cache)
                        rows.append({"root": group, "instance": instance, "budget": budget, "faults": faults,
                            "policy": name, "success": int(report["scientific_success"]), "valid": int(report["valid"]),
                            "coverage": int(report["complete"]), "strict": int(report["strict_execution"]),
                            "return": reward, "sealed_error": report["sealed_error"], "resources": report["resources"]})
        print(f"evaluated root group {group+1}/8", flush=True)
    write_json(output/"final_test.json", {"manifest_hash": digest(manifest), "rows": rows})
    summary = {}
    for name in policies:
        records = [r for r in rows if r["policy"] == name]
        summary[name] = {"successes": sum(r["success"] for r in records), "tasks": len(records),
                         "success_rate": float(np.mean([r["success"] for r in records])),
                         "coverage": float(np.mean([r["coverage"] for r in records])),
                         "mean_search_cu": float(np.mean([r["resources"]["search_cu"] for r in records])),
                         "vs_strong_rule": paired_interval(rows, name, "rule_adaptive")}
    result = {"policies": summary, "root_groups": 8, "scope": "small_controlled_pilot",
              "llm_baseline": "separate_live_api_pilot_required", "selected_on_dev": list(selected),
              "ablations": "separately retrained no-budget/no-history/no-diagnostics/no-fault pilots, seed 11 only; all main rewards unshaped",
              "candidate_permutation": "shared scorer is permutation equivariant; training shuffled; semantic invariance tested"}
    aggregates = {}
    for kind in ("bc_ppo", "ppo_scratch"):
        roots = list(range(8))
        differences = np.asarray([[np.mean([r["success"] for r in rows if r["root"] == root and r["policy"] == f"{kind}_{seed}"])
                                  -np.mean([r["success"] for r in rows if r["root"] == root and r["policy"] == "rule_adaptive"])
                                  for root in roots] for seed in available])
        rng = np.random.default_rng(2026)
        boot = [float(differences[rng.integers(len(available), size=len(available))][:, rng.integers(8, size=8)].mean())
                for _ in range(2000)]
        aggregates[kind] = {"seed_success_rates": [summary[f"{kind}_{seed}"]["success_rate"] for seed in available],
                            "mean_success_rate": float(np.mean([summary[f"{kind}_{seed}"]["success_rate"] for seed in available])),
                            "paired_difference_vs_adaptive": float(differences.mean()),
                            "ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
                            "uncertainty": "resample_training_seeds_and_root_mechanism_groups"}
    result["variant_aggregates"] = aggregates
    result["budget_curves"] = {name: [{"budget": b,
        "success_rate": float(np.mean([r["success"] for r in rows if r["policy"] == name and r["budget"] == b])),
        "mean_search_cu": float(np.mean([r["resources"]["search_cu"] for r in rows if r["policy"] == name and r["budget"] == b]))}
        for b in (6, 10, 14)] for name in policies}
    write_json(output/"summary.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=Path("models/planner/v1"))
    parser.add_argument("--output", type=Path, default=Path("delivery/evaluation"))
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args(argv)
    torch.set_num_threads(1)
    if args.audit_only:
        result = environment_audit(args.output/"environment_audit.json")
        print(json.dumps({k: v for k, v in result.items() if k not in {"e0", "paired_training_rules"}}, indent=2))
    else:
        evaluate(args.models, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
