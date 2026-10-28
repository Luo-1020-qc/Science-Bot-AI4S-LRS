"""Real product acceptance, cross-process restore, HTTP and small live LLM comparison.

Does not invent passes: each check retains the underlying session or exception.
Run after the frozen evaluation has registered models/planner/selected.
"""
import argparse
from dataclasses import replace
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen
import torch
from rut_science.science_bot.contracts import BudgetedResearchSpec, catalog
from rut_science.science_bot.session import ScienceSession, ROOT, MODELS
from rut_science.science_bot.api import make_server
from rut_science.science_bot.terminal import banner, show_status, show_experiments
from rut_science.util import write_json, digest
from rut_science.darcy_workflow import file_hash


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Use real configured fixed LLM with bounded per-session budgets")
    parser.add_argument("--reuse-sessions", action="store_true", help="Reuse matching completed evidence after a packaging interruption; do not repeat model calls")
    args = parser.parse_args()
    torch.set_num_threads(1)
    delivery = ROOT/"delivery"
    base = ROOT/"outputs"/"science_bot_release"
    checks, sessions, live_pairs = {}, {}, []
    existing = [ScienceSession.restore(p.parent) for p in base.glob("*/session.json")] if args.reuse_sessions else []

    def run(name, spec, backend="offline", planner="rl", intake=False):
        session = next((s for s in existing if s.spec.to_dict() == spec.to_dict()
                        and s.meta["backend"] == backend and s.meta["planner"] == planner
                        and bool(s.meta["messages"]) == intake and s.env.done), None)
        reused = session is not None
        session = session or ScienceSession.create(base, backend=backend, planner=planner, spec=spec)
        sessions[name] = str(session.folder)
        try:
            if intake and not reused:
                session.message("Darcy pressure_field" if spec.dataset == "darcy" else "generated regression_output")
            if not reused:
                session.confirm(session.confirmation)
                session.run()
            report = session.env.state["report"]
            checks[name] = {"passed": bool(report and report["valid"] and
                                           (backend != "api" or (session.folder/"explanation.json").exists())), "session": str(session.folder),
                            "scientific_success": bool(report and report["scientific_success"]),
                            "explanation": (session.folder/"explanation.json").exists(), "reused_evidence": reused}
        except Exception as exc:
            checks[name] = {"passed": False, "error_type": type(exc).__name__, "detail": str(exc)[:160],
                            "session": str(session.folder)}
        return session

    offline = run("cold_generated_rl", BudgetedResearchSpec(split="demo"))
    run("cold_darcy_rl", BudgetedResearchSpec(dataset="darcy", split="demo"))
    for group in range(8):
        fixture = run(f"fixture_{group}", BudgetedResearchSpec(split="demo", group=group, fault_rate=0.5))
        if any(j.get("fixture") for j in fixture.env.state["jobs"].values()):
            checks["fixture_fault_observed"] = {"passed": True, "session": str(fixture.folder), "fixture": True}
            break
    paused = ScienceSession.create(base, backend="offline", planner="rl", spec=BudgetedResearchSpec(split="demo"))
    paused.confirm(paused.confirmation); paused.run(max_steps=1)
    attempts_before = paused.env.state["attempts"]
    process = subprocess.run([sys.executable, "-m", "rut_science", "science", "--demo", "--resume", str(paused.folder)],
                             cwd=ROOT, capture_output=True, timeout=120)
    (delivery/"resume_process.log").write_bytes(process.stdout+process.stderr)
    restored = ScienceSession.restore(paused.folder)
    checks["cross_process_restore"] = {"passed": process.returncode == 0 and restored.env.done,
                                        "attempts_at_pause": attempts_before, "session": str(paused.folder)}
    # Same idempotent action returns original result after cross-process restore.
    first_key, first = next(iter(restored.env.state["requests_done"].items()))
    action = first["result"]["action_id"]
    before = restored.env.state["attempts"]
    restored.env.step_action(action, "obs_000000", first_key)
    checks["idempotent_restore"] = {"passed": before == restored.env.state["attempts"]}
    sessions["cross_process_restore"] = str(paused.folder)

    server = make_server(base/"http", port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    origin = f"http://127.0.0.1:{server.server_port}/v1/sessions"
    def http(path="", body=None, key=None):
        headers = {"Authorization": "Bearer "+server.service.token, "Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        data = json.dumps(body).encode() if body is not None else None
        with urlopen(Request(origin+path, data=data, headers=headers), timeout=5) as response:
            return json.load(response)
    try:
        created = http(body={"backend": "offline", "planner": "rl", "spec": {"split": "demo"}}, key="create")
        sid = created["id"]
        http(f"/{sid}/confirm", {"draft_hash": created["draft_hash"]}, "confirm")
        http(f"/{sid}/resume", {}, "resume")
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            status = http(f"/{sid}")
            if status["report_available"]:
                break
            time.sleep(0.1)
        report = http(f"/{sid}/report")
        checks["http_cli_equivalence"] = {"passed": report["selected"] == offline.env.state["report"]["selected"]
            and report["sealed_error"] == offline.env.state["report"]["sealed_error"]
            and report["resources"]["search_cu"] == offline.env.state["report"]["resources"]["search_cu"]}
        sessions["http"] = str(base/"http"/sid)
    finally:
        server.shutdown(); server.server_close(); worker.join()

    if args.live:
        run("live_generated_llm_rl", BudgetedResearchSpec(split="demo"), backend="api", intake=True)
        run("live_darcy_llm_rl", BudgetedResearchSpec(dataset="darcy", split="demo"), backend="api", intake=True)
        # Standard confirmed spec isolates selector contribution; all use full catalog.
        for group in (0, 1):
            spec = BudgetedResearchSpec(split="demo", group=group, compute_units=6, llm_requests=12, llm_tokens=100000)
            for planner in ("llm", "rl", "bc", "adaptive"):
                name = f"live_pair_{group}_{planner}"
                session = run(name, spec, backend="api", planner=planner)
                report = session.env.state["report"]
                live_pairs.append({"root": group, "planner": planner, "report": report,
                                   "error": session.meta.get("error"), "session": str(session.folder)})
        write_json(delivery/"evaluation"/"live_selector_pilot.json", {"rows": live_pairs,
                    "scope": "two_demo_roots_only_not_statistical_evidence", "candidate_mode": "full_registered_catalog",
                    "budget_scope": "same_scientific_and_total_resource_limits_actual_usage_reported"})

    from rich.console import Console
    console = Console(record=True, width=110, force_terminal=True, color_system="truecolor")
    banner(console, offline); show_status(console, offline); show_experiments(console, offline)
    (delivery/"science_bot_terminal.svg").write_text(console.export_svg(title="science Bot", clear=False), encoding="utf-8")
    console.save_text(str(delivery/"science_bot_terminal.txt"))

    # Copy auditable evidence without credentials or local service tokens.
    for name, source in sessions.items():
        destination = delivery/"demo_sessions"/name
        shutil.copytree(source, destination, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".local_token", "*.lock", "terminal.history"))
    for name, source in (("policy_checkpoint", MODELS/"selected"), ("prompts", ROOT/"prompts")):
        shutil.copytree(source, delivery/name, dirs_exist_ok=True)
    checkpoint_manifests = {p.parent.name: json.loads(p.read_text(encoding="utf-8"))
                           for p in MODELS.glob("*/manifest.json")}
    write_json(delivery/"training"/"all_checkpoints.json", checkpoint_manifests)
    for path in MODELS.glob("*/learning_curve.json"):
        target = delivery/"training"/path.parent.name
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target/path.name)
    manifest = json.loads((delivery/"evaluation"/"benchmark_manifest.json").read_text(encoding="utf-8"))
    write_json(delivery/"benchmark_manifest"/"splits.json", manifest)
    write_json(delivery/"benchmark_manifest"/"catalog.json", catalog())
    tests_log = (delivery/"tests.log").read_text(encoding="utf-8", errors="replace")
    tests_ok = "\nOK" in tests_log and "FAILED (" not in tests_log
    test_count = re.search(r"Ran (\d+) tests", tests_log)
    checks["regression_tests"] = {"passed": tests_ok, "log": "tests.log",
                                  "count": int(test_count[1]) if test_count else None}
    audit = json.loads((delivery/"evaluation"/"environment_audit.json").read_text(encoding="utf-8"))
    checks["environment_admission"] = {"passed": audit["admitted"]}
    product_required = ["cold_generated_rl", "cold_darcy_rl", "cross_process_restore", "idempotent_restore",
                        "http_cli_equivalence", "regression_tests", "environment_admission"]
    if args.live:
        product_required += ["live_generated_llm_rl", "live_darcy_llm_rl"]
    product_passed = all(checks.get(name, {}).get("passed", False) for name in product_required)
    write_json(delivery/"verification.json", {"product_checks_passed": product_passed,
        "real_api_checked": args.live, "checks": checks, "checkpoints": list(checkpoint_manifests),
        "research_scope": "controlled_generated_pilot_plus_historically_exposed_darcy_transfer",
        "research_gain_claim": "consult paired intervals; no automatic superiority claim",
        "limitations": ["Only 8 held-out mechanism groups; no cross-domain scientific generalization",
                        "Ablation retraining has one seed each; main PPO variants have five seeds",
                        "Live selector comparison has two demo roots; not a powered statistical study",
                        "No real service-failure recovery claim; injected faults explicitly marked fixture",
                        "No Elasticity backend or unrestricted coding agent; outside v1 scope"],
        "source_hashes": {str(p.relative_to(ROOT)): file_hash(p) for p in (ROOT/"rut_science"/"science_bot").glob("*.py")}})
    print(json.dumps({"product_checks_passed": product_passed, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if product_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
