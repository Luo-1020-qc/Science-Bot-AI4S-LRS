"""Versioned synthetic interview task bank. Hidden facts never enter policy observations."""
from copy import deepcopy
import json
import random
from .contracts import digest
from .guard import LAB, file_hash, write_json

BASE_SCENARIOS = ("ordinary_comparison", "paired_design", "predictive_run", "explanation_only", "negated_execution",
                  "ambiguous_intent", "unknown_structure", "clustered_data", "missing_cases", "read_denied",
                  "transient_inspection", "bad_tool_schema", "goal_correction", "conflicting_response", "low_budget", "causal_claim")
HOLDOUT_SCENARIOS = ("paired_revocation", "prediction_goal_correction", "missing_read_denied", "paired_unknown_source",
                     "paired_conflict", "temporal_prediction", "prediction_transient", "comparison_confirmation_denied")


def make_task(scenario, split, index, seed):
    rng = random.Random(seed*1000+index)
    family = "paired" if "paired" in scenario else "prediction" if "predict" in scenario else "independent"
    truth = {"intent": "run", "goal": "prediction" if family == "prediction" else "compare_means",
             "unit_structure": "paired_units" if family == "paired" else "independent_rows",
             "response": "response", "unit": "unit_id", "provenance": "synthetic",
             "sample_basis": "available_exploratory", "factor": "condition", "levels": ["control", "treatment"],
             "features": ["x1", "x2"], "missing_policy": "reject"}
    if scenario in {"paired_design", "ordinary_comparison", "negated_execution", "unknown_structure", "clustered_data", "causal_claim"}:
        truth["intent"] = "design"
    if scenario == "explanation_only":
        truth["intent"] = "chat"
    if scenario == "causal_claim":
        truth["goal"], truth["provenance"] = "causal_effect", "observational"
    if scenario == "clustered_data":
        truth["unit_structure"] = "clustered"
    if scenario == "temporal_prediction":
        truth["unit_structure"] = "temporal"
    read_permission = False if scenario in {"read_denied", "missing_read_denied", "explanation_only", "negated_execution"} else True
    execution_permission = truth["intent"] == "run"
    permission_initial = {"read": read_permission, "execute": execution_permission}
    if scenario in {"ambiguous_intent", "read_denied", "missing_read_denied"}:
        permission_initial["read"] = None
        permission_initial["execute"] = None
    initial = {name: deepcopy(value) for name, value in truth.items() if rng.random() < .42}
    if scenario == "ambiguous_intent":
        initial.pop("intent", None)
    else:
        initial["intent"] = truth["intent"]
    if scenario == "explanation_only":
        initial["goal"] = "compare_means"
    unknown = []
    if scenario == "unknown_structure":
        unknown = ["unit_structure"]
    if scenario == "paired_unknown_source":
        unknown = ["provenance"]
    for name in unknown:
        initial.pop(name, None)
    events = []
    if scenario in {"goal_correction", "prediction_goal_correction"}:
        initial["goal"] = "compare_means"
        truth["goal"] = "prediction"
        events.append({"when": "after_first_question", "type": "correction", "fields": {"goal": "prediction"}})
    if scenario in {"conflicting_response", "paired_conflict"}:
        initial["response"] = "old_response"
        events.append({"when": "after_first_question", "type": "conflict", "fields": {"response": "response"}})
    # A changed goal produces a different method even with unchanged unit data.
    if scenario == "goal_correction":
        family = "prediction"
    missing = .15 if scenario in {"missing_cases", "missing_read_denied"} else 0
    if missing:
        truth["missing_policy"] = "drop_complete_case"
        initial.pop("missing_policy", None)
    mode = "transient_once" if scenario in {"transient_inspection", "prediction_transient"} else "bad_schema" if scenario == "bad_tool_schema" else "ok"
    profile = {"schema_version": "mock_csv_profile_v1", "columns": ["unit_id", "condition", "response", "x1", "x2"],
               "rows": rng.choice([40, 60, 80]), "rows_per_unit": 2 if family == "paired" else 1,
               "missing_fraction": missing, "estimated_execution_cost": 6 if truth["goal"] == "prediction" else 3,
               "data_identity": digest([split, scenario, index, seed]), "simulated": True}
    prompt = {"explanation_only": "如何执行配对比较？现在只解释，不读取也不执行。",
              "negated_execution": "不要读取数据或执行实验，只讨论设计。",
              "ambiguous_intent": "这个数据可以做什么？请先弄清楚我的目标。"}.get(scenario, "请根据已声明事实设计合适实验，缺项先提问；执行需明确授权。")
    return {"schema_version": "g2_2_task_v2", "id": digest([split, scenario, index, seed])[:20], "split": split,
            "root_group": f"{split}/{scenario}/{index}", "scenario": scenario, "family": family, "prompt": prompt,
            "initial": initial, "initial_permissions": permission_initial,
            "visible_hints": {"short_interaction_preferred": True, "declared_goal_uncertain": scenario == "ambiguous_intent"},
            "question_budget": 14, "resource_budget": 2 if scenario == "low_budget" else 12,
            "hidden": {"facts": truth, "unknown_fields": unknown, "read_permission": read_permission,
                       "execute_permission": execution_permission, "confirmation": "revoke" if scenario == "paired_revocation" else "deny" if scenario == "comparison_confirmation_denied" else "approve",
                       "profile": profile, "inspection_mode": mode, "events": events},
            "provenance": "synthetic_template_not_human_expert", "fixture_alias": "copied_paired" if family == "paired" else "copied_prediction" if family == "prediction" else "copied_groups"}


def build_bank():
    seal_path = LAB/"bank/seal.json"
    if seal_path.exists():
        return verify_bank()
    counts = {"train": 192, "development": 64, "heldout": 96}
    records = {}
    for split, count in counts.items():
        scenarios = HOLDOUT_SCENARIOS if split == "heldout" else BASE_SCENARIOS
        tasks = [make_task(scenarios[i % len(scenarios)], split, i, {"train": 31, "development": 71, "heldout": 113}[split]) for i in range(count)]
        path = LAB/"bank"/(split+".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(task, ensure_ascii=False)+"\n" for task in tasks), encoding="utf-8")
        records[split] = {"path": path.relative_to(LAB).as_posix(), "sha256": file_hash(path), "count": count, "scenarios": list(scenarios)}
    write_json(seal_path, {"schema_version": "g2_2_bank_seal_v1", "date": "2026-10-26", "splits": records,
                          "heldout_policy": "Heldout scenarios are absent from train/development. Sealed before BC training; final task records loaded only for evaluation.",
                          "expert_status": "No human expert labels yet; reference actions are synthetic curriculum labels"})
    return verify_bank()


def verify_bank():
    seal = json.loads((LAB/"bank/seal.json").read_text(encoding="utf-8"))
    for record in seal["splits"].values():
        if file_hash(LAB/record["path"]) != record["sha256"]:
            raise ValueError("Frozen task bank changed")
    return {"sealed": True, "counts": {split: record["count"] for split, record in seal["splits"].items()}}


def load_split(split, *, purpose):
    if split not in {"train", "development", "heldout"} or purpose not in {"training", "development", "final_evaluation", "test"}:
        raise ValueError("Invalid bank access purpose")
    if split == "heldout" and purpose not in {"final_evaluation", "test"}:
        raise PermissionError("Heldout tasks cannot be used to train or select models")
    verify_bank()
    return [json.loads(line) for line in (LAB/"bank"/(split+".jsonl")).read_text(encoding="utf-8").splitlines() if line]
