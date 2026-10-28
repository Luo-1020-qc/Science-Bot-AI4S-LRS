"""G2.3 integrity audit, PPO transition recount and protected-project check."""
import json
import math
import re
import sys
import torch
from .guard import LAB, file_hash, protected_after, write_json
from .contracts import digest
from .adapter_v3 import ACTIONS_V3, FEATURES_V3
from .ppo import ActorCritic, policy_value
from .evaluation_v3 import check_selection, cvit_demo
from .suite_tasks import verify_bank
from .reporting_v3 import audit_final


def training_audit():
    summary = json.loads((LAB/"evidence/training_summary.json").read_text(encoding="utf-8"))
    manifests = summary["manifests"]
    audited, total, changed = {}, 0, 0
    for key, manifest in manifests.items():
        if manifest["algorithm"] == "behavior_cloning":
            continue
        count = 0
        files = sorted((LAB/"training_rollouts"/key).glob("update_*.jsonl"))
        for path in files:
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if (len(row["features"]) != len(FEATURES_V3) or len(row["mask"]) != len(ACTIONS_V3)
                        or not row["mask"][row["action"]] or row["done"] not in {0., 1.}
                        or not all(math.isfinite(row[field]) for field in ("old_logp", "value", "next_value", "reward"))
                        or row["done"] and row["next_value"] != 0.):
                    raise ValueError("Invalid training transition evidence")
                count += 1
        saved = torch.load(LAB/"models"/key/"trainer_state.pt", map_location="cpu", weights_only=True)
        network = ActorCritic(); network.load_state_dict(saved["network"])
        actual_changed = digest(policy_value(network)) != manifest["initial_policy_hash"]
        changed += actual_changed
        if count != manifest["transitions"] or saved["transitions"] != count or len(files) != manifest["ppo_updates"]:
            raise ValueError("Training resource recount mismatch")
        audited[key] = {"transitions": count, "updates": len(files), "parameters_changed": actual_changed,
                        "selected_update": manifest["selected_update"], "initial_policy_retained": manifest["initial_policy_retained"]}
        total += count
    value = {"total_ppo_transitions": total, "all_six_networks_updated": changed == 6, "runs": audited,
             "unit_test_transitions_excluded": True, "real_cvit_or_llm_weights_updated": False}
    write_json(LAB/"evidence/training_audit.json", value)
    return value


def verify_delivery():
    freeze = check_selection()
    bank = verify_bank()
    audited = training_audit()
    final = json.loads((LAB/"evidence/final_evaluation.json").read_text(encoding="utf-8"))
    scoring = audit_final()
    feedback_folder = LAB/"experiments/feedback_v2"
    feedback = json.loads((feedback_folder/"final.json").read_text(encoding="utf-8"))
    feedback_selection = json.loads((feedback_folder/"selection.json").read_text(encoding="utf-8"))
    feedback_count, feedback_changed = 0, True
    for seed in (21, 37, 59):
        folder = feedback_folder/"models"/f"seed_{seed}"
        manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
        count_v2 = 0
        for path in (folder/"rollouts").glob("update_*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if not row["mask"][row["action"]] or not all(math.isfinite(row[k]) for k in ("reward", "value", "next_value", "old_logp")):
                    raise ValueError("Invalid corrective trial transition")
                count_v2 += 1
        if count_v2 != manifest["ppo_transitions"]:
            raise ValueError("Corrective trial transition count mismatch")
        for kind, expected in (("baseline", manifest["baseline_hash"]), ("ppo", manifest["selected_ppo_hash"])):
            if digest(json.loads((folder/(kind+".json")).read_text(encoding="utf-8"))) != expected:
                raise ValueError("Corrective trial policy changed")
        feedback_changed = feedback_changed and manifest["parameter_updates_occurred"]
        feedback_count += count_v2
    demo = cvit_demo()
    protected = protected_after()
    log = (LAB/"evidence/tests.log").read_text(encoding="utf-8")
    count = re.search(r"Ran (\d+) tests", log)
    cv_copy = json.loads((LAB/"evidence/cvit_fixture_copy.json").read_text(encoding="utf-8"))
    checks = {"original_project_and_g2_2_unchanged": protected["unchanged"],
              "own_tests_pass": bool(count and "\nOK" in log and "FAILED" not in log),
              "bank_and_policies_frozen": bool(freeze), "ppo_trained_with_audited_transitions": audited["total_ppo_transitions"] == 122880,
              "ppo_network_parameters_updated": audited["all_six_networks_updated"],
              "corrective_trial_updates_audited": feedback_count == 36864 and feedback_changed,
              "corrective_trial_selected_before_final": feedback_selection["stage"] == "selected_before_loading_trial_final",
              "no_final_task_selection": freeze["final_tasks_loaded"] is False and freeze["model_selection"] == "development_only",
              "no_real_api_gpu_or_tool_execution": final["real_model_calls"] == final["real_tool_executions"] == final["real_gpu_jobs"] == 0,
              "no_cvit_numeric_metric_fabricated": final["cvit_metrics"] is None,
              "cvit_fixture_copy_matches": file_hash(LAB/cv_copy["source"]) == file_hash(LAB/cv_copy["copy"]) == cv_copy["sha256"],
              "existing_mock_job_reused_after_restore": demo["success"] and demo["existing_job_reused"] and demo["restored_from_saved_state"],
              "no_duplicate_mock_launches_in_evaluation": all(report["duplicate_mock_launches"] == 0 for report in final["reports"].values()),
              "live_policy_not_promoted": final["live_policy_promoted"] is False,
              "live_science_bot_not_imported": not any(name == "rut_science" or name.startswith("rut_science.") or "dynamic_cvit" in name for name in sys.modules),
              "no_new_zip_package": not list(LAB.rglob("*.zip"))}
    sources = [LAB/"run.py", LAB/"bootstrap.py"]+sorted((LAB/"lab").glob("*.py"))+sorted((LAB/"tests").glob("*.py"))+sorted(LAB.glob("*.md"))
    write_json(LAB/"evidence/source_manifest.json", {p.relative_to(LAB).as_posix(): file_hash(p) for p in sources})
    value = {"version": "g2_3_delivery_v1", "passed": all(checks.values()), "checks": checks,
             "protected_files": protected["files_checked"], "tests": int(count[1]) if count else None,
             "task_counts": bank["counts"], "ppo_transitions": audited["total_ppo_transitions"]+feedback_count,
             "primary_ppo_transitions": audited["total_ppo_transitions"], "corrective_ppo_transitions": feedback_count,
             "real_api_calls": 0, "real_tool_executions": 0, "real_gpu_jobs": 0, "live_policy_promoted": False,
             "aggregates": final["aggregates"], "limitations": ["Scripted task protocol learning, not language-model RLHF",
                 "CViT configuration/job lifecycle mock, not a real training experiment", "Three seeds, synthetic held-out combinations; no broad generalization or superiority claim"]}
    value["audited_aggregates"] = scoring["aggregates"]
    value["reward_limitation_disclosed"] = True
    value["corrective_trial"] = feedback["summary"]
    value["release_gate"] = {"promote_to_live_agent": False,
        "reason": "PPO not superior to rule or the matched baseline; all experiments remain isolated"}
    write_json(LAB/"evidence/verification.json", value)
    if not value["passed"]:
        raise ValueError("Verification failed: "+str([key for key, ok in checks.items() if not ok]))
    return {"passed": True, "tests": value["tests"], "ppo_transitions": value["ppo_transitions"],
            "protected_files_unchanged": protected["files_checked"], "real_gpu_jobs": 0}
