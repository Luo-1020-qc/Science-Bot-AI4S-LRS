"""Fresh G2.3 train/dev/final task groups; past G2.2 final cases are not blind."""
from copy import deepcopy
import json
import random
from .guard import LAB, file_hash, write_json
from .contracts import digest
from .tasks import make_task, BASE_SCENARIOS
from .cvit_mock import CONFIGS

CV_TRAIN = ("pilot_run", "full_design", "explain_only", "denied_read", "insufficient_budget", "unknown_dataset",
            "unsupported_target", "existing_running", "existing_completed", "job_oom", "confirmation_denied", "data_change", "memory_low", "job_mismatch")
CV_FINAL = ("full_existing_completed", "pilot_seed_unknown", "full_data_change", "full_existing_running",
            "pilot_oom", "full_confirmation_revoked", "pilot_mismatched_existing", "full_memory_low")
TAB_FINAL = ("pair_conflict_revoke_v3", "prediction_unknown_features_v3", "prediction_change_transient_v3", "paired_unknown_permission_v3")


def tabular_task(scenario, split, i, seed):
    mapping = {"pair_conflict_revoke_v3": "paired_conflict", "prediction_unknown_features_v3": "predictive_run",
               "prediction_change_transient_v3": "goal_correction", "paired_unknown_permission_v3": "paired_unknown_source"}
    task = make_task(mapping.get(scenario, scenario), split, i, seed)
    task["scenario"] = scenario
    task["id"] = digest(["g2.3", split, scenario, i, seed])[:24]
    task["root_group"] = f"g2.3/{split}/{scenario}/{i}"
    task["hidden"]["profile"]["data_identity"] = digest(["fresh-g2.3-data", task["id"]])
    if scenario == "pair_conflict_revoke_v3":
        task["hidden"]["confirmation"] = "revoke"
    elif scenario == "prediction_unknown_features_v3":
        task["hidden"]["unknown_fields"] = ["features"]
        task["initial"].pop("features", None)
    elif scenario == "prediction_change_transient_v3":
        task["hidden"]["inspection_mode"] = "transient_once"
    elif scenario == "paired_unknown_permission_v3":
        task["initial_permissions"]["read"] = None
    task["domain"] = "tabular"
    return task


def cvit_task(scenario, split, i, seed):
    rng = random.Random(seed*1000+i)
    configuration = "full" if "full" in scenario else "pilot"
    facts = {"intent": "design" if scenario == "full_design" else "chat" if scenario == "explain_only" else "run",
             "dataset": "mock_darcy_fixture", "target": "pressure_field", "metric": "relative_l2", "seed": i+17,
             "configuration": configuration, "budget": 10}
    if scenario == "unsupported_target":
        facts["target"] = "temperature"
    if scenario == "insufficient_budget":
        facts["budget"] = 2
    initial = {key: value for key, value in facts.items() if rng.random() < .48}
    initial["intent"] = facts["intent"]
    unknown = ["dataset"] if scenario == "unknown_dataset" else ["seed"] if scenario == "pilot_seed_unknown" else []
    for field in unknown:
        initial.pop(field, None)
    existing = "running" if scenario in {"existing_running", "full_existing_running", "job_mismatch", "pilot_mismatched_existing"} else "completed" if scenario in {"existing_completed", "full_existing_completed"} else "none"
    return {"schema_version": "cvit_job_mock_v1", "domain": "cvit", "id": digest(["cvit_v3", split, scenario, i, seed])[:24],
            "root_group": f"cvit/{split}/{scenario}/{i}", "scenario": scenario, "split": split,
            "initial": initial, "read_allowed": scenario != "denied_read", "execute_allowed": facts["intent"] == "run",
            "hidden": {"facts": facts, "unknown_fields": unknown,
                       "profile": {"schema_version": "mock_cvit_config_v1", "data_identity": digest([split, scenario, i, seed]),
                                   "available_memory_gb": 2 if scenario in {"memory_low", "full_memory_low"} else 16,
                                   "split_protocol": "frozen_train_validation_test", "simulated": True},
                       "existing_job": existing, "existing_matches": scenario not in {"job_mismatch", "pilot_mismatched_existing"},
                       "job_outcome": "oom" if scenario in {"job_oom", "pilot_oom"} else "success",
                       "confirmation": "deny" if scenario == "confirmation_denied" else "revoke" if scenario == "full_confirmation_revoked" else "approve",
                       "change_data_after_confirm": scenario in {"data_change", "full_data_change"}},
            "provenance": "scripted_mock_job_not_real_cvit_experiment"}


def build_bank():
    if (LAB/"bank_v3/seal.json").exists():
        return verify_bank()
    records = {}
    for split, tab_count, cv_count, seed in (("train", 128, 112, 101), ("development", 48, 42, 307), ("heldout", 48, 48, 1009)):
        tab_scenarios = TAB_FINAL if split == "heldout" else BASE_SCENARIOS
        cv_scenarios = CV_FINAL if split == "heldout" else CV_TRAIN
        tasks = [tabular_task(tab_scenarios[i%len(tab_scenarios)], split, i, seed) for i in range(tab_count)]
        tasks += [cvit_task(cv_scenarios[i%len(cv_scenarios)], split, i, seed+23) for i in range(cv_count)]
        path = LAB/"bank_v3"/(split+".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(task, ensure_ascii=False)+"\n" for task in tasks), encoding="utf-8")
        records[split] = {"path": path.relative_to(LAB).as_posix(), "sha256": file_hash(path), "tasks": len(tasks),
                          "domains": {"tabular": tab_count, "cvit_mock": cv_count}, "scenario_groups": list(tab_scenarios)+list(cv_scenarios)}
    write_json(LAB/"bank_v3/seal.json", {"version": "g2_3_bank_v1", "date": "2026-10-26", "splits": records,
                 "past_g2_2_heldout": "Previously exposed; not reused as this delivery's blind test",
                 "heldout_scope": "Fresh synthetic source identities and held-out combinations; not wholly unseen primitive mechanisms",
                 "cvit_scope": "Job protocol/configuration mock only; no actual CViT code or dataset loaded"})
    write_json(LAB/"cvit_mock/fixtures/configurations.json", {"simulated": True, "configurations": CONFIGS,
               "job_metrics": None, "real_gpu_execution_allowed": False})
    source = LAB/"cvit_mock/fixtures/configurations.json"
    copy = LAB/"cvit_mock/test_copies/configurations.json"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(source.read_bytes())
    write_json(LAB/"evidence/cvit_fixture_copy.json", {"source": source.relative_to(LAB).as_posix(),
               "copy": copy.relative_to(LAB).as_posix(), "sha256": file_hash(source), "matches": file_hash(source) == file_hash(copy)})
    return verify_bank()


def verify_bank():
    seal = json.loads((LAB/"bank_v3/seal.json").read_text(encoding="utf-8"))
    for record in seal["splits"].values():
        if file_hash(LAB/record["path"]) != record["sha256"]:
            raise ValueError("G2.3 task bank changed")
    return {"sealed": True, "counts": {key: record["tasks"] for key, record in seal["splits"].items()}}


def load_split(split, purpose):
    if split not in {"train", "development", "heldout"} or purpose not in {"training", "development", "final_evaluation"}:
        raise ValueError("Invalid bank purpose")
    if split == "heldout" and purpose != "final_evaluation":
        raise PermissionError("Final tasks cannot enter training/model selection")
    verify_bank()
    return [json.loads(line) for line in (LAB/"bank_v3"/(split+".jsonl")).read_text(encoding="utf-8").splitlines() if line]
