"""Paired analysis: preserve task/seed pairs and bootstrap root tasks, not rewrites."""
from collections import Counter, defaultdict
import random
from statistics import mean

from .contracts import BEHAVIORS


def clustered_gap(records: list[dict], behavior: str, samples: int = 1000) -> dict:
    index = {(r["task_id"], r["seed"], r["behavior"]): r["score"]["execution_success"] for r in records}
    grouped = defaultdict(list)
    for task_id, seed, kind in index:
        if kind == behavior:
            ideal = index.get((task_id, seed, "ideal"))
            changed = index[(task_id, seed, kind)]
            if ideal is not None and changed is not None:
                grouped[task_id].append(int(ideal)-int(changed))
    if not grouped:
        return {"gap_pp": None, "ci95_pp": None, "paired_runs": 0, "task_clusters": 0}
    task_means = [mean(values) for _, values in sorted(grouped.items())]
    rng = random.Random(903)
    boot = sorted(mean(rng.choices(task_means, k=len(task_means))) for _ in range(samples))
    return {"gap_pp": 100*mean(task_means), "ci95_pp": [100*boot[int(samples*0.025)], 100*boot[int(samples*0.975)]],
            "paired_runs": sum(map(len, grouped.values())), "task_clusters": len(grouped),
            "method": "task_cluster_bootstrap; absolute percentage points; small authored development set"}


def summarize(records: list[dict]) -> dict:
    output = {}
    for agent in sorted({r["agent"] for r in records}):
        own = [r for r in records if r["agent"] == agent]
        core = [r for r in own if r["suite"] == "paired_core"]
        scored = [r for r in core if r["score"]["execution_success"] is not None]
        rows = {}
        for behavior in BEHAVIORS:
            valid = [r for r in scored if r["behavior"] == behavior]
            rows[behavior] = {
                "n": len(valid), "successes": sum(r["score"]["execution_success"] for r in valid),
                "sr": mean(r["score"]["execution_success"] for r in valid) if valid else None,
                "paired_gap": clustered_gap(core, behavior),
            }
        response = [r for r in own if r["suite"] == "response_only" and r["score"]["interaction_success"] is not None]
        output[agent] = {
            "behavior_results": rows, "core_runs": len(core), "scored_core_runs": len(scored),
            "overall_execution_sr": mean(r["score"]["execution_success"] for r in scored) if scored else None,
            "state_only_sr_extension": mean(r["score"]["state_only_success_extension"] for r in scored) if scored else None,
            "response_runs": len(response),
            "interaction_success_rate_extension": mean(r["score"]["interaction_success"] for r in response) if response else None,
            "infrastructure_errors": sum(r["episode"]["termination"] in {"service_error", "adapter_error"} for r in own),
            "failures": dict(Counter(r["score"]["primary_failure"] for r in scored if r["score"]["primary_failure"])),
            "mean_tool_calls": mean(sum(e["event_type"] == "tool_call" for e in r["episode"]["events"]) for r in core) if core else None,
            "mean_elapsed_seconds": mean(r["episode"]["elapsed_seconds"] for r in core) if core else None,
            "prompt_tokens": sum(r["episode"]["tokens"]["prompt_tokens"] for r in own),
            "completion_tokens": sum(r["episode"]["tokens"]["completion_tokens"] for r in own),
            "monetary_cost": None, "informational_honesty": None, "tool_discipline": None,
        }
    return output


def report_markdown(summary: dict, manifest: dict) -> str:
    def rate(value):
        return f"{100*value:.1f}%" if value is not None else "N/A"
    lines = [
        "# RUT-Science evaluation", "",
        "Source: project extension inspired by RUT-Bench; not an official reproduction.", "",
        f"Base tasks: {manifest['task_count']}; paired dialogues: {manifest['task_count']*7}; seeds: {manifest['seeds']}.", "",
        "Offline rule controllers are harness controls. Their measured differences are authored and do not establish LLM planning gains.", "",
        "| Agent | Ideal SR | Overall execution SR | Response-only success (extension) | Core scored/attempted | Service/adapter errors |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for agent, data in summary.items():
        lines.append(f"| {agent} | {rate(data['behavior_results']['ideal']['sr'])} | {rate(data['overall_execution_sr'])} | "
                     f"{rate(data['interaction_success_rate_extension'])} | {data['scored_core_runs']}/{data['core_runs']} | {data['infrastructure_errors']} |")
    lines.extend(["", "| Agent | Behavior | Successes / n | SR | Ideal minus behavior (pp) | Task-cluster 95% interval (pp) |", "|---|---|---:|---:|---:|---|"])
    for agent, data in summary.items():
        for behavior, row in data["behavior_results"].items():
            gap = row["paired_gap"]
            lines.append(f"| {agent} | {behavior} | {row['successes']}/{row['n']} | {rate(row['sr'])} | {gap['gap_pp']} | {gap['ci95_pp']} |")
    lines.extend(["", "Failure labels use R4 -> R1a/R1b -> R2 -> R3. Tool errors and termination reasons are retained separately.", "",
                  "IH/TD: not run (null). Monetary prices: not configured (null). Token counts are recorded separately.", "",
                  "Five root tasks share one environment and synthetic data generators. Bootstrap intervals are descriptive; repeated deterministic seeds add no independent evidence.", "",
                  "Unresolved conflicts/missing critical context are response-only cases and are excluded from execution SR and paired gaps.", ""])
    for agent, data in summary.items():
        lines.extend([f"{agent}: failures={data['failures']}; mean tool calls={data['mean_tool_calls']:.2f}; "
                      f"tokens in/out={data['prompt_tokens']}/{data['completion_tokens']}.", ""])
        lines.extend([f"State-only diagnostic SR (project extension): {rate(data['state_only_sr_extension'])}. "
                      "This does not replace the three-check primary metric or reproduce the upstream relaxed metric.", ""])
    return "\n".join(lines)
