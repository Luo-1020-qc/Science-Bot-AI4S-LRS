"""Build small, fully exposed illustrative data. Does not train any network."""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
from dataset_lib import ROOT, VERSION, ACTIONS, digest, grade, save

DATE = "2026-10-28"
SPLITS = {"train": "source_A", "development": "source_B", "evaluation_example": "source_C"}


def fact_evidence(observation, key, value, kind="user_declaration"):
    identity = "ev_"+digest([key, value, len(observation["evidence"])])[:12]
    observation["evidence"].append({"id": identity, "kind": kind, "field": key, "value": deepcopy(value),
        "source": "synthetic_user_or_mock_fixture", "real_world_verified": False})
    return identity


def plan_for(domain):
    cvit = domain == "cvit"
    return {"schema_version": "illustrative_experiment_plan_v1", "revision": 1,
        "research_question": "Estimate architecture and learning-rate effects on pressure prediction" if cvit else "Compare mean_field and ridge_field under paired independent data realizations",
        "design": "blocked_full_factorial_2x2" if cvit else "randomized_complete_block_two_arm",
        "factors": [{"name": "architecture", "levels": ["baseline_small", "candidate_small"]},
                    {"name": "learning_rate", "levels": [.0001, .0003]}] if cvit else [{"name": "predictor", "levels": ["mean_field", "ridge_field"]}],
        "primary_contrast": "architecture_high_minus_low_averaged_over_learning_rate" if cvit else "ridge_field_minus_mean_field",
        "analysis_terms": ["architecture", "learning_rate", "architecture:learning_rate", "data_realization_block"] if cvit else ["predictor", "data_realization_block"],
        "experimental_unit": "One separately seeded model-training run within a data-realization block" if cvit else "One predictor fitted and evaluated within an independently generated data-realization block",
        "blocks": {"factor": "independent_synthetic_data_realization", "count": 6 if cvit else 12},
        "replicates_per_cell_per_block": 2 if cvit else 1, "planned_runs": 48 if cvit else 24,
        "unit_response": "Mean relative L2 across the fixed test fields for this run; fields are not independent architecture replicates",
        "randomization": {"method": "allocate_independent_rng_streams_and_shuffle_within_block", "seed": 21017},
        "analysis_assumptions": ["independent_residuals_conditional_on_block", "normal_homoscedastic_errors", "additive_blocks"],
        "assumptions_status": "synthetic_declared_not_verified", "sample_size_basis": {"method": "pending_real_pilot_then_power_or_precision_analysis",
            "nominal_alpha": .05, "target_power": .8, "minimum_relevant_effect": .02, "sigma": .02,
            "numeric_inputs_source": "invented_for_schema_example_not_real_pilot", "achieved_power": None},
        "training_validation_test": {"fit_preprocessing": "train_only", "select_checkpoint_and_hyperparameters": "validation_only",
            "final_test": "after_plan_and_selection_lock_only", "test_for_tuning": False},
        "acceptance": {"design": ["unit_definition_and_source", "all_planned_cells", "interactions_and_blocks_in_analysis", "budget_and_plan_identity"],
            "execution": ["record_assignment_and_deviations", "no_duplicate_job_launch", "current_plan_confirmation"],
            "scientific": ["report_effect_and_interval", "practical_relevance_separate", "negative_results_are_valid"],
            "scientific_conclusion": None, "expert_review": "pending"},
        "resources": {"unit": "mock_resource_unit", "per_run": 4 if cvit else 1, "planned_total": 192 if cvit else 24,
            "measured_hardware_cost": None}, "execution_authorized": False}


