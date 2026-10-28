"""Prepare an auditable cleanup plan. All move/delete operations use native PowerShell."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT/"docs/cleanup/2026-10-28"
ARCHIVE = ROOT.parent/"ScienceBot_Archive_2026-10-28"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""): h.update(chunk)
    return h.hexdigest()


def main():
    if (RECORD/"plan.json").exists() or ARCHIVE.exists(): raise ValueError("Cleanup already planned; do not overwrite evidence")
    RECORD.mkdir(parents=True)
    moves, deletes = [], []
    def move(relative, target=None, reason="historical_material_outside_harness_workspace"):
        source = ROOT/relative
        if source.exists(): moves.append({"source": relative, "destination": str(ARCHIVE/(target or relative)), "reason": reason})
    # Preserve checkpoint material in the main Harness before removing old deliveries.
    if (ROOT/"RUT_Science/delivery/policy_checkpoint").exists():
        moves.append({"source": "RUT_Science/delivery/policy_checkpoint", "destination": str(ROOT/"RUT_Science/models/retained_delivery_checkpoint"), "reason": "retain_all_existing_checkpoint_material_inside_harness"})
    for relative in ("RUT_Science/outputs", "RUT_Science/delivery", "maintenance", "RUT_Science/docs"):
        move(relative)
    for path in ROOT.glob("*.md"):
        if path.name not in {"README.md", "CHANGELOG.md", "CONTRIBUTING.md"}: move(path.name, "historical_documents/"+path.name, "merged_into_current_progress_and_usage_documents")
    move("RUT_Science/README.md", reason="application_readme_merged_into_root_navigation")
    keep_scripts = {"science_bot_research.py", "train_design_interview.py", "export_design_review.py", "check_agent_api_config.py"}
    for path in (ROOT/"RUT_Science/scripts").glob("*"):
        if path.is_file() and path.name not in keep_scripts: move(path.relative_to(ROOT).as_posix(), reason="historical_delivery_and_standalone_scientific_launchers")
    hub = ROOT/"RUT_Science/research/strategy_learning"
    for study in (hub/"studies").iterdir():
        if not study.is_dir(): continue
        for suffix in ("evidence/documents_before", "evidence/pre_consolidation", "current_test_outputs", "test_outputs", "cache"):
            move((study/suffix).relative_to(ROOT).as_posix(), reason="superseded_document_snapshots_or_regenerable_test_runs")
        for path in study.glob("*.md"): move(path.relative_to(ROOT).as_posix(), reason="study_delivery_documents_merged_into_progress")
    move("Training_Data_Darcy_CViT/v2/tool_runtime/sessions", reason="historical_synthetic_sessions_not_training_inputs")
    move("Research_Tool_Library/test_fixture", reason="regenerable_test_fixture")
    legacy = ["v1", "tasks", "episodes", "labels", "evaluator_only", "review", "examples", "schemas", "reference_copy", "tests",
              "build_examples.py", "dataset_lib.py", "manifest.json", "schemas.py", "validate.py", "validation.json", "validation_tests.log", "project_integrity.json", "prepare_v2.py"]
    dataset = ROOT/"Training_Data_Darcy_CViT"
    for name in legacy:
        if (dataset/name).exists(): deletes.append({"source": (dataset/name).relative_to(ROOT).as_posix(), "reason": "explicitly_retired_v1_dataset_and_duplicate_compatibility_tree"})
    for path in dataset.glob("*.md"):
        if path.name.startswith("字段"): deletes.append({"source": path.relative_to(ROOT).as_posix(), "reason": "retired_v1_field_guide_superseded_by_v2_and_expert_handoff"})
    for name in ("v1_snapshot.json", "original_root_names.json"):
        deletes.append({"source": "Training_Data_Darcy_CViT/v2/"+name, "reason": "retired_v1_migration_inventory"})
    excluded = (".git", ".venv", "__pycache__")
    files = {}
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in excluded for part in relative.parts) or not path.is_file() or relative.parts[:2] == ("docs", "cleanup"): continue
        if path.name == "API_key_Agent.json": continue
        files[relative.as_posix()] = {"sha256": sha(path), "bytes": path.stat().st_size}
    # Never delete a model/checkpoint/policy even when duplicates exist elsewhere.
    def is_weight(name):
        p = Path(name)
        return any(part in {"models", "policy_checkpoint"} for part in p.parts) or p.suffix.lower() in {".pt", ".pth", ".onnx", ".safetensors"} or any(word in p.name.lower() for word in ("policy.json", "weights", "checkpoint"))
    weights = {name: row for name, row in files.items() if is_weight(name)}
    architecture = {name: row for name, row in files.items() if name.startswith("RUT_Science/rut_science/") or name.startswith("RUT_Science/prompts/")}
    frozen = json.loads((hub/"online_artifacts.json").read_text(encoding="utf-8"))["studies"]
    frozen_paths = {"RUT_Science/research/strategy_learning/studies/"+study+"/"+name for study, entries in frozen.items() for name in entries}
    architecture.update({name: files[name] for name in frozen_paths})
    architecture.update({name: files[name] for name in files if name.startswith("Training_Data_Darcy_CViT/v2/") and ("/ppo_" in name or name.endswith(("/environment.py", "/protocol.py", "/ppo_smoke.py"))) and "/sessions/" not in name})
    for item in deletes:
        prefix = item["source"]+"/"
        if any(name == item["source"] or name.startswith(prefix) for name in weights | architecture):
            raise ValueError("Deletion intersects protected architecture/weights: "+item["source"])
    # Map each pre-cleanup weight/architecture to its final location.
    def destination(name):
        for item in moves:
            if name == item["source"] or name.startswith(item["source"]+"/"):
                return str(Path(item["destination"])/Path(name).relative_to(item["source"]))
        return str(ROOT/name)
    protected = {name: {**row, "final_path": destination(name)} for name, row in (architecture | weights).items()}
    (RECORD/"protected_before.json").write_text(json.dumps({"files": protected, "weight_files": sorted(weights), "architecture_files": sorted(architecture)}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (RECORD/"inventory_before.json").write_text(json.dumps({"files": files}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    plan = {"project_root": str(ROOT), "archive_root": str(ARCHIVE), "moves": moves, "deletes": deletes,
            "protected_file_count": len(protected), "weight_file_count": len(weights), "architecture_file_count": len(architecture)}
    (RECORD/"plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"move_entries": len(moves), "obsolete_delete_entries": len(deletes), "protected_files": len(protected), "weight_files": len(weights), "archive": str(ARCHIVE)}, ensure_ascii=False))


if __name__ == "__main__": main()
