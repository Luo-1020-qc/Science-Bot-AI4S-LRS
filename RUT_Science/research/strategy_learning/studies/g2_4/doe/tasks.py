"""Synthetic protocol calibration cases; reference expectations are not expert labels."""
from copy import deepcopy
from .compiler import compile_plan
from .guard import LAB
from .io import digest, read, rows, sha, write, write_rows
from .schema import CLAIM_PATHS, FAMILIES, VERSION

SCENARIOS = ("valid", "technical_repeats", "duplicate_units", "unrandomized_schedule", "missing_cell",
    "wrong_model", "low_power", "over_budget", "forged_sigma", "unavailable_fact", "unanswered_fact",
    "missing_provenance", "changed_primary", "unsupported_scope")


def request_for(contract):
    evidence = [{"id": f"e{i:02d}", "path": path, "value": deepcopy(contract[path[1:]]), "status": "provided",
                 "source": "synthetic_fixture", "reference": "Synthetic user/pilot statement; not real-world verification"}
                for i, path in enumerate((*CLAIM_PATHS, "/family"))]
    return {"schema_version": "doe_request_v1", "scope": "design_only", "requested_family": contract["family"],
            "execution_permission": "denied", "evidence": evidence}


def base_contract(family="crd_two_arm", seed=1):
    factorial = family == "factorial_2x2"
    blocks = [f"b{i+1}" for i in range(6 if factorial else 24)] if family != "crd_two_arm" else []
    factors = [{"name": "A", "levels": ["control", "candidate"]}]
    if factorial:
        factors.append({"name": "B", "levels": ["low", "high"]})
    assumptions = ["normal_iid_errors", "constant_error_variance"]
    if blocks:
        assumptions.append("no_treatment_block_interaction")
    scale = 1+(seed % 7)/10
    contract = {"schema_version": VERSION, "request_hash": "0"*64, "revision": 1,
        "question": "Estimate the prespecified high-minus-low effect on a synthetic response",
        "family": family, "factors": factors, "response": {"name": "synthetic_error", "unit": "declared_units", "direction": "lower"},
        "experimental_unit": {"definition": "One separately allocated synthetic treatment application",
            "independence_basis": "Declared independent units and independent Gaussian residuals; not established by table structure",
            "measurement_repeats": 1},
        "blocks": blocks, "replicates": 2 if factorial else 1 if blocks else 24,
        "assumptions": assumptions, "randomization": {"seed": seed, "algorithm": "shuffle_v1"},
        "analysis": {"model": "blocked_full_factorial" if factorial else "additive_blocks" if blocks else "two_arm",
            "primary_term": "A", "alpha": .05, "minimum_effect": scale, "sigma": scale, "target_power": .8,
            "multiplicity": "single_primary", "missing_policy": "stop_and_review",
            "decision_rule": "two_sided_t_ci_practical_relevance_separate"},
        "resources": {"per_run": 1.0, "budget": 100.0},
        "provenance": [{"path": path, "evidence_id": f"e{i:02d}"} for i, path in enumerate(CLAIM_PATHS)], "run_plan": []}
    contract["run_plan"] = compile_plan(contract)
    request = request_for(contract)
    contract["request_hash"] = digest(request)
    return request, contract


