"""Post-evaluation audit: a stop must be justified by public evidence.

The original CViT mock terminal rubric credited some hidden future refusals or
unknown fields even before the policy elicited them. Preserve original scores
and trained weights; report the stricter audit separately, with no reselection.
"""
from collections import defaultdict
import json
from .guard import LAB, write_json
from .suite_tasks import load_split
from .cvit_mock import CONFIGS


def public_trace_replay(tasks, original):
    """Initial frozen report saved episode summaries; add deterministic audit traces."""
    from .adapter_v3 import SuiteRule, rollout
    from .evaluation_v3 import check_selection, RandomPolicy
    from .ppo import NeuralPolicy, load_policy, setup_seed
    from .contracts import digest
    check_selection()
    target = LAB/"evidence/final_replayed_traces.jsonl"
    manifest_path = LAB/"evidence/replay_manifest.json"
    if target.exists() and manifest_path.exists():
        from .guard import file_hash
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["original_summary_hash"] != digest(original) or manifest["trace_file_hash"] != file_hash(target):
            raise ValueError("Audit replay identity changed")
        return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line]
    setup_seed(17)
    policies, rows = {}, []
    for original_row in original:
        key = original_row["policy"]
        if key not in policies:
            if key == "context_rule":
                policies[key] = SuiteRule()
            elif key == "random_legal":
                policies[key] = RandomPolicy()
            else:
                value = json.loads((LAB/"models"/key/"policy.json").read_text(encoding="utf-8"))
                policies[key] = NeuralPolicy(load_policy(value))
        replay = rollout(policies[key], tasks[original_row["task_id"]], record=True)
        for field in ("success", "decisions", "questions", "blocked_attempts", "mock_launches", "return"):
            if replay[field] != original_row[field]:
                raise ValueError("Deterministic audit replay differs from frozen summary: "+field)
        rows.append({"policy": key, **replay})
    target.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")
    from .guard import file_hash
    write_json(manifest_path, {"original_summary_hash": digest(original), "trace_file_hash": file_hash(target),
                              "episodes": len(rows), "all_summary_fields_match": True, "policies_modified": False,
                              "reason": "Original final evaluation retained summaries only; deterministic replay adds public decision evidence for scoring audit"})
    return rows


def stop_evidence(observation):
    domain, obs = observation["domain"], observation["observation"]
    facts, profile = obs["facts"], obs["profile"] or {}
    if domain == "tabular":
        return bool(obs["unknown"] or obs["permissions"]["read"] is False or obs["confirmation_refused"]
                    or facts.get("unit_structure") in {"clustered", "temporal"} or facts.get("goal") == "causal_effect"
                    or obs["last_failure"] == "invalid_schema"
                    or facts.get("intent") == "run" and profile and profile["estimated_execution_cost"] > obs["remaining_resource"])
    if obs["unknown"] or not obs["read_allowed"] or obs["refused"] or obs["job"] == "mismatch" or obs["last_failure"]:
        return True
    if facts.get("intent") == "run" and not obs["execute_allowed"]:
        return True
    for field, allowed in (("dataset", "mock_darcy_fixture"), ("target", "pressure_field"), ("metric", "relative_l2")):
        if field in facts and facts[field] != allowed:
            return True
    config = facts.get("configuration")
    return bool(config in CONFIGS and (("budget" in facts and CONFIGS[config]["cost"] > facts["budget"])
                or profile and CONFIGS[config]["memory_gb"] > profile["available_memory_gb"]))


def execution_eligible(task):
    h, f = task["hidden"], task["hidden"]["facts"]
    if task["domain"] == "tabular":
        return bool(f["intent"] == "run" and h["read_permission"] and h["execute_permission"] and h["confirmation"] == "approve"
                    and not h["unknown_fields"] and f["unit_structure"] in {"independent_rows", "paired_units"}
                    and f["goal"] != "causal_effect" and not (f["goal"] == "prediction" and f["unit_structure"] != "independent_rows")
                    and h["inspection_mode"] != "bad_schema" and task["resource_budget"] >= h["profile"]["estimated_execution_cost"]+1)
    return bool(f["intent"] == "run" and task["read_allowed"] and task["execute_allowed"] and h["confirmation"] == "approve"
                and not h["unknown_fields"] and f["dataset"] == "mock_darcy_fixture" and f["target"] == "pressure_field"
                and f["metric"] == "relative_l2" and CONFIGS[f["configuration"]]["cost"] <= f["budget"]
                and CONFIGS[f["configuration"]]["memory_gb"] <= h["profile"]["available_memory_gb"]
                and h["job_outcome"] != "oom" and (h["existing_job"] == "none" or h["existing_matches"]))


def audit_final():
    tasks = {task["id"]: task for task in load_split("heldout", "final_evaluation")}
    original = [json.loads(line) for line in (LAB/"evidence/final_episode_results.jsonl").read_text(encoding="utf-8").splitlines() if line]
    rows = public_trace_replay(tasks, original)
    groups = defaultdict(list)
    for row in rows:
        last = row["trace"][-1]
        grounded = last["action"] != "stop" or stop_evidence(last["observation"])
        strict = bool(row["success"] and grounded)
        terminal_completed = bool(strict and (last["action"] == "execute_mock" or last["action"] == "cvit:poll_mock"))
        groups[row["policy"]].append({"domain": row["domain"], "strict_success": strict, "original_success": row["success"],
                     "unjustified_stop": last["action"] == "stop" and not grounded,
                     "execution_eligible": execution_eligible(tasks[row["task_id"]]), "completed": terminal_completed,
                     "decisions": row["decisions"], "blocked_attempts": row["blocked_attempts"]})
    reports = {}
    for policy, values in groups.items():
        eligible = [row for row in values if row["execution_eligible"]]
        reports[policy] = {"tasks": len(values), "strict_successes": sum(row["strict_success"] for row in values),
             "strict_success_rate": sum(row["strict_success"] for row in values)/len(values),
             "unjustified_stops": sum(row["unjustified_stop"] for row in values),
             "eligible_execution_tasks": len(eligible), "completed_eligible_tasks": sum(row["completed"] for row in eligible),
             "missed_eligible_tasks": sum(not row["completed"] for row in eligible),
             "by_domain": {domain: {"tasks": sum(row["domain"] == domain for row in values),
                     "strict_successes": sum(row["domain"] == domain and row["strict_success"] for row in values)} for domain in ("tabular", "cvit")}}
    aggregates = {}
    for algorithm in ("bc", "bc_ppo", "ppo_scratch"):
        values = [v for key, v in reports.items() if key.endswith("/"+algorithm)]
        aggregates[algorithm] = {"mean_strict_success_rate": sum(v["strict_success_rate"] for v in values)/len(values),
              "min_strict_success_rate": min(v["strict_success_rate"] for v in values), "max_strict_success_rate": max(v["strict_success_rate"] for v in values),
              "eligible_tasks_per_seed": values[0]["eligible_execution_tasks"],
              "completed_eligible_tasks_mean": sum(v["completed_eligible_tasks"] for v in values)/len(values)}
    result = {"version": "public_evidence_stop_audit_v1", "reports": reports, "aggregates": aggregates,
        "reason": "Original CViT terminal reward could credit stopping for hidden future refusal/unknown facts; audited success requires an observed blocker. A reporting correction, not a training or selection change.",
        "policy_retrained_or_reselected": False, "original_frozen_report_preserved": True,
        "limitation": "Policies were trained with the original terminal reward. This audit does not repair that reward or demonstrate policy improvement."}
    write_json(LAB/"evidence/scoring_audit.json", result)
    return result