def make_task(domain, scenario, split, group):
    identity = domain+"_"+split+"_"+scenario
    messages = {
        "paired_design": "请为Darcy压力场设计mean与ridge比较，先确认独立实验单位和验收方式，本次只设计。",
        "pseudoreplication": "Darcy测试集有1000个网格点，能否算1000次独立实验来比较两种方法？",
        "budget_revision": "Darcy比较的预算只有30个模拟资源单位，请把方案控制在预算内。",
        "factorial_design": "请设计CViT架构×学习率的2×2实验，考虑交互、区组与验收，本次只设计。",
        "existing_job": "请模拟继续已有CViT作业，先核对作业身份，避免重复启动。",
        "unknown_variance": "我想确定CViT的重复数，但没有先导方差，也无法提供；请不要编造功效。",
        "data_changed": "CViT计划已审阅，但数据版本变了，请先处理版本一致性。",
        "mock_oom": "请检查CViT模拟作业状态；如果OOM，保留失败依据并停止本轮模拟。"}
    raw = messages[scenario]
    facts = {"domain": domain, "scientific_problem": "Darcy coefficient_field_to_pressure_field", "target": "pressure_field",
             "response_metric": "relative_l2", "scope": "mock_job_protocol" if scenario in {"existing_job", "mock_oom"} else "design_only"}
    observation = {"user_messages": [{"role": "user", "content": raw}], "facts": facts,
        "unknown": ["experimental_unit", "source_of_replication"] if scenario == "paired_design" else [],
        "evidence": [], "draft": None,
        "permissions": {"inspect_mock": True, "design": True, "run_mock_job": True, "real_execution": False},
        "budget": {"remaining_mock_units": 30 if domain == "darcy" else 240, "max_decisions": 24},
        "job": {"status": "not_queried", "matched_current_plan": None}, "history": [],
        "action_mask": {name: name != "resume_job_mock" for name in ACTIONS}}
    fact_evidence(observation, "initial_request", raw)
    if scenario not in {"paired_design", "unknown_variance"}:
        observation["facts"]["unit_basis"] = "Separate synthetic data realizations; training-run variability conditional on data for CViT"
        fact_evidence(observation, "unit_basis", observation["facts"]["unit_basis"])
    if scenario == "pseudoreplication":
        observation["facts"]["user_proposed_unit"] = "one_grid_point"
        fact_evidence(observation, "user_proposed_unit", "one_grid_point")
    return {"schema_version": VERSION, "task_id": identity, "root_group": group, "domain": domain,
        "policy_split": split, "scenario_for_curator_only": scenario,
        "data_lineage": {"underlying_source_ids": ["synthetic_darcy_"+group], "source_kind": "synthetic_references_only_no_scientific_arrays",
            "within_experiment_partition": {role: f"mock://{group}/darcy/{role}" for role in ("train", "validation", "test")},
            "scope_note": "All variants sharing these synthetic sources are assigned to the same policy split"},
        "initial_observation": observation, "training_target": "Harness decisions, not pressure fields or CViT weights",
        "expert_status": "pending", "origin": "hand_authored_scripted_example"}


class Episode:
    def __init__(self, task):
        self.task = task
        self.obs = deepcopy(task["initial_observation"])
        self.steps = []

    def step(self, name, arguments, update, message, *, blocking=(), recommended=True, terminal=False):
        before = deepcopy(self.obs)
        action = {"name": name, "arguments": deepcopy(arguments)}
        update(self.obs)
        self.obs["history"].append({"action": name, "feedback": message})
        if terminal:
            self.obs["action_mask"] = {key: False for key in ACTIONS}
        feedback = {"source": "scripted_mock_feedback", "message": message, "blocking_codes": list(blocking),
                    "real_execution": False, "scientific_metric": None}
        self.steps.append({"decision_index": len(self.steps), "observation": before, "observation_hash": digest(before),
            "action": action, "feedback": feedback, "next_observation": deepcopy(self.obs), "next_observation_hash": digest(self.obs),
            "reward": grade(before, action, feedback, self.obs, terminal), "terminated": terminal, "truncated": False,
            "behavior_log_probability": None, "value_estimate": None, "reference_action_is_recommended": recommended})

    def emit(self, classification):
        return {"schema_version": VERSION, "episode_id": "ep_"+self.task["task_id"], "task_id": self.task["task_id"],
            "policy_split": self.task["policy_split"], "source": "scripted_reference_not_human_expert", "ppo_eligible": False,
            "classification": classification, "reward_version": "toy_example_reward_v1", "steps": self.steps,
            "expert_review": "pending", "real_tool_executions": 0, "scientific_outcome": None}


