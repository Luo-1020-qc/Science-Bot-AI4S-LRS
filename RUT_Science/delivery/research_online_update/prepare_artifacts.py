"""Freeze read-only worker inputs; keep original research byte-identical."""
from pathlib import Path
import hashlib
import json
import shutil

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
HUB = PROJECT/"RUT_Science/research/strategy_learning"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = HUB/"online_artifacts.json"
    if target.exists() and (HERE/"verification.json").exists():
        raise ValueError("Online artifact manifest already exists")
    studies = {}
    for study in ("g2_2", "g2_3", "g2_4"):
        folder = HUB/"studies"/study
        paths = list((folder/("doe" if study == "g2_4" else "lab")).glob("*.py"))
        extras = {
            "g2_2": ["bank/seal.json", "bank/development.jsonl", "evidence/benchmark.json", "evidence/freeze.json", "review/pending.jsonl", "training/reference_train.jsonl"],
            "g2_3": ["bank_v3/seal.json", "bank_v3/development.jsonl", "evidence/scoring_audit.json", "evidence/selection_freeze.json", "experiments/feedback_v2/final.json", "experiments/feedback_v2/selection.json"],
            "g2_4": ["bank/train.jsonl", "bank/seal.json", "review/pending.jsonl", "evidence/protocol_freeze.json", "evidence/development_diagnostics.json", "schemas/experiment_contract.schema.json", "schemas/request.schema.json"]}[study]
        paths += [folder/name for name in extras]
        paths += list((folder/"models").rglob("policy.json"))
        if study == "g2_3":
            paths += [p for p in (folder/"experiments/feedback_v2/models").rglob("*.json") if p.name in {"baseline.json", "ppo.json"}]
        studies[study] = {path.relative_to(folder).as_posix(): sha(path) for path in paths}
    value = {"version": "research_online_artifacts_v1", "date": "2026-10-27", "studies": studies,
             "training_exposed": False, "live_tools_exposed": False}
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    # Snapshot explicitly authorized app edits before any later audit comparison.
    baseline = json.loads((HERE/"protected_before.json").read_text(encoding="utf-8"))["files"]
    print(json.dumps({"study_artifacts": {k: len(v) for k, v in studies.items()}, "protected_baseline_files": len(baseline)}))


if __name__ == "__main__":
    main()
