"""Bounded design compiler; nominal power is conditional on declared assumptions."""
from collections import Counter
from itertools import product
import random
import numpy as np
from scipy.stats import nct, t


def layout(contract):
    family, factors, blocks, repetitions = (contract[k] for k in ("family", "factors", "blocks", "replicates"))
    if len({f["name"] for f in factors}) != len(factors):
        raise ValueError("Duplicate factor names")
    if family in {"crd_two_arm", "rcbd_two_arm"} and len(factors) != 1:
        raise ValueError("Two-arm designs require one two-level factor")
    if family == "crd_two_arm" and blocks:
        raise ValueError("CRD does not have declared blocks")
    if family == "rcbd_two_arm" and (len(blocks) < 2 or repetitions != 1):
        raise ValueError("RCBD v1 requires >=2 blocks and one unit per treatment per block")
    if family == "factorial_2x2" and (len(factors) != 2 or (blocks and len(blocks) < 2)):
        raise ValueError("Factorial requires two factors and either zero or >=2 blocks")
    if family not in {"crd_two_arm", "rcbd_two_arm", "factorial_2x2"}:
        raise ValueError("Unsupported design family")
    combinations = list(product(*(factor["levels"] for factor in factors)))
    count = len(combinations)*repetitions*max(1, len(blocks))
    if not 4 <= count <= 1000:
        raise ValueError("Design exceeds the 4..1000 planned-unit limit")
    return blocks or ["unblocked"], combinations


def compile_plan(contract):
    blocks, combinations = layout(contract)
    # Separate deterministic streams for unit allocation and run ordering.
    allocation = random.Random(str(contract["randomization"]["seed"])+":allocation:v1")
    order = random.Random(str(contract["randomization"]["seed"])+":order:v1")
    rows = []
    for block_index, block in enumerate(blocks):
        treatments = list(combinations)*contract["replicates"]
        allocation.shuffle(treatments)
        inside = [{"unit_id": f"planned_b{block_index+1}_u{i+1}", "block": block, "levels": list(levels)}
                  for i, levels in enumerate(treatments)]
        order.shuffle(inside)
        rows.extend(inside)
    return [{"run": i+1, **row} for i, row in enumerate(rows)]


def matrix(contract):
    names = [f["name"] for f in contract["factors"]]
    columns = ["intercept", *names]
    if contract["family"] == "factorial_2x2":
        columns.append(":".join(names))
    blocks = contract["blocks"]
    columns += ["block:"+block for block in blocks[1:]]
    rows = []
    for run in contract["run_plan"]:
        coded = [-1.0 if level == factor["levels"][0] else 1.0 if level == factor["levels"][1] else float("nan")
                 for factor, level in zip(contract["factors"], run["levels"])]
        if len(coded) != len(names):
            raise ValueError("Run treatment dimensions differ")
        row = [1.0, *coded]
        if contract["family"] == "factorial_2x2":
            row.append(coded[0]*coded[1])
        row += [float(run["block"] == block) for block in blocks[1:]]
        rows.append(row)
    x = np.array(rows, dtype=float)
    if not np.isfinite(x).all():
        raise ValueError("Run contains unknown factor levels")
    return x, columns


def diagnose(contract):
    x, columns = matrix(contract)
    rank = int(np.linalg.matrix_rank(x))
    df = len(x)-rank
    term = contract["analysis"]["primary_term"]
    report = {"runs": len(x), "columns": columns, "rank": rank, "parameters": len(columns), "residual_df": df,
              "full_rank": rank == len(columns), "nominal_power": None, "power_scope": "conditional_gaussian_homoscedastic_fixed_effect_model"}
    if term not in columns[1:] or term.startswith("block:"):
        return {**report, "primary_estimable": False}
    c = np.zeros(len(columns))
    c[columns.index(term)] = 4.0 if ":" in term else 2.0
    projection = np.linalg.pinv(x)@x
    estimable = bool(np.allclose(c@projection, c, atol=1e-9, rtol=1e-9))
    report["primary_estimable"] = estimable
    cells = Counter((r["block"], tuple(r["levels"])) for r in contract["run_plan"])
    report["pure_error_df"] = sum(n-1 for n in cells.values())
    if not estimable or not report["full_rank"] or df <= 0:
        return report
    variance_factor = float(c@np.linalg.inv(x.T@x)@c)
    sigma = contract["analysis"]["sigma"]
    se = sigma*np.sqrt(variance_factor)
    nc = contract["analysis"]["minimum_effect"]/se
    critical = float(t.isf(contract["analysis"]["alpha"]/2, df))
    power = float(nct.sf(critical, df, nc)+nct.cdf(-critical, df, nc))
    if not np.isfinite([se, nc, critical, power]).all():
        raise ValueError("Non-finite statistical diagnostic")
    sensitivity = [{"sigma_multiplier": multiplier,
        "nominal_power": float(nct.sf(critical, df, nc/multiplier)+nct.cdf(-critical, df, nc/multiplier))}
        for multiplier in (1.0, 1.25, 1.5)]
    return {**report, "contrast": c.tolist(), "contrast_definition": "difference_in_differences" if ":" in term else "high_minus_low_average",
            "variance_factor": variance_factor, "planned_standard_error": float(se), "noncentrality": float(nc),
            "critical_t": critical, "nominal_power": power, "sigma_sensitivity": sensitivity,
            "pilot_variance_uncertainty_integrated": False}


def compile_workflow(contract):
    """Reviewable experiment steps; execution and inference remain unavailable."""
    items = [
        ("ground_facts", [], "Every required claim has a current source; unresolved facts block submission"),
        ("check_design", ["ground_facts"], "Unit allocation, model, estimability, nominal power and budget pass the verifier"),
        ("preregister", ["check_design"], "Freeze request, contract, primary contrast, alpha, analysis, missing-data rule and run order"),
        ("external_review", ["preregister"], "Review real-world assumptions and obtain separate host authorization"),
        ("collect_outcomes", ["external_review"], "Record actual assignment, treatment application, measurement, deviations and failures"),
        ("analyze", ["collect_outcomes"], "Check assumptions; use the prespecified model and unit-level response; deviations require review"),
        ("report", ["analyze"], "Report effect, two-sided interval, practical relevance, exclusions and limitations including negative results")]
    return {"version": "doe_steps_v1", "mode": "design_review_only", "contract_family": contract["family"],
        "steps": [{"id": name, "depends_on": deps, "acceptance": criterion, "executed": False} for name, deps, criterion in items],
        "execution_authorized": False, "observed_outcomes": None}