def episode_for(task):
    ep = Episode(task)
    scenario = task["scenario_for_curator_only"]
    domain = task["domain"]
    plan = plan_for(domain)
    if scenario == "unknown_variance":
        def unavailable(obs):
            obs["unknown"].append("pilot_variance")
            fact_evidence(obs, "pilot_variance", None, "user_unavailable")
            obs["user_messages"].append({"role": "user", "content": "没有方差依据，本轮也无法提供；请保留未知。"})
        ep.step("ask", {"field": "pilot_variance", "question": "是否有同一响应和单位下的先导方差及来源？"}, unavailable,
                "User explicitly cannot provide variance; ask occurred before the stop")
        certificate = [row["id"] for row in ep.obs["evidence"] if row["kind"] == "user_unavailable"]
        ep.step("stop_with_evidence", {"reason": "sample_size_not_justifiable", "evidence_ids": certificate,
            "next_step": "Collect a separately planned pilot or agree an exploratory scope"}, lambda obs: None,
            "Only the requested powered sample-size commitment is stopped; no claim that all design work is impossible", terminal=True)
        return ep.emit("appropriate_scoped_stop")
    if scenario in {"existing_job", "mock_oom"}:
        def reconcile(obs):
            obs["job"] = {"status": "running" if scenario == "existing_job" else "failed_oom", "matched_current_plan": True}
            obs["action_mask"]["resume_job_mock"] = scenario == "existing_job"
            fact_evidence(obs, "existing_job", obs["job"], "mock_job_status" if scenario == "existing_job" else "mock_job_failure")
        ep.step("reconcile_job_mock", {"job_ref": "mock://existing_cvit_job", "require_current_identity": True}, reconcile,
                "Matched job identity; no new launch")
        if scenario == "mock_oom":
            certificate = [row["id"] for row in ep.obs["evidence"] if row["kind"] == "mock_job_failure"]
            ep.step("stop_with_evidence", {"reason": "current_job_failed_oom", "evidence_ids": certificate,
                "next_step": "Revise memory configuration and obtain new confirmation before any future job"}, lambda obs: None,
                "Preserve failure; do not silently retry or invent completed metrics", terminal=True)
            return ep.emit("appropriate_scoped_stop")
        def resume(obs):
            obs["job"]["status"] = "mock_completed"
            fact_evidence(obs, "job_completion", {"mock_completed": True, "metric": None, "new_launches": 0}, "mock_job_status")
        ep.step("resume_job_mock", {"job_ref": "mock://existing_cvit_job", "start_new_job": False}, resume,
                "Mock completion protocol only; metric=null, no actual CViT training")
    if scenario == "paired_design":
        def clarify(obs):
            obs["facts"]["unit_basis"] = "12 independent synthetic data realizations; both predictors run within every realization"
            obs["unknown"] = []
            fact_evidence(obs, "unit_basis", obs["facts"]["unit_basis"])
            obs["user_messages"].append({"role": "user", "content": "独立重复来自不同合成数据实现；同一实现内比较mean和ridge。"})
        ep.step("ask", {"field": "experimental_unit", "question": "重复来自独立数据实现、训练随机性，还是同一场的网格点？"}, clarify,
                "User distinguishes independent data realizations from grid-point measurements")
    def inspect(obs):
        profile = {"input": "coefficient_field", "target": "pressure_field", "partition_overlap": False,
            "training_variance": "not_measured", "real_data_read": False}
        obs["facts"]["profile"] = profile
        obs["budget"]["remaining_mock_units"] -= 1
        fact_evidence(obs, "profile", profile, "mock_inspection")
    ep.step("inspect_mock", {"dataset_ref": task["data_lineage"]["within_experiment_partition"]["train"], "include_sealed_test_values": False}, inspect,
            "Synthetic metadata only; sealed outcome values are not returned")
    bad = None
    if scenario == "factorial_design":
        bad = deepcopy(plan); bad["analysis_terms"].remove("architecture:learning_rate")
    elif scenario == "pseudoreplication":
        bad = deepcopy(plan); bad["experimental_unit"] = "one_grid_point"; bad["planned_runs"] = 1000
    elif scenario == "budget_revision":
        bad = deepcopy(plan); bad["resources"]["planned_total"] = 240
    elif scenario == "data_changed":
        bad = deepcopy(plan); bad["data_identity"] = "old_revision"
    if bad is not None:
        ep.step("propose_design", {"plan": bad}, lambda obs: obs.update(draft=deepcopy(bad)),
                "Intentionally flawed candidate retained as a negative example", recommended=False)
        code = {"factorial_design": "missing_interaction", "pseudoreplication": "pseudo_replication",
                "budget_revision": "cost_exceeds_budget", "data_changed": "stale_input_identity"}[scenario]
        def reject(obs):
            fact_evidence(obs, "draft_validation", {"draft_hash": digest(obs["draft"]), "blocking_code": code}, "design_check_blocked")
        ep.step("check_design_mock", {"draft_hash": digest(bad)}, reject,
                "Scripted mock verifier detects the deliberately injected defect", blocking=(code,))
        plan["revision"] += 1
        if scenario == "data_changed":
            plan["data_identity"] = "current_synthetic_revision"
        ep.step("revise_design", {"plan": plan, "invalidate_previous_confirmation": True}, lambda obs: obs.update(draft=deepcopy(plan)),
                "Repair current design and invalidate old confirmation; values remain synthetic planning inputs")
    else:
        ep.step("propose_design", {"plan": plan}, lambda obs: obs.update(draft=deepcopy(plan)),
                "Draft is an illustrative protocol; no experiment has been run")
    def accept(obs):
        fact_evidence(obs, "draft_validation", {"draft_hash": digest(obs["draft"]), "status": "illustrative_protocol_check_passed",
            "real_assumptions_verified": False, "power_computed": False, "expert_review": "pending"}, "design_check_passed")
    ep.step("check_design_mock", {"draft_hash": digest(plan)}, accept,
            "Mock protocol check passes; actual DOE validation, power calculation and expert review remain required")
    ep.step("submit_for_review", {"draft_hash": digest(plan), "execute": False}, lambda obs: None,
            "Ready for review in this toy environment; scientific conclusion=null", terminal=True)
    return ep.emit("illustrative_plan_submitted")


