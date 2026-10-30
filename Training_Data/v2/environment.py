"""Actual offline tool-call environment, fixed candidate parameters and public rewards."""
from copy import deepcopy
import uuid
from protocol import ROOT, VERSION, REWARD_VERSION, ACTION_SPECS, ACTION_IDS, FEATURE_NAMES, Library, digest, validate_task, verify_runtime


class ToolEnvironment:
    def __init__(self, task, *, run_id=None):
        validate_task(task)
        self._task = deepcopy(task)
        self.goal = deepcopy(task["public"])
        self.run_id = run_id or uuid.uuid4().hex[:10]
        self.catalog_hash = verify_runtime()

    def reset(self):
        self._reset_count = getattr(self, "_reset_count", 0)+1
        self.library = Library(ROOT/"tool_runtime"/"sessions"/(self.run_id+"_"+str(self._reset_count)))
        self.refs, self.evidence, self.history = {}, [], []
        self.steps, self.milestones = 0, set()
        self.terminated = self.truncated = False
        self.reconciled = self.workflow_checked = False
        self.last_failed = False
        self.variance_available = self.goal["sigma"] is not None
        self.unavailable = self.tool_failure = False
        project = self.library.call("project_create", {"title": "Synthetic "+self.goal["domain"]+" task", "objective": self.goal["user_request"]})["result"]["project_ref"]
        initial = self.library.call("plan_create", {"project_ref": project, "family": self.goal["family"]})["result"]["plan_ref"]
        contract = self.library.store.get(initial, "plan")["contract"]
        model = self.expected_model()
        changes = [{"path": path, "value": value} for path, value in [
            ("/question", self.goal["user_request"]), ("/factors", self.goal["factors"]),
            ("/experimental_unit/definition", self.goal["unit_definition"]), ("/response/name", self.goal["response"]),
            ("/response/direction", self.goal["direction"]), ("/response/unit", "dimensionless"),
            ("/analysis/primary_term", self.goal["primary_term"]), ("/analysis/minimum_effect", self.goal["minimum_effect"]),
            ("/analysis/sigma", self.goal["sigma"] or .02), ("/analysis/target_power", self.goal["target_power"]),
            ("/analysis/model", model), ("/resources/budget", self.goal["resource_budget"])]]
        plan = self.library.call("plan_patch", {"plan_ref": initial, "expected_contract_hash": digest(contract), "changes": changes,
            "reason": "Synthetic task initialization from declared public goal; placeholder sigma cannot authorize review when unavailable"})["result"]["plan_ref"]
        claim = self.library.call("claim_define", {"project_ref": project, "statement": self.goal["user_request"],
            "response": self.goal["response"], "primary_term": self.goal["primary_term"], "direction": self.goal["direction"],
            "practical_margin": self.goal["practical_margin"], "population_scope": "declared_dataset_and_training_protocol",
            "factor_levels": [{"factor": f["name"], "baseline": f["levels"][0], "candidate": f["levels"][1]} for f in self.goal["factors"]],
            "expected_unit_definition": self.goal["unit_definition"]})["result"]["claim_ref"]
        self.refs.update(project=project, plan=plan, claim=claim)
        fixture = self._task["simulator"]
        if fixture["initial_fault"] == "stale_review":
            self.refs["review"] = self.library.call("plan_review", {"plan_ref": plan})["result"]["review_ref"]
        fault = {"wrong_model": ("/analysis/model", "two_arm" if model != "two_arm" else "full_factorial"),
                 "wrong_response": ("/response/name", "training_loss"), "low_budget": ("/resources/budget", 2),
                 "stale_review": ("/resources/budget", self.goal["resource_budget"]+1)}.get(fixture["initial_fault"])
        if fault:
            current = self.current_plan()
            patched = self.library.call("plan_patch", {"plan_ref": plan, "expected_contract_hash": digest(current["contract"]),
                "changes": [{"path": fault[0], "value": fault[1]}], "reason": "Synthetic initial draft requiring independent review"})["result"]["plan_ref"]
            self.refs["parent"] = plan
            self.refs["plan"] = patched
        if fixture["existing_job"]:
            # Existing mock job is environment state; no future outcome label is
            # exposed. The policy still has to obtain/reconcile public references.
            self._bootstrap_existing_job()
        self._add_evidence("initial_request", {"user_request": self.goal["user_request"]})
        return self.observe(), {"real_executions": 0}

    def expected_model(self):
        return {"crd_two_arm": "two_arm", "rcbd_two_arm": "additive_blocks", "factorial_2x2": "blocked_full_factorial"}[self.goal["family"]]

    def current_plan(self):
        return self.library.store.get(self.refs["plan"], "plan")

    def _bootstrap_existing_job(self):
        review = self.library.call("plan_review", {"plan_ref": self.refs["plan"]})["result"]
        alignment = self.library.call("claim_check_plan", {"claim_ref": self.refs["claim"], "plan_ref": self.refs["plan"]})["result"]
        frozen = self.library.call("plan_freeze", {"plan_ref": self.refs["plan"], "review_ref": review["review_ref"], "alignment_ref": alignment["alignment_ref"]})["result"]
        self.library.call("job_run_mock", {"freeze_ref": frozen["freeze_ref"], "scenario": self._task["simulator"]["outcome_scenario"]})

    def _add_evidence(self, kind, value):
        row = {"id": digest([kind, value, len(self.evidence)])[:16], "kind": kind, "value": deepcopy(value), "source": "offline_tool_or_scripted_user"}
        self.evidence.append(row)
        return row["id"]

    def _review(self):
        return self.library.store.get(self.refs["review"], "review") if "review" in self.refs else None

    def _alignment(self):
        return self.library.store.get(self.refs["alignment"], "alignment") if "alignment" in self.refs else None

    def candidates(self):
        r, plan = self.refs, self.current_plan()
        c = plan["contract"]
        values = []
        for identity, tool in ACTION_SPECS:
            available = not (self.terminated or self.truncated)
            args = {}
            if identity == "review": args = {"plan_ref": r["plan"]}
            elif identity == "align_claim": args = {"claim_ref": r["claim"], "plan_ref": r["plan"]}
            elif identity == "diff":
                available &= "parent" in r
                args = {"old_plan_ref": r.get("parent"), "new_plan_ref": r["plan"]}
            elif tool == "plan_patch":
                path, value = (("/analysis/model", identity.removeprefix("model_")) if identity.startswith("model_") else
                    ("/response/name", self.goal["response"]) if identity == "repair_response" else ("/resources/budget", self.goal["resource_budget"]))
                args = {"plan_ref": r["plan"], "expected_contract_hash": digest(c), "changes": [{"path": path, "value": value}],
                        "reason": "Agent selected a bounded public candidate amendment"}
            elif identity == "resolve":
                available &= "old_review" in r and "review" in r
                args = {"old_review_ref": r.get("old_review"), "new_review_ref": r.get("review")}
            elif identity == "freeze":
                available &= "review" in r and "alignment" in r
                args = {"plan_ref": r["plan"], "review_ref": r.get("review"), "alignment_ref": r.get("alignment")}
            elif identity == "workflow":
                available &= "freeze" in r; args = {"freeze_ref": r.get("freeze")}
            elif identity == "verify_workflow":
                available &= "workflow" in r; args = {"workflow_ref": r.get("workflow")}
            elif identity in {"reconcile", "run_mock"}:
                available &= "freeze" in r
                if identity == "run_mock": available &= self.reconciled
                args = {"freeze_ref": r.get("freeze")}
                if identity == "run_mock": args["scenario"] = {"$host": "private_mock_fixture"}
            elif identity in {"poll", "analyze"}:
                available &= "job" in r; args = {"job_ref": r.get("job")}
            elif identity == "assess":
                available &= "analysis" in r; args = {"claim_ref": r["claim"], "analysis_ref": r.get("analysis")}
            elif identity in {"next", "report"}:
                available &= "assessment" in r
                args = {"assessment_ref": r.get("assessment")}
                if identity == "report":
                    available &= "workflow" in r; args["workflow_ref"] = r.get("workflow")
            elif identity == "read_plan": args = {"artifact_ref": r["plan"]}
            elif identity == "ask_variance": args = {"field": "variance_source"}
            elif identity == "stop": args = {"evidence_ids": [row["id"] for row in self.evidence if row["kind"] in {"user_unavailable", "mock_tool_failure"}]}
            values.append({"action_id": identity, "tool": tool, "arguments": args, "available": bool(available)})
        return values

    def observe(self):
        c, review, alignment = self.current_plan()["contract"], self._review(), self._alignment()
        current_review = bool(review and review["plan_ref"] == self.refs["plan"])
        current_alignment = bool(alignment and alignment["plan_ref"] == self.refs["plan"])
        flags = {"review_current": current_review, "review_passed": bool(current_review and review["validation"]["ready_for_review"]),
            "alignment_current": current_alignment, "alignment_passed": bool(current_alignment and alignment["can_test_conditionally"]),
            "workflow_checked": self.workflow_checked, "job_queried": self.reconciled,
            "variance_available": self.variance_available, "public_unavailable": self.unavailable, "public_tool_failure": self.tool_failure}
        return {"schema_version": VERSION, "goal": deepcopy(self.goal), "current_contract": c,
            "artifact_refs": dict(self.refs), "flags": flags, "evidence": deepcopy(self.evidence),
            "history": deepcopy(self.history[-4:]), "turn": self.steps, "last_call_failed": self.last_failed,
            "candidates": self.candidates(), "real_execution_allowed": False}

    def features(self, obs=None):
        obs = obs or self.observe()
        g, c, r, f = obs["goal"], obs["current_contract"], obs["artifact_refs"], obs["flags"]
        model = c["analysis"]["model"]
        vector = [g["domain"] == "cvit", g["family"] == "crd_two_arm", g["family"] == "rcbd_two_arm", g["family"] == "factorial_2x2",
            f["variance_available"], f["public_unavailable"], f["public_tool_failure"], "parent" in r,
            model == "two_arm", model == "additive_blocks", model == "full_factorial", model == "blocked_full_factorial",
            c["response"]["name"] == g["response"], min(2, c["resources"]["budget"]/g["resource_budget"]),
            "review" in r, f["review_current"], f["review_passed"], "old_review" in r and "resolution" not in r,
            f["alignment_current"], f["alignment_passed"], "freeze" in r, "workflow" in r, f["workflow_checked"], f["job_queried"],
            "job" in r, "analysis" in r, "assessment" in r, "next" in r, "report" in r,
            obs["turn"]/g["max_decisions"], obs["last_call_failed"], 1.0]
        if len(vector) != len(FEATURE_NAMES): raise ValueError("Feature protocol mismatch")
        return [float(value) for value in vector]

    def step(self, action):
        if self.terminated or self.truncated:
            raise ValueError("Episode has ended")
        before = self.observe()
        if type(action) is not int or not 0 <= action < len(ACTION_IDS):
            raise ValueError("Choose a candidate index")
        candidate = before["candidates"][action]
        self.steps += 1
        reward, result, error = -.02, {}, None
        self.last_failed = False
        identity, tool = candidate["action_id"], candidate["tool"]
        classification = "in_progress"
        try:
            if not candidate["available"]: raise ValueError("Host prerequisite unavailable")
            if identity == "ask_variance":
                if self.variance_available or self.unavailable: raise ValueError("Variance was already answered")
                answer = self._task["simulator"]["user_variance_answer"]
                if answer is None:
                    self.unavailable = True
                    result = {"status": "explicitly_unavailable", "evidence_id": self._add_evidence("user_unavailable", {"field": "variance_source", "answer": "User cannot provide a variance basis for this powered-design request"})}
                else:
                    raise ValueError("This version only demonstrates explicitly unavailable answers; provide sigma/source in the public task otherwise")
                reward += .1
            elif identity == "stop":
                ids = set(candidate["arguments"]["evidence_ids"])
                available = {row["id"] for row in before["evidence"] if row["kind"] in {"user_unavailable", "mock_tool_failure"}}
                justified = bool(ids and ids.issubset(available))
                self.terminated = True
                reward += 10 if justified else -10
                classification = "justified_stop" if justified else "unjustified_stop"
                result = {"justified": justified, "public_evidence_ids": sorted(ids)}
            else:
                if identity in {"review", "freeze"} and not self.variance_available:
                    raise ValueError("Variance source is unresolved; a template default is not scientific evidence")
                if identity == "freeze" and "old_review" in self.refs and "resolution" not in self.refs:
                    old = self.library.store.get(self.refs["old_review"], "review")
                    if old["findings"]: raise ValueError("Old review findings require a new resolution record")
                args = deepcopy(candidate["arguments"])
                if identity == "run_mock":
                    if self._task["simulator"]["job_failure"]:
                        self.tool_failure = True
                        self._add_evidence("mock_tool_failure", {"code": "mock_oom", "actual_training": False})
                        raise ValueError("Mock resource failure: no real job was launched")
                    args["scenario"] = self._task["simulator"]["outcome_scenario"]
                result = self.library.call(tool, args)["result"]
                if tool == "plan_patch":
                    old_review = self.refs.get("old_review") if "old_review" in self.refs and "resolution" not in self.refs else self.refs.get("review")
                    old_plan, claim, project = self.refs["plan"], self.refs["claim"], self.refs["project"]
                    self.refs = {"project": project, "claim": claim, "parent": old_plan, "plan": result["plan_ref"]}
                    if old_review: self.refs["old_review"] = old_review
                    self.reconciled = self.workflow_checked = False
                else:
                    ref_key = {"review": "review", "align_claim": "alignment", "resolve": "resolution", "freeze": "freeze", "workflow": "workflow",
                        "run_mock": "job", "analyze": "analysis", "assess": "assessment", "report": "report"}.get(identity)
                    if ref_key: self.refs[ref_key] = result[ref_key+"_ref"]
                    if identity == "verify_workflow": self.workflow_checked = result["passed"]
                    if identity == "reconcile":
                        self.reconciled = True
                        if result["job_ref"]: self.refs["job"] = result["job_ref"]
                    if identity == "next": self.refs["next"] = "recorded"
                self._add_evidence("tool_result", {"tool": tool, "result": result})
                milestone = None
                if identity == "review" and result["ready_for_review"]: milestone = "review_pass"
                elif identity == "align_claim" and result["can_test_conditionally"]: milestone = "alignment_pass"
                elif identity in {"freeze", "verify_workflow", "reconcile", "analyze", "assess"}: milestone = identity
                if milestone and milestone not in self.milestones:
                    self.milestones.add(milestone); reward += .2
                if identity == "report":
                    if not self.workflow_checked or not self.reconciled or "next" not in self.refs:
                        raise ValueError("Completion requires workflow verification, reconciliation and explicit next-step handling")
                    self.terminated = True; classification = "completed_mock_research_loop"; reward += 10
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            error = str(exc)[:500]; self.last_failed = True; reward -= 1
        if not self.terminated and self.steps >= self.goal["max_decisions"]:
            self.terminated = True; classification = "decision_budget_exhausted"; reward -= 2
        feedback = {"tool": tool, "result": result, "error": error, "real_execution": False}
        self.history.append({"action_id": identity, "tool": tool, "error": error, "result_keys": list(result)})
        return self.observe(), reward, self.terminated, self.truncated, {"feedback": feedback, "classification": classification,
            "success": classification in {"completed_mock_research_loop", "justified_stop"}, "reward_version": REWARD_VERSION}

    def truncate(self):
        if self.terminated: raise ValueError("Cannot truncate a terminal task")
        self.truncated = True
        return self.observe()