def make_case(family, scenario, split, index):
    request, contract = base_contract(family, 1000+index)
    if scenario == "technical_repeats":
        contract["experimental_unit"]["measurement_repeats"] = 20
        request = request_for(contract)
    elif scenario == "over_budget":
        contract["resources"]["budget"] = 2.0
        request = request_for(contract)
    elif scenario == "low_power":
        if family == "rcbd_two_arm":
            contract["blocks"] = ["b1", "b2"]
        else:
            contract["replicates"] = 2 if family == "crd_two_arm" else 1
            if family == "factorial_2x2":
                contract["blocks"] = ["b1", "b2"]
        contract["run_plan"] = compile_plan(contract)
        request = request_for(contract)
    contract["request_hash"] = digest(request)
    expected = {"ready": scenario in {"valid", "technical_repeats"}, "blocker": None, "stop_required": False}
    if scenario == "duplicate_units":
        contract["run_plan"][1]["unit_id"] = contract["run_plan"][0]["unit_id"]
        expected["blocker"] = "experimental_units"
    elif scenario == "unrandomized_schedule":
        contract["run_plan"] = sorted(contract["run_plan"], key=lambda row: (row["block"], row["levels"]))
        for i, row in enumerate(contract["run_plan"]):
            row["run"] = i+1
        expected["blocker"] = "randomization_schedule"
    elif scenario == "missing_cell":
        missing = contract["run_plan"][0]["levels"]
        contract["run_plan"] = [row for row in contract["run_plan"] if row["levels"] != missing]
        expected["blocker"] = "estimability"
    elif scenario == "wrong_model":
        contract["analysis"]["model"] = "two_arm" if family != "crd_two_arm" else "full_factorial"
        expected["blocker"] = "analysis_model"
    elif scenario == "forged_sigma":
        contract["analysis"]["sigma"] /= 100
        expected["blocker"] = "evidence_grounding"
    elif scenario in {"unavailable_fact", "unanswered_fact"}:
        row = next(row for row in request["evidence"] if row["path"] == "/analysis")
        row.update(value=None, status="unavailable" if scenario == "unavailable_fact" else "unanswered")
        contract["request_hash"] = digest(request)
        expected.update(blocker="critical_facts_available", stop_required=scenario == "unavailable_fact")
    elif scenario == "missing_provenance":
        contract["provenance"].pop()
        expected["blocker"] = "contract_schema"
    elif scenario == "changed_primary":
        contract["analysis"]["primary_term"] = "intercept"
        expected["blocker"] = "evidence_grounding"
    elif scenario == "unsupported_scope":
        request["requested_family"] = "split_plot"
        next(row for row in request["evidence"] if row["path"] == "/family")["value"] = "split_plot"
        contract["request_hash"] = digest(request)
        expected.update(blocker="supported_scope", stop_required=True)
    elif scenario == "low_power":
        expected["blocker"] = "nominal_power"
    elif scenario == "over_budget":
        expected["blocker"] = "run_budget"
    return {"task_id": f"g24_{split}_{index:04d}", "root_group": f"g24_{split}_source_{index:04d}", "split": split,
            "scenario": scenario, "family": family, "request": request, "candidate": contract,
            "expected": expected, "label_source": "synthetic_protocol_reference_not_expert"}


def public_observation(task):
    return deepcopy({"request": task["request"], "candidate": task["candidate"]})


def build_bank():
    path = LAB/"bank/seal.json"
    if path.exists():
        return verify_bank()
    splits = {}
    counter = 0
    for split, repeats in (("train", 2), ("development", 1), ("heldout", 1)):
        cases = []
        for _ in range(repeats):
            for family in FAMILIES:
                for scenario in SCENARIOS:
                    counter += 1
                    cases.append(make_case(family, scenario, split, counter))
        target = LAB/"bank"/(split+".jsonl")
        write_rows(target, cases, fresh=True)
        splits[split] = {"path": target.relative_to(LAB).as_posix(), "sha256": sha(target), "count": len(cases),
                         "source_groups": [row["root_group"] for row in cases]}
    value = {"version": "doe_calibration_bank_v1", "date": "2026-10-27", "splits": splits,
        "scenario_templates_shared": True, "independent_expert_case_authors": 0,
        "limitations": "Synthetic regression/calibration templates. Source ids disjoint; shared generator is not independent domain generalization."}
    write(path, value, fresh=True)
    return verify_bank()


def verify_bank():
    seal = read(LAB/"bank/seal.json")
    groups = []
    for row in seal["splits"].values():
        if sha(LAB/row["path"]) != row["sha256"]:
            raise ValueError("Frozen task bank changed")
        groups.extend(row["source_groups"])
    if len(set(groups)) != len(groups):
        raise ValueError("Source group overlap")
    return {"counts": {name: row["count"] for name, row in seal["splits"].items()}, "hashes_match": True, "source_groups_disjoint": True}


def load_split(split, *, purpose):
    allowed = {"training": {"train"}, "review": {"train"}, "development": {"development"}}
    if purpose not in allowed or split not in allowed[purpose]:
        raise PermissionError("G2.4 does not open heldout task records or use dev/test for training/review")
    verify_bank()
    return rows(LAB/"bank"/(split+".jsonl"))