def main():
    if (ROOT/"manifest.json").exists():
        raise ValueError("Example version already exists; validate it or create a new version instead of overwriting")
    artifacts = []
    all_tasks, all_episodes = [], []
    cases = [("darcy", "paired_design"), ("darcy", "pseudoreplication"), ("darcy", "budget_revision"),
             ("cvit", "factorial_design"), ("cvit", "existing_job"), ("cvit", "unknown_variance"), ("cvit", "data_changed"), ("cvit", "mock_oom")]
    for split, group in SPLITS.items():
        selected = cases if split == "train" else [("darcy", "paired_design"), ("cvit", "factorial_design")]
        tasks = [make_task(domain, scenario, split, group) for domain, scenario in selected]
        episodes = [episode_for(task) for task in tasks]
        all_tasks += tasks; all_episodes += episodes
        for prefix, data in (("tasks", tasks), ("episodes", episodes)):
            relative = f"{prefix}/{split}.jsonl"
            save(relative, data, jsonl=True); artifacts.append(relative)
    hidden = [{"task_id": t["task_id"], "scenario": t["scenario_for_curator_only"], "split": t["policy_split"],
               "expected_classification": ep["classification"], "label_source": "scripted_scenario_not_human_expert",
               "scripted_tool_feedback": [{"action": s["action"]["name"], "feedback": s["feedback"]} for s in ep["steps"]]}
              for t, ep in zip(all_tasks, all_episodes)]
    save("evaluator_only/scenarios.jsonl", hidden, jsonl=True); artifacts.append("evaluator_only/scenarios.jsonl")
    labels, preferences = [], []
    for ep in all_episodes:
        if ep["policy_split"] != "train":
            continue
        for step in ep["steps"]:
            if step["reference_action_is_recommended"]:
                labels.append({"schema_version": VERSION, "episode_id": ep["episode_id"], "decision_index": step["decision_index"],
                    "observation": step["observation"], "target_action": step["action"], "source": "scripted_reference_not_human_expert",
                    "expert_review_status": "pending"})
            elif step["action"]["name"] == "propose_design":
                repaired = next(s["action"]["arguments"]["plan"] for s in ep["steps"] if s["action"]["name"] == "revise_design")
                preferences.append({"schema_version": VERSION, "episode_id": ep["episode_id"], "observation": step["observation"],
                    "preferred_action": {"name": "propose_design", "arguments": {"plan": repaired}}, "rejected_action": step["action"],
                    "source": "scripted_comparison_not_human_preference", "expert_review_status": "pending"})
    for relative, records in (("labels/bc_train.jsonl", labels), ("labels/preferences_train.jsonl", preferences)):
        save(relative, records, jsonl=True); artifacts.append(relative)
    pending = [{"review_id": "review_"+digest([r["episode_id"], r["decision_index"]])[:16], "episode_id": r["episode_id"],
                "decision_index": r["decision_index"], "observation_hash": digest(r["observation"]), "proposed_action": r["target_action"],
                "review": {"status": "pending", "reviewer": None, "verdict": None, "reason": None, "reviewed_at": None}}
               for r in labels[::3]]
    save("review/pending.jsonl", pending, jsonl=True); artifacts.append("review/pending.jsonl")
    for domain in ("darcy", "cvit"):
        episode = next(ep for ep, t in zip(all_episodes, all_tasks) if t["domain"] == domain and t["policy_split"] == "train")
        task = next(t for t in all_tasks if t["task_id"] == episode["task_id"])
        relative = "examples/"+domain+"_full_example.json"
        save(relative, {"task": task, "episode": episode}); artifacts.append(relative)
    from schemas import TASK_SCHEMA, TRANSITION_SCHEMA, PPO_SCHEMA
    for relative, value in (("schemas/task.schema.json", TASK_SCHEMA), ("schemas/transition.schema.json", TRANSITION_SCHEMA), ("schemas/ppo_rollout.schema.json", PPO_SCHEMA)):
        save(relative, value); artifacts.append(relative)
    refs = []
    for source in (ROOT.parent/"RUT_Science/research/strategy_learning/studies/g2_3/lab/contracts.py",
                   ROOT.parent/"RUT_Science/research/strategy_learning/studies/g2_4/doe/schema.py"):
        relative = "reference_copy/"+source.parent.name+"_"+source.name
        path = ROOT/relative; path.parent.mkdir(exist_ok=True); shutil.copy2(source, path)
        refs.append({"source": str(source), "copy": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "not_imported": True})
        artifacts.append(relative)
    save("reference_copy/manifest.json", refs); artifacts.append("reference_copy/manifest.json")
    manifest = {"schema_version": VERSION, "date": DATE, "purpose": "Small exposed training-data examples and validation, not a scientific benchmark",
        "human_expert_labels": 0, "blind_heldout_tasks": 0, "policy_split_counts": {s: sum(t["policy_split"] == s for t in all_tasks) for s in SPLITS},
        "underlying_groups_disjoint": True, "shared_scenario_templates": True,
        "evaluation_example_is_public": True, "compatible_with_live_agent_loader": False,
        "ppo_training_data": False, "formal_training_transitions": 0, "real_scientific_data_copied": False,
        "artifact_sha256": {ref: hashlib.sha256((ROOT/ref).read_bytes()).hexdigest() for ref in artifacts}}
    save("manifest.json", manifest)
    from dataset_lib import validate_dataset
    print(canonical_result(validate_dataset()))


def canonical_result(value):
    import json
    return json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    main()
