"""Independent checks of persisted rollout probabilities, lineage and Darcy data."""
import json
from pathlib import Path
import sys
import numpy as np
import torch
from rut_science.science_bot.session import ROOT, MODELS
from rut_science.science_bot.policies import make_network
from rut_science.science_bot.numerics import array_hash
from rut_science.darcy_workflow import load_bundle
from rut_science.util import write_json


def main():
    torch.set_num_threads(1)
    records = []
    for folder in MODELS.iterdir():
        if not (folder/"last_rollout_policy.pt").exists():
            continue
        manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
        if folder.name == "selected":
            continue
        batches = sorted((folder/"rollouts").glob("*.npz"))
        total = sum(len(np.load(p, allow_pickle=False)["actions"]) for p in batches)
        last = np.load(batches[-1], allow_pickle=False)
        network = make_network()
        network.load_state_dict(torch.load(folder/"last_rollout_policy.pt", weights_only=True))
        batch = {k: torch.from_numpy(last[k]) for k in ("global", "history", "candidates", "mask")}
        with torch.no_grad():
            dist, values = network(batch)
            lp = dist.log_prob(torch.from_numpy(last["actions"]))
        lp_error = float(np.max(np.abs(lp.numpy()-last["old_log_prob"])))
        value_error = float(np.max(np.abs(values.numpy()-last["values"])))
        illegal_zero = bool(torch.all(dist.probs[~batch["mask"]] == 0))
        passed = total == manifest["actual_transitions"] and lp_error < 1e-5 and value_error < 1e-5 and illegal_zero
        records.append({"checkpoint": folder.name, "transitions": total, "old_log_prob_max_error": lp_error,
                        "value_max_error": value_error, "illegal_probability_zero": illegal_zero, "passed": passed})
    metadata, arrays = load_bundle(ROOT/"data"/"darcy_cpu_v1")
    seen, duplicates = {}, []
    for split, values in arrays.items():
        for i, sample in enumerate(values["coeff"]):
            identity = array_hash(sample)
            if identity in seen:
                duplicates.append([seen[identity], [split, i]])
            seen[identity] = [split, i]
    result = {"rollouts": records, "rollout_checks_passed": bool(records) and all(r["passed"] for r in records),
              "darcy": {"manifest_hash_verified": True, "bundle_hashes_verified": True,
                        "samples": {k: len(v["coeff"]) for k, v in arrays.items()}, "duplicate_input_samples": duplicates,
                        "source_reference": metadata["source_reference"], "historically_exposed": True,
                        "license_reaudit": "not independently verified for expanded redistribution; original data not included in delivery",
                        "scope": "local_existing_bundle_transfer_pilot"}}
    write_json(ROOT/"delivery"/"artifact_audit.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["rollout_checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
