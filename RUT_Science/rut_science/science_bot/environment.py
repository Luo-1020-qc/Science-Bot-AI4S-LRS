"""Shared scientific transition kernel for terminal, HTTP and Gym.

One authoritative business snapshot. Jobs have a durable result before state
commit; unknown outcomes suspend scheduling rather than blindly retraining.
"""
import copy
import json
from pathlib import Path
import time
import numpy as np
from .contracts import K_MAX, catalog
from .numerics import diagnose_inputs, diagnose_residuals, errors, predict, fit, array_hash
from .cache import OutcomeCache
from ..util import digest, write_json


class BudgetedEnvironment:
    def __init__(self, spec, data, *, cache=None, folder=None, state=None, candidate_ids=None):
        self.spec, self.data = spec, data
        self.cache = cache or OutcomeCache()
        self.folder = Path(folder) if folder else None
        self.state = state if state is not None else {
            "version": 0, "phase": "ready", "experiments": {}, "diagnostics": {}, "residuals": {},
            "jobs": {}, "pending_job": None, "latest_failure": None, "retries": 0,
            "cu": 0.0, "attempts": 0, "decisions": 0, "tokens": 0, "requests": 0,
            "active_seconds": 0.0, "history": [], "requests_done": {}, "report": None,
            "candidate_ids": candidate_ids or [c["id"] for c in catalog()], "finalization_tools": 0,
            "finalization_cu": 0, "evaluation_reads": 0}
        self.reconcile()

    @property
    def done(self):
        return self.state["phase"] in {"completed", "abstained", "cancelled"}

    def save(self):
        if self.folder:
            write_json(self.folder/"environment.json", {"state": self.state, "hash": digest(self.state),
                                                       "data_identity": self.data.identity})

    def reconcile(self):
        if self.state["phase"] == "finalizing":
            report_path = self.folder/"report.json" if self.folder else None
            if report_path and report_path.exists():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                if report["data_identity"] != self.data.identity:
                    raise ValueError("Final report data identity mismatch")
                self.state["report"] = report
                self.state["phase"] = "completed" if report["selected"] else "abstained"
                self.state["evaluation_reads"] = report["evaluation_reads"]
                self.state["finalization_cu"], self.state["finalization_tools"] = 2, 2
            elif self.state["evaluation_reads"]:
                self.state["phase"] = "needs_reconciliation"
            else:
                # Freeze was committed but sealed evaluation had not started.
                self.finalize("recovered_finalization", abstain=self.state.get("selected") is None)
        job_id = self.state["pending_job"]
        if not job_id:
            return
        path = self.folder/"jobs"/(job_id+".json") if self.folder else None
        if path and path.exists():
            outcome = json.loads(path.read_text(encoding="utf-8"))
            self._commit_job(job_id, outcome)
            self.state["phase"] = "ready"
        else:
            self.state["phase"] = "needs_reconciliation"
        self.save()

    def incumbent(self):
        completed = [(v["validation_mean"], k) for k, v in self.state["experiments"].items()
                     if v["status"] == "succeeded"]
        return min(completed)[1] if completed else None

    def candidates(self):
        s, spec = self.state, self.spec
        result = []
        for c in catalog():
            item = copy.deepcopy(c)
            item["legal"] = c["id"] in s["candidate_ids"] and c["id"] not in s["experiments"]
            result.append(item)
        result += [{"id": "diagnose_inputs", "kind": "diagnose_inputs", "parameters": {}, "cost": 1,
                    "legal": not s["diagnostics"]}]
        best = self.incumbent()
        result += [{"id": "diagnose_residuals", "kind": "diagnose_residuals", "parameters": {"model_id": best},
                    "cost": 1, "legal": best is not None and best not in s["residuals"]}]
        failed = s["latest_failure"]
        job = s["jobs"].get(failed, {})
        result += [{"id": "retry", "kind": "retry", "parameters": {"job_id": failed},
                    "cost": job.get("candidate", {}).get("cost", 0),
                    "legal": bool(failed and job.get("atomic") and not job.get("retried") and s["retries"] < 2)}]
        for c in result:
            c["legal"] = bool(c["legal"] and s["cu"]+c["cost"] <= spec.compute_units
                              and s["attempts"] < spec.tool_attempts and not self.done
                              and s["phase"] != "needs_reconciliation")
        result += [{"id": "submit_best", "kind": "submit_best", "parameters": {}, "cost": 0,
                    "legal": best is not None and not self.done},
                   {"id": "abstain", "kind": "abstain", "parameters": {}, "cost": 0, "legal": True}]
        assert len(result) == 18 and len({c["id"] for c in result}) == len(result)
        return result

    def observe(self, *, permutation=None):
        s = self.state
        candidates = self.candidates()
        if permutation is not None:
            if sorted(permutation) != list(range(len(candidates))):
                raise ValueError("Invalid candidate permutation")
            candidates = [candidates[i] for i in permutation]
        experiments = []
        for c in catalog():
            e = s["experiments"].get(c["id"])
            experiments.append({"candidate_ref": c["id"], "kind": c["kind"], "parameters": c["parameters"],
                                "status": e["status"] if e else "untried",
                                "observed": bool(e and e["status"] == "succeeded"),
                                "validation_mean": e.get("validation_mean") if e else None,
                                "validation_std": e.get("validation_std") if e else None,
                                "attempts": e.get("attempts", 0) if e else 0})
        # Explicit allowlist: no raw arrays, private seeds, paths, cache tables or sealed results.
        return {"schema_version": "planner_observation_v1", "observation_ref": f"obs_{s['version']:06d}",
                "goal": {"metric": "mean_relative_l2", "unit": "dimensionless", "quality_threshold": self.spec.quality_threshold},
                "dataset_public": self.data.public(), "phase": s["phase"],
                "budget": {"compute_units_remaining": self.spec.compute_units-s["cu"],
                           "compute_units_limit": self.spec.compute_units,
                           "tool_attempts_remaining": self.spec.tool_attempts-s["attempts"],
                           "decision_steps_remaining": self.spec.decision_steps-s["decisions"],
                           "llm_tokens_remaining": self.spec.llm_tokens-s["tokens"],
                           "llm_requests_remaining": self.spec.llm_requests-s["requests"],
                           "active_seconds_remaining": max(0, self.spec.active_seconds-s["active_seconds"]),
                           "finalization_reserved_cu": 2, "finalization_reserved_tools": 2},
                "diagnostics": copy.deepcopy(s["diagnostics"]), "residuals": copy.deepcopy(s["residuals"]),
                "failures": [{"candidate_ref": j["candidate"]["id"], "attempt": j["attempt"],
                              "error": j.get("error", "fixture_pre_call_unavailable"), "atomic": j.get("atomic", False),
                              "fixture": j.get("fixture", False)} for j in s["jobs"].values() if j["status"] == "failed"],
                "experiments": experiments, "incumbent": self.incumbent(),
                "history": copy.deepcopy(s["history"][-16:]), "candidates": candidates,
                "mask": [c["legal"] for c in candidates] + [False]*(K_MAX-len(candidates))}

    def cost(self):
        s, p = self.state, self.spec
        return (0.70*(s["cu"]+s["finalization_cu"])/(p.compute_units+2)
                + 0.15*(s["attempts"]+s["finalization_tools"])/(p.tool_attempts+2)
                + 0.15*s["tokens"]/p.llm_tokens)

    def step_action(self, action_id, observation_ref, idempotency_key):
        s = self.state
        request_hash = digest([action_id, observation_ref])
        if idempotency_key in s["requests_done"]:
            old = s["requests_done"][idempotency_key]
            if old["request_hash"] != request_hash:
                raise ValueError("Idempotency key reused with different request")
            return old["result"]
        if self.done or s["phase"] == "needs_reconciliation":
            raise ValueError("Session is terminal or requires job reconciliation")
        if observation_ref != self.observe()["observation_ref"]:
            raise ValueError("Stale observation")
        choices = {c["id"]: c for c in self.candidates() if c["legal"]}
        if action_id not in choices:
            raise ValueError("Illegal action")
        started, before, cu_before = time.perf_counter(), self.cost(), s["cu"]
        c = choices[action_id]
        s["decisions"] += 1
        if c["kind"] in {"submit_best", "abstain"}:
            self.finalize("explicit_submit" if action_id == "submit_best" else "explicit_abstain",
                          abstain=action_id == "abstain")
        elif c["kind"] == "diagnose_inputs":
            s["cu"] += 1; s["attempts"] += 1
            s["diagnostics"] = diagnose_inputs(self.data)
        elif c["kind"] == "diagnose_residuals":
            s["cu"] += 1; s["attempts"] += 1
            model_id = c["parameters"]["model_id"]
            s["residuals"][model_id] = diagnose_residuals(self.data, s["experiments"][model_id]["model"])
        else:
            self._fit_action(c, idempotency_key)
        s["active_seconds"] += time.perf_counter()-started
        if s["report"]:
            s["report"]["resources"]["active_seconds"] = s["active_seconds"]
        s["version"] += 1
        s["history"].append({"action_id": action_id, "kind": c["kind"], "cost_cu": s["cu"]-cu_before,
                             "quoted_cost_cu": c["cost"],
                             "incumbent": self.incumbent(), "version": s["version"]})
        if not self.done and (s["decisions"] >= self.spec.decision_steps or s["active_seconds"] >= self.spec.active_seconds
                              or s["requests"] >= self.spec.llm_requests or s["tokens"] >= self.spec.llm_tokens):
            self.finalize("host_finalize_due_to_budget")
        reward = -0.05*(self.cost()-before)
        if self.done:
            reward += float(bool(s["report"].get("scientific_success")))
        result = {"reward": reward, "terminated": self.done, "truncated": False,
                  "observation_ref": self.observe()["observation_ref"], "action_id": action_id}
        s["requests_done"][idempotency_key] = {"request_hash": request_hash, "result": result}
        self.save()
        return result

    def _fit_action(self, action, key):
        s = self.state
        if action["kind"] == "retry":
            previous = s["jobs"][action["parameters"]["job_id"]]
            previous["retried"] = True
            c = previous["candidate"]
            s["retries"] += 1
        else:
            c = action
        job_id = digest([self.data.identity, key])[:24]
        old_attempts = s["experiments"].get(c["id"], {}).get("attempts", 0)
        s["attempts"] += 1
        s["jobs"][job_id] = {"candidate": {k: v for k, v in c.items() if k != "legal"},
                              "status": "reserved", "reserved_cu": c["cost"], "attempt": old_attempts+1,
                              "retried": action["kind"] == "retry"}
        s["pending_job"] = job_id
        self.save()
        stream = int(digest([self.data.identity, c["id"], old_attempts])[:12], 16)/16**12
        if stream < self.spec.fault_rate:
            outcome = {"status": "failed", "atomic": True, "fixture": True,
                       "error": "fixture_pre_call_unavailable", "used_cu": 0.25}
        else:
            result, metadata = self.cache.get(self.data, c)
            outcome = {"status": "succeeded", "atomic": False, "used_cu": c["cost"],
                       "result": result, "metadata": metadata}
        if self.folder:
            write_json(self.folder/"jobs"/(job_id+".json"), outcome)
        self._commit_job(job_id, outcome)

    def _commit_job(self, job_id, outcome):
        s = self.state
        job = s["jobs"][job_id]
        if job["status"] in {"succeeded", "failed"}:
            s["pending_job"] = None
            return
        s["cu"] += outcome["used_cu"]
        job.update(status=outcome["status"], atomic=outcome["atomic"], reserved_cu=0,
                   outcome_hash=digest(outcome), fixture=outcome.get("fixture", False), error=outcome.get("error"))
        c = job["candidate"]
        s["experiments"][c["id"]] = {"status": outcome["status"], "attempts": job["attempt"],
                                       **outcome.get("result", {})}
        if outcome["status"] == "failed":
            s["latest_failure"] = job_id
        elif s["latest_failure"] and s["jobs"][s["latest_failure"]]["candidate"]["id"] == c["id"]:
            s["latest_failure"] = None
        s["pending_job"] = None

    def finalize(self, reason, abstain=False):
        s = self.state
        if s["report"] is not None:
            return s["report"]
        selected = None if abstain else self.incumbent()
        s["phase"] = "finalizing"
        s["selected"] = selected
        self.save()  # freeze before any sealed evaluation
        report = {"schema_version": "budgeted_report_v1", "termination": reason, "selected": selected,
                  "complete": False, "valid": False, "quality_pass": False, "scientific_success": False,
                  "sealed_error": None, "threshold": self.spec.quality_threshold,
                  "data_identity": self.data.identity, "provenance": self.data.provenance,
                  "strict_execution": not any(j["status"] == "failed" for j in s["jobs"].values()),
                  "retries": s["retries"], "fixture_faults": self.spec.fault_rate > 0}
        if selected:
            c = next(c for c in catalog() if c["id"] == selected)
            independent = fit(self.data, c)
            actual = s["experiments"][selected]
            val = predict(independent, self.data.val_x)
            valid = (array_hash(val) == actual["prediction_hash"]
                     and digest(independent) == digest(actual["model"]))
            s["evaluation_reads"] += 1
            self.save()  # never silently read sealed evaluation twice after a crash
            e = errors(predict(independent, self.data.sealed_x), self.data.sealed_y)
            error = float(e.mean())
            report.update(complete=True, valid=valid, quality_pass=error <= self.spec.quality_threshold,
                          scientific_success=bool(valid and error <= self.spec.quality_threshold),
                          sealed_error=error, search_validation_error=actual["validation_mean"],
                          model_hash=digest(independent))
        s["finalization_tools"], s["finalization_cu"] = 2, 2
        s["phase"] = "completed" if selected else "abstained"
        report["resources"] = {"search_cu": s["cu"], "finalization_cu": 2, "tool_attempts": s["attempts"],
                               "finalization_tools": 2, "decisions": s["decisions"], "llm_requests": s["requests"],
                               "llm_tokens": s["tokens"], "active_seconds": s["active_seconds"]}
        report["evaluation_reads"] = s["evaluation_reads"]
        s["report"] = report
        if self.folder:
            write_json(self.folder/"report.json", report)
            (self.folder/"report.md").write_text(
                f"# science Bot research report\n\nSelected: {selected}\n\nScientific success: {report['scientific_success']}\n\n"
                f"Sealed mean relative L2: {report['sealed_error']}\n\nEngineering threshold: {self.spec.quality_threshold}\n\n"
                f"Scope: {self.data.provenance['source']}\n\nFull provenance and resource ledger: report.json\n", encoding="utf-8")
        self.save()
        return report
