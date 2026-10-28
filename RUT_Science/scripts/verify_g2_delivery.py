"""Reproducible G2 fixtures, bounded acceptance and numerical audit.

Default: no online calls. --live performs one cached native-tool acceptance;
only explicitly generated public fixtures are sent to the configured model.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np
from scipy import stats
from rich.console import Console

from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.experiment import ExperimentSpec
from rut_science.science_bot.session import ScienceSession
from rut_science.util import write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"delivery/g2_update"
EXAMPLES = ROOT/"examples/g2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixtures():
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261022)
    groups = [[f"u{i}", "A" if i < 12 else "B", float(y)] for i, y in
              enumerate(np.concatenate([rng.normal(10, 2, 12), rng.normal(12, 3, 15)]))]
    pairs = [[f"p{i}", level, float(value)] for i in range(16)
             for level, value in zip(["before", "after"], [10+i/5+rng.normal(), 12+i/5+rng.normal()])]
    # Shuffle rows to exercise actual key matching, rather than positional pairing.
    rng.shuffle(pairs)
    prediction = []
    for i in range(100):
        x1, x2 = rng.normal(size=2)
        prediction.append([f"r{i}", float(x1), float(x2), float(2+3*x1-.7*x2+rng.normal(0, .3))])
    for name, columns, rows in (("two_groups.csv", ["id", "group", "y"], groups),
                                 ("paired_measurements.csv", ["id", "condition", "y"], pairs),
                                 ("prediction.csv", ["id", "x1", "x2", "y"], prediction)):
        path = EXAMPLES/name
        if not path.exists():
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(columns)
                writer.writerows(rows)
    common = {"response": "y", "unit": "id", "provenance": "synthetic",
              "sampling_note": "全部现有合成样本，仅作探索性演示；未进行事先功效计算"}
    specs = {
        "independent": ExperimentSpec(**common, data_path="two_groups.csv", research_question="合成数据中A与B组的平均响应是否不同？",
                                      design="independent", factor="group", levels=["A", "B"]),
        "paired": ExperimentSpec(**common, data_path="paired_measurements.csv", research_question="同一合成单位before与after的平均差是否为零？",
                                 design="paired", factor="condition", levels=["before", "after"]),
        "prediction": ExperimentSpec(**common, data_path="prediction.csv", research_question="在未见合成单位上比较均值基线与OLS预测y的误差。",
                                     design="prediction", features=["x1", "x2"]),
    }
    for name, spec in specs.items():
        path = EXAMPLES/f"{name}_design.json"
        if not path.exists():
            write_json(path, spec.to_dict())
    return {name: ExperimentSpec.from_dict(json.loads((EXAMPLES/f"{name}_design.json").read_text(encoding="utf-8"))) for name in specs}


def audit(experiment):
    spec = experiment.spec
    with (experiment.folder/"input.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    report = experiment.report()
    metrics = report["metrics"]
    if spec.design == "prediction":
        split = experiment.result("partition")
        x = np.asarray([[float(row[key]) for key in spec.features] for row in rows])
        y = np.asarray([float(row[spec.response]) for row in rows])
        train = split["train"]
        # Independent reconstruction in original units, without reusing the
        # executor's standardized coefficients or prediction function.
        matrix = np.column_stack([np.ones(len(train)), x[train]])
        coefficients = np.linalg.solve(matrix.T @ matrix, matrix.T @ y[train])
        predictions = lambda ids: np.column_stack([np.ones(len(ids)), x[ids]]) @ coefficients
        val = split["validation"]
        val_losses = {"mean": float(np.mean((y[train].mean()-y[val])**2)), "ols": float(np.mean((predictions(val)-y[val])**2))}
        winner = "mean" if val_losses["mean"] <= val_losses["ols"] else "ols"
        test = split["test"]
        predicted = np.full(len(test), y[train].mean()) if winner == "mean" else predictions(test)
        mse = float(np.mean((predicted-y[test])**2))
        return {"metric_recomputes": bool(np.isclose(mse, metrics["test_mse"], rtol=1e-10, atol=1e-12)),
                "selection_recomputes": winner == metrics["selected"],
                "disjoint_partitions": not bool(set(train)&set(val) or set(train)&set(test) or set(val)&set(test)),
                "test_evaluations": metrics["test_evaluations"], "test_mse": mse, "winner": winner}
    if spec.design == "paired":
        units = {}
        for row in rows:
            units.setdefault(row[spec.unit], {})[row[spec.factor]] = float(row[spec.response])
        difference = np.asarray([unit[spec.levels[0]]-unit[spec.levels[1]] for unit in units.values()])
        estimate, se, df = float(difference.mean()), float(difference.std(ddof=1)/np.sqrt(len(difference))), len(difference)-1
    else:
        left, right = [np.asarray([float(row[spec.response]) for row in rows if row[spec.factor] == level]) for level in spec.levels]
        estimate = float(left.mean()-right.mean())
        a, b = float(left.var(ddof=1)/len(left)), float(right.var(ddof=1)/len(right))
        se = (a+b)**.5
        df = (a+b)**2/(a*a/(len(left)-1)+b*b/(len(right)-1))
    p = float(2*stats.t.sf(abs(estimate/se), df))
    interval = [estimate-float(stats.t.ppf(1-spec.alpha/2, df))*se, estimate+float(stats.t.ppf(1-spec.alpha/2, df))*se]
    return {"metric_recomputes": bool(np.isclose(p, metrics["p_value"], rtol=1e-11)
                                      and np.allclose(interval, metrics["confidence_interval"], rtol=1e-11)),
            "p_value": p, "mean_difference": estimate}


def offline_acceptance(specs):
    saved = OUT/"offline_verification.json"
    if saved.exists():
        result = json.loads(saved.read_text(encoding="utf-8"))
        for value in result["cases"].values():
            session = ScienceSession.restore(value["session"], workspace=EXAMPLES)
            assert audit(session.tabular)["metric_recomputes"]
        return result
    cases = {}
    for name, spec in specs.items():
        session = GeneralSession.create(OUT/"offline_sessions", backend="offline", workspace=EXAMPLES)
        fresh = session.env is None and session.tabular is None
        draft = session.message("/design "+json.dumps(spec.to_dict(), ensure_ascii=False))
        assert draft.get("requires_confirmation"), draft
        session.confirm(draft["draft_hash"])
        session.run(max_steps=1)
        paused = session.meta["phase"] == "paused"
        code = ("import sys; from rut_science.science_bot.session import ScienceSession; "
                "s=ScienceSession.restore(sys.argv[1]); s.run(); print(s.meta['phase'])")
        process = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(session.folder)],
                                 capture_output=True, text=True, encoding="utf-8", timeout=50, check=True)
        assert process.stdout.strip() == "complete", process.stdout
        restored = ScienceSession.restore(session.folder)
        before = restored.resources()
        restored.run()
        cases[name] = {"session": str(session.folder), "fresh_no_environment": fresh,
                       "paused_then_new_process_completed": paused, **audit(restored.tabular),
                       "completed_run_did_not_spend_again": before == restored.resources(),
                       "model_requests": restored.resources()["llm_requests"], "tool_attempts": before["tool_attempts"]}
        assert cases[name]["metric_recomputes"]
    result = {"cases": cases, "new_online_calls": 0}
    write_json(saved, result)
    return result


def live_acceptance():
    saved = OUT/"live_verification.json"
    if saved.exists():
        return json.loads(saved.read_text(encoding="utf-8"))
    # Persist the session reference before making calls, so an interrupted paid
    # request is inspected rather than silently replaced with a new session.
    pending = OUT/"live_session.json"
    if pending.exists():
        if not (OUT/"live_initial_failure_review.json").exists():
            raise ValueError("已存在未完成在线会话，请检查其模型历史；脚本不会自动重发")
        pending = OUT/"live_retry_session.json"
        if pending.exists():
            raise ValueError("已存在复核后的在线会话，请检查历史；不会再次自动重发")
    session = GeneralSession.create(OUT/"live_sessions", backend="api", workspace=EXAMPLES,
                                    limits={"llm_requests": 4, "llm_tokens": 20000})
    write_json(pending, {"session": str(session.folder)})
    prompt = ("请为 two_groups.csv 设计独立两组 Welch 比较。研究问题：A组与B组平均y是否不同。"
              "response=y，unit=id，factor=group，levels=[A,B]，数据来源为合成 synthetic。"
              "sampling_note=全部现有合成样本，仅作探索性演示；未进行事先功效计算。alpha=0.05，seed=42。")
    result = session.message(prompt)
    assert result.get("requires_confirmation"), result
    assert session.tabular.meta["completed"] == {}
    session.confirm(result["draft_hash"])
    session.run()
    proof = audit(session.tabular)
    assert proof["metric_recomputes"]
    before = session.resources()
    session.model_output("list"); session.model_output("1"); session.research_report()
    wire = json.loads((session.folder/"turns/0001_messages.json").read_text(encoding="utf-8"))
    proposed = [call["id"] for message in wire for call in message.get("tool_calls", [])]
    returned = [message["tool_call_id"] for message in wire if message["role"] == "tool"]
    result = {"session": str(session.folder), "prompt": prompt, **proof, "native_call_ids_match": proposed == returned,
              "native_tools": [call["function"]["name"] for message in wire for call in message.get("tool_calls", [])],
              "resources": session.resources(), "replay_cost_unchanged": before == session.resources(),
              "all_outputs_accepted": all(call["status"] == "accepted" for call in session.model_output("list")["calls"])}
    prior = OUT/"live_initial_failure_review.json"
    if prior.exists():
        failed = json.loads(prior.read_text(encoding="utf-8"))
        result["initial_failure"] = failed
        result["total_new_api_requests"] = failed["resources"]["llm_requests"]+session.resources()["llm_requests"]
        result["total_new_api_tokens"] = failed["resources"]["llm_tokens"]+session.resources()["llm_tokens"]
    write_json(saved, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures-only", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    specs = fixtures()
    if args.fixtures_only:
        print(EXAMPLES)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    offline = offline_acceptance(specs)
    live = live_acceptance() if args.live else (json.loads((OUT/"live_verification.json").read_text(encoding="utf-8")) if (OUT/"live_verification.json").exists() else None)
    log = (OUT/"tests.log").read_text(encoding="utf-8") if (OUT/"tests.log").exists() else ""
    match = re.search(r"Ran (\d+) tests", log)
    source_hashes = {}
    sources = list((ROOT/"rut_science/science_bot/general").rglob("*.py")) + [
        ROOT/"rut_science/science_bot/terminal.py", ROOT/"rut_science/science_bot/model_output.py", Path(__file__),
        ROOT/"tests/test_tabular_g2.py", ROOT/"tests/test_tabular_native_http.py", ROOT/"tests/test_general_tools.py"]
    sources += list((ROOT/"docs").glob("Science_Bot_G2*"))
    sources += [ROOT.parent/"science-bot.cmd", ROOT.parent/"Start-ScienceBot.ps1", ROOT.parent/"README.md",
                ROOT.parent/"science_Bot_交接.md", OUT/"README_本轮交付.md"]
    sources += list(EXAMPLES.glob("*.json")) + list(EXAMPLES.glob("*.csv")) + [EXAMPLES/"README.md"]
    for path in sources:
        relative = path.relative_to(ROOT.parent)
        target = OUT/"source_snapshot"/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        source_hashes[relative.as_posix()] = sha(path)
    checks = {"full_regression": bool(match and "\nOK" in log and "FAILED" not in log),
              "offline_three_designs_recompute": all(value["metric_recomputes"] for value in offline["cases"].values()),
              "cross_process_restore": all(value["paused_then_new_process_completed"] for value in offline["cases"].values()),
              "repeated_run_no_extra_cost": all(value["completed_run_did_not_spend_again"] for value in offline["cases"].values()),
              "prediction_split_isolation": offline["cases"]["prediction"]["disjoint_partitions"],
              "prediction_test_committed_once": offline["cases"]["prediction"]["test_evaluations"] == 1,
              "entry_preserved": (ROOT.parent/"science-bot.cmd").exists(), "no_new_zip": not list(OUT.rglob("*.zip"))}
    initial = json.loads((ROOT/"delivery/g1_update/verification.json").read_text(encoding="utf-8"))
    checks["entry_identical_to_g1"] = all(sha(ROOT.parent/name) == initial["source_hashes"][name]
                                         for name in ("science-bot.cmd", "Start-ScienceBot.ps1"))
    terminal_file = OUT/"terminal_acceptance.json"
    if terminal_file.exists():
        terminal = json.loads(terminal_file.read_text(encoding="utf-8"))
        session = ScienceSession.restore(terminal["session"], workspace=EXAMPLES)
        history = (session.folder/"terminal.history").read_text(encoding="utf-8")
        checks["real_terminal_commands_saved"] = all(command in history for command in terminal["inputs"])
        checks["real_terminal_result_recomputes"] = audit(session.tabular)["metric_recomputes"]
        checks["real_terminal_no_online_calls"] = session.resources()["llm_requests"] == 0
        from rut_science.science_bot.terminal import show_status, show_model_output
        output = io.StringIO()
        console = Console(file=output, width=100, color_system=None)
        console.print("Saved terminal session display replay; not raw PTY footage.")
        show_status(console, session)
        console.print_json(data=session.research_report()["metrics"])
        show_model_output(console, session, "list")
        (OUT/"terminal_replay.txt").write_text(output.getvalue(), encoding="utf-8")
    else:
        checks["real_terminal_commands_saved"] = False
    if live:
        checks.update(live_native_tool_chain=live["native_call_ids_match"], live_metric_recomputes=live["metric_recomputes"],
                      live_outputs_accepted=live["all_outputs_accepted"], live_replay_no_cost=live["replay_cost_unchanged"])
    from rut_science.configuration import load_api_config
    credential = load_api_config()["api_key"].encode("utf-8")
    checks["credential_absent_in_delivery"] = all(credential not in path.read_bytes() for path in OUT.rglob("*")
        if path.is_file() and path.suffix.casefold() in {".json", ".jsonl", ".txt", ".log", ".md", ".py"})
    result = {"schema_version": "g2_delivery_verification_v1", "date": "2026-10-22", "passed": all(checks.values()),
              "checks": checks, "tests": int(match[1]) if match else None, "offline": offline, "live": live,
              "source_hashes": source_hashes, "rl_retrained": False,
              "limitations": ["Only independent/paired two-group means and IID mean/OLS prediction",
                              "Provenance and independence are user declarations, not verified scientific facts",
                              "One live synthetic task is not a broad generalization benchmark"]}
    write_json(OUT/"verification.json", result)
    print(json.dumps({"passed": result["passed"], "checks": checks, "tests": result["tests"],
                      "live_requests": live.get("total_new_api_requests", live["resources"]["llm_requests"]) if live else 0}, ensure_ascii=False))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