def reference_action(obs):
    """Transparent scripted reference uses only current public observations."""
    g, c, r, f = obs["goal"], obs["current_contract"], obs["artifact_refs"], obs["flags"]
    if f["public_unavailable"] or f["public_tool_failure"]: return ACTION_IDS.index("stop")
    if not f["variance_available"]: return ACTION_IDS.index("ask_variance")
    if c["response"]["name"] != g["response"]: return ACTION_IDS.index("repair_response")
    if c["resources"]["budget"] < len(c["run_plan"])*c["resources"]["per_run"]: return ACTION_IDS.index("repair_budget")
    if not f["review_current"]: return ACTION_IDS.index("review")
    if not f["review_passed"]:
        model = {"crd_two_arm": "two_arm", "rcbd_two_arm": "additive_blocks", "factorial_2x2": "blocked_full_factorial"}[g["family"]]
        return ACTION_IDS.index("model_"+model)
    if "old_review" in r and "resolution" not in r: return ACTION_IDS.index("resolve")
    if not f["alignment_current"] or not f["alignment_passed"]: return ACTION_IDS.index("align_claim")
    for identity, condition in (("freeze", "freeze" not in r), ("workflow", "workflow" not in r),
        ("verify_workflow", not f["workflow_checked"]), ("reconcile", not f["job_queried"]), ("run_mock", "job" not in r),
        ("analyze", "analysis" not in r), ("assess", "assessment" not in r), ("next", "next" not in r)):
        if condition: return ACTION_IDS.index(identity)
    return ACTION_IDS.index("report")
