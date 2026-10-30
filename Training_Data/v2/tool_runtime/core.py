"""Versioned artifacts, bounded local tools, independent review and synthetic evidence."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REF = re.compile(r"[a-f0-9]{64}")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def strict(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value
    def invalid(_):
        raise ValueError("Nonfinite JSON")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def adapter(action, **payload):
    process = subprocess.run([sys.executable, "-I", "-B", str(ROOT/"doe_adapter.py")],
        input=canonical({"action": action, **payload}), capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
        timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    value = strict(process.stdout)
    if process.returncode or not value.get("ok"):
        raise ValueError(value.get("error", "DOE adapter failed"))
    return value["result"]


class Store:
    def __init__(self, folder):
        self.folder = Path(folder).absolute()
        if not self.folder.is_relative_to(ROOT) or self.folder == ROOT or self.folder.resolve() != self.folder:
            raise ValueError("Tool sandbox must be a non-redirected child of Research_Tool_Library")
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder/"objects").mkdir(exist_ok=True)

    def put(self, kind, data):
        body = {"kind": kind, "data": data}
        identity = digest(body)
        target = self.folder/"objects"/(identity[:24]+".json")
        if target.resolve() != target:
            raise ValueError("Redirected artifact")
        if target.exists():
            self.get(identity)
        else:
            target.write_text(json.dumps({"ref": identity, **body}, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        return identity

    def get(self, identity, kind=None):
        if type(identity) is not str or not REF.fullmatch(identity):
            raise ValueError("Invalid artifact reference")
        path = self.folder/"objects"/(identity[:24]+".json")
        if path.resolve() != path or path.stat().st_size > 2*1024*1024:
            raise ValueError("Artifact redirected or oversized")
        value = strict(path.read_text(encoding="utf-8"))
        if value["ref"] != identity or digest({"kind": value["kind"], "data": value["data"]}) != identity:
            raise ValueError("Artifact content changed")
        if kind and value["kind"] != kind:
            raise ValueError("Artifact type mismatch: expected "+kind)
        return deepcopy(value["data"])

    def log(self, tool, arguments, result):
        path = self.folder/"calls.jsonl"
        if path.resolve() != path:
            raise ValueError("Redirected event log")
        previous = strict(path.read_text(encoding="utf-8").splitlines()[-1])["event_hash"] if path.exists() else None
        record = {"tool": tool, "arguments": arguments, "result": result, "previous_hash": previous}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(canonical({**record, "event_hash": digest(record)})+"\n")


def patch_value(value, path, replacement):
    parts = path.strip("/").split("/")
    current = value
    for key in parts[:-1]:
        if type(current) is list:
            current = current[int(key)]
        else:
            current = current[key]
    if type(current) is list:
        current[int(parts[-1])] = deepcopy(replacement)
    elif parts[-1] in current:
        current[parts[-1]] = deepcopy(replacement)
    else:
        raise ValueError("Patch only replaces existing fields")


class Library:
    def __init__(self, folder):
        self.store = Store(folder)

    def call(self, name, arguments):
        from catalog import CATALOG, validate
        tools = {row["name"]: row for row in CATALOG}
        if name not in tools:
            raise ValueError("Tool is not registered")
        spec = tools[name]
        if spec["implementation"] != "offline_implemented":
            raise ValueError("Tool contract is not implemented in this offline library: "+name)
        validate(arguments, spec["input_schema"])
        result = getattr(self, name)(**arguments)
        validate(result, spec["output_schema"])
        self.store.log(name, arguments, result)
        return {"tool": name, "result": result, "real_executions": 0}

    def tool_catalog(self):
        from catalog import CATALOG
        return {"tools": CATALOG, "live_agent_registered": False}

    def project_create(self, title, objective):
        return {"project_ref": self.store.put("project", {"title": title, "objective": objective, "mode": "offline_design_and_mock_only"})}

    def claim_define(self, project_ref, statement, response, primary_term, direction, practical_margin, population_scope, factor_levels, expected_unit_definition):
        self.store.get(project_ref, "project")
        claim = {"project_ref": project_ref, "statement": statement, "response": response, "primary_term": primary_term,
            "direction": direction, "practical_margin": practical_margin, "population_scope": population_scope,
            "factor_levels": factor_levels, "expected_unit_definition": expected_unit_definition,
            "type": "directional_difference", "decision_rule": "prespecified_two_sided_ci", "real_world_verified": False}
        return {"claim_ref": self.store.put("claim", claim)}

    def plan_create(self, project_ref, family):
        self.store.get(project_ref, "project")
        value = adapter("template", family=family)
        return {"plan_ref": self.store.put("plan", {"project_ref": project_ref, "parent": None, "amendment_reason": "synthetic template", **value}),
                "synthetic": True, "execution_authorized": False}

    def plan_patch(self, plan_ref, expected_contract_hash, changes, reason):
        before = self.store.get(plan_ref, "plan")
        contract = before["contract"]
        if digest(contract) != expected_contract_hash:
            raise ValueError("Concurrent/stale plan modification")
        allowed = {"question", "factors", "response", "experimental_unit", "blocks", "replicates", "assumptions", "randomization", "analysis", "resources"}
        if not changes or len({row["path"] for row in changes}) != len(changes):
            raise ValueError("Provide unique explicit changes")
        changed_roots = set()
        for row in changes:
            if set(row) != {"path", "value"} or not row["path"].startswith("/"):
                raise ValueError("Patch schema invalid")
            root = row["path"].split("/")[1]
            if root not in allowed:
                raise ValueError("Cannot patch plan identity, review, authorization or execution status")
            patch_value(contract, row["path"], row["value"])
            changed_roots.add(root)
        request = before["request"]
        # Caller requested amendment becomes an explicit source record; never
        # silently alter the old immutable request. Review every resulting draft.
        for record in request["evidence"]:
            root = record["path"].strip("/")
            if root in changed_roots:
                record.update(value=deepcopy(contract[root]), status="provided", source="user_declaration",
                              reference="Explicit local amendment: "+reason)
        contract["revision"] += 1
        contract["request_hash"] = digest(request)
        value = adapter("compile", contract=contract, request=request)
        return {"plan_ref": self.store.put("plan", {"project_ref": before["project_ref"], "parent": plan_ref,
            "amendment_reason": reason, **value}), "prior_review_invalidated": True, "execution_authorized": False}

    def plan_diff(self, old_plan_ref, new_plan_ref):
        old, new = self.store.get(old_plan_ref, "plan"), self.store.get(new_plan_ref, "plan")
        if old["project_ref"] != new["project_ref"]:
            raise ValueError("Plans belong to different projects")
        keys = sorted(set(old["contract"]) | set(new["contract"]))
        return {"changes": [{"path": "/"+key, "before": old["contract"].get(key), "after": new["contract"].get(key)} for key in keys if old["contract"].get(key) != new["contract"].get(key)],
                "old_plan_ref": old_plan_ref, "new_plan_ref": new_plan_ref}

    def artifact_read(self, artifact_ref):
        return {"artifact": self.store.get(artifact_ref)}

    def plan_review(self, plan_ref):
        plan = self.store.get(plan_ref, "plan")
        value = adapter("review", request=plan["request"], contract=plan["contract"])
        review = {"plan_ref": plan_ref, "reviewer": "fixed_g2_4_verifier_not_the_planner", "validation": value,
            "findings": [{"finding_id": digest([plan_ref, row["code"]])[:16], "code": row["code"], "detail": row["detail"]}
                         for row in value["checks"] if row["status"] == "blocked"]}
        return {"review_ref": self.store.put("review", review), "ready_for_review": value["ready_for_review"],
                "finding_codes": [r["code"] for r in review["findings"]], "expert_calibrated": False}

    def claim_check_plan(self, claim_ref, plan_ref):
        claim, plan = self.store.get(claim_ref, "claim"), self.store.get(plan_ref, "plan")
        c = plan["contract"]
        checks = {"same_project": claim["project_ref"] == plan["project_ref"], "response_matches": claim["response"] == c["response"]["name"],
            "contrast_matches": claim["primary_term"] == c["analysis"]["primary_term"], "direction_matches": claim["direction"] == c["response"]["direction"],
            "factor_levels_match": claim["factor_levels"] == [{"factor": f["name"], "baseline": f["levels"][0], "candidate": f["levels"][1]} for f in c["factors"]],
            "unit_definition_matches": claim["expected_unit_definition"] == c["experimental_unit"]["definition"],
            "scope_bounded": claim["population_scope"] == "declared_dataset_and_training_protocol",
            "inference_protocol_supported": c["analysis"]["multiplicity"] == "single_primary" and c["analysis"]["decision_rule"] == "two_sided_t_ci_practical_relevance_separate"}
        value = {"claim_ref": claim_ref, "plan_ref": plan_ref, "checks": checks, "can_test_conditionally": all(checks.values()),
            "claim_supported": None, "real_world_assumptions_verified": False,
            "note": "Alignment checks do not prove independent units, causal identification or broad-domain generalization"}
        return {"alignment_ref": self.store.put("alignment", value), **value}

    def review_resolve(self, old_review_ref, new_review_ref):
        old, new = self.store.get(old_review_ref, "review"), self.store.get(new_review_ref, "review")
        cursor, ancestors = new["plan_ref"], set()
        while cursor:
            ancestors.add(cursor); cursor = self.store.get(cursor, "plan")["parent"]
        if old["plan_ref"] not in ancestors or new["plan_ref"] == old["plan_ref"]:
            raise ValueError("Resolution requires a new descendant plan and its independent review")
        current_codes = {row["code"] for row in new["findings"]}
        value = {"old_review_ref": old_review_ref, "new_review_ref": new_review_ref,
            "resolved": [r["finding_id"] for r in old["findings"] if r["code"] not in current_codes],
            "still_blocked": [r["finding_id"] for r in old["findings"] if r["code"] in current_codes],
            "new_findings": new["findings"], "all_clear": not new["findings"]}
        return {"resolution_ref": self.store.put("resolution", value), **value}

    def plan_freeze(self, plan_ref, review_ref, alignment_ref):
        plan, review, alignment = self.store.get(plan_ref, "plan"), self.store.get(review_ref, "review"), self.store.get(alignment_ref, "alignment")
        if review["plan_ref"] != plan_ref or alignment["plan_ref"] != plan_ref or not review["validation"]["ready_for_review"] or not alignment["can_test_conditionally"]:
            raise ValueError("Freeze requires the current plan's passing review and claim alignment")
        certificate = {"plan_ref": plan_ref, "review_ref": review_ref, "alignment_ref": alignment_ref,
            "contract_hash": digest(plan["contract"]), "mode": "mock_only", "real_execution_authorized": False,
            "human_approval": None, "primary_term_locked": plan["contract"]["analysis"]["primary_term"]}
        return {"freeze_ref": self.store.put("freeze", certificate), "real_execution_authorized": False}

    def workflow_compile(self, freeze_ref):
        self.store.get(freeze_ref, "freeze")
        rows = [("inspect_frozen_inputs", "artifact_read", []), ("reconcile", "job_reconcile_mock", ["inspect_frozen_inputs"]),
            ("run_or_reuse", "job_run_mock", ["reconcile"]), ("poll", "job_poll_mock", ["run_or_reuse"]),
            ("analyze", "result_analyze", ["poll"]), ("assess_claim", "claim_assess", ["analyze"]),
            ("choose_next", "loop_next_action", ["assess_claim"]), ("write_report", "report_build", ["choose_next"])]
        nodes = [{"id": identity, "tool": tool, "depends_on": deps, "acceptance": {
            "inspect_frozen_inputs": "Frozen plan identity valid", "reconcile": "Match existing job to same frozen plan",
            "run_or_reuse": "At most one synthetic job per frozen plan", "poll": "Only mock-completed unit rows accepted",
            "analyze": "All frozen units accounted for; locked primary contrast analyzed", "assess_claim": "Plan, source, contrast and interval agree",
            "choose_next": "No significance chasing or automatic retest", "write_report": "Separate design pass, mock completion and conditional statistical evidence"}[identity]} for identity, tool, deps in rows]
        bindings = {
            "inspect_frozen_inputs": {"artifact_ref": freeze_ref}, "reconcile": {"freeze_ref": freeze_ref},
            "run_or_reuse": {"freeze_ref": freeze_ref, "scenario": {"$input": "mock_fixture_scenario"}},
            "poll": {"job_ref": {"$from": "run_or_reuse.job_ref"}}, "analyze": {"job_ref": {"$from": "run_or_reuse.job_ref"}},
            "assess_claim": {"claim_ref": {"$input": "claim_ref"}, "analysis_ref": {"$from": "analyze.analysis_ref"}},
            "choose_next": {"assessment_ref": {"$from": "assess_claim.assessment_ref"}},
            "write_report": {"assessment_ref": {"$from": "assess_claim.assessment_ref"}, "workflow_ref": {"$input": "workflow_ref"}}}
        from catalog import CATALOG
        specs = {row["name"]: row for row in CATALOG}
        for node in nodes:
            node["arguments"] = bindings[node["id"]]
            node["produces"] = list(specs[node["tool"]]["output_schema"]["properties"])
            node["on_failure"] = "stop_preserve_evidence_then_revise_and_review_new_version"
        return {"workflow_ref": self.store.put("workflow", {"freeze_ref": freeze_ref, "mode": "mock_only", "nodes": nodes})}

    def workflow_verify(self, workflow_ref):
        from catalog import CATALOG
        workflow = self.store.get(workflow_ref, "workflow")
        implemented = {row["name"] for row in CATALOG if row["implementation"] == "offline_implemented"}
        nodes = workflow["nodes"]
        ids = [row["id"] for row in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate workflow node id")
        remaining, ordered = {row["id"]: row for row in nodes}, []
        while remaining:
            ready = [key for key, row in remaining.items() if set(row["depends_on"]).issubset(ordered)]
            if not ready:
                raise ValueError("Workflow has unknown dependency or a cycle")
            for key in ready:
                if remaining[key]["tool"] not in implemented:
                    raise ValueError("Workflow includes an unimplemented tool")
                ordered.append(key); remaining.pop(key)
        by_id = {row["id"]: row for row in nodes}
        specs = {row["name"]: row for row in CATALOG}
        def ancestors(identity):
            result = set(by_id[identity]["depends_on"])
            for parent in list(result):
                result |= ancestors(parent)
            return result
        for node in nodes:
            if set(node["arguments"]) != set(specs[node["tool"]]["input_schema"]["required"]):
                raise ValueError("Workflow arguments do not match the selected tool")
            for value in node["arguments"].values():
                if type(value) is dict and "$from" in value:
                    source, output_name = value["$from"].split(".", 1)
                    if source not in ancestors(node["id"]) or output_name not in by_id[source]["produces"]:
                        raise ValueError("Workflow output reference has no valid dependency")
        return {"passed": True, "topological_order": ordered, "mode": "mock_only", "scientific_success": None}

    def job_reconcile_mock(self, freeze_ref):
        self.store.get(freeze_ref, "freeze")
        path = self.store.folder/("job_"+freeze_ref[:16]+".json")
        if path.resolve() != path:
            raise ValueError("Redirected mock job index")
        if path.exists():
            record = strict(path.read_text(encoding="utf-8")); job = self.store.get(record["job_ref"], "job")
            if job["freeze_ref"] != freeze_ref:
                raise ValueError("Existing job identity mismatch")
            return {"job_ref": record["job_ref"], "status": "mock_completed", "reused": True}
        return {"job_ref": None, "status": "none", "reused": False}

    def job_run_mock(self, freeze_ref, scenario):
        prior = self.job_reconcile_mock(freeze_ref)
        if prior["job_ref"]:
            job = self.store.get(prior["job_ref"], "job")
            if job["scenario"] != scenario:
                raise ValueError("Cannot change outcome scenario for an existing frozen-plan job; no result shopping")
            return prior
        freeze = self.store.get(freeze_ref, "freeze")
        plan = self.store.get(freeze["plan_ref"], "plan")
        c = plan["contract"]
        import numpy as np
        rng = np.random.default_rng(c["randomization"]["seed"]+17)
        effect = {"benefit": -.06, "null": 0.0, "harm": .06}[scenario]
        rows = []
        for run in c["run_plan"]:
            coded = [-1 if v == f["levels"][0] else 1 for f, v in zip(c["factors"], run["levels"])]
            block_shift = (c["blocks"].index(run["block"]) if c["blocks"] else 0)*.001
            response = .3+block_shift+effect*coded[0]/2+rng.normal(0, c["analysis"]["sigma"])
            if len(coded) == 2:
                response += .005*coded[1]+.003*coded[0]*coded[1]
            rows.append({"unit_id": run["unit_id"], "response": float(response)})
        job_ref = self.store.put("job", {"freeze_ref": freeze_ref, "scenario": scenario, "status": "mock_completed",
            "source_kind": "synthetic_mock", "rows": rows, "real_training_performed": False, "declared_tool_cost_only": True})
        (self.store.folder/("job_"+freeze_ref[:16]+".json")).write_text(canonical({"job_ref": job_ref})+"\n", encoding="utf-8")
        return {"job_ref": job_ref, "status": "mock_completed", "reused": False}

    def job_poll_mock(self, job_ref):
        job = self.store.get(job_ref, "job")
        return {"job_ref": job_ref, "status": job["status"], "units": len(job["rows"]), "real_training_performed": False}

    def result_analyze(self, job_ref):
        import numpy as np
        from scipy.stats import t
        job = self.store.get(job_ref, "job")
        if job["source_kind"] != "synthetic_mock" or job["status"] != "mock_completed" or job["real_training_performed"] is not False:
            raise ValueError("This analyzer accepts only completed synthetic library jobs")
        freeze = self.store.get(job["freeze_ref"], "freeze")
        plan = self.store.get(freeze["plan_ref"], "plan")
        c, values = plan["contract"], job["rows"]
        mapping = {r["unit_id"]: r["response"] for r in values}
        if len(mapping) != len(values) or set(mapping) != {r["unit_id"] for r in c["run_plan"]}:
            raise ValueError("Missing, duplicate or unexpected unit outcomes")
        names = [f["name"] for f in c["factors"]]
        columns = ["intercept", *names]+([":".join(names)] if len(names) == 2 else [])+["block:"+b for b in c["blocks"][1:]]
        x, y = [], []
        for run in c["run_plan"]:
            levels = [-1.0 if v == f["levels"][0] else 1.0 for f, v in zip(c["factors"], run["levels"])]
            x.append([1.0, *levels]+([levels[0]*levels[1]] if len(levels) == 2 else [])+[float(run["block"] == b) for b in c["blocks"][1:]])
            y.append(mapping[run["unit_id"]])
        x, y = np.asarray(x), np.asarray(y)
        if not np.isfinite(y).all() or np.linalg.matrix_rank(x) != len(columns):
            raise ValueError("Nonfinite outcomes or rank-deficient analysis")
        beta = np.linalg.lstsq(x, y, rcond=None)[0]
        df = len(y)-len(columns)
        if df <= 0:
            raise ValueError("No residual variance degrees of freedom")
        mse = float(np.sum((y-x@beta)**2)/df)
        term = c["analysis"]["primary_term"]
        contrast = np.zeros(len(columns)); contrast[columns.index(term)] = 4.0 if ":" in term else 2.0
        effect = float(contrast@beta)
        se = float(np.sqrt(mse*(contrast@np.linalg.inv(x.T@x)@contrast)))
        width = float(t.isf(c["analysis"]["alpha"]/2, df))*se
        report = {"job_ref": job_ref, "freeze_ref": job["freeze_ref"], "plan_ref": freeze["plan_ref"], "response": c["response"]["name"],
            "primary_term": term, "effect": effect, "interval": [effect-width, effect+width], "confidence": 1-c["analysis"]["alpha"],
            "df": df, "model_assumptions_verified": False, "source_kind": "synthetic_mock", "original_unit_count": len(y),
            "decision_rule": "prespecified_two_sided_ci", "posthoc_model_selection": False, "scientific_success": None}
        return {"analysis_ref": self.store.put("analysis", report), **report}

    def claim_assess(self, claim_ref, analysis_ref):
        claim, analysis = self.store.get(claim_ref, "claim"), self.store.get(analysis_ref, "analysis")
        freeze = self.store.get(analysis["freeze_ref"], "freeze")
        locked_alignment = self.store.get(freeze["alignment_ref"], "alignment")
        if locked_alignment["claim_ref"] != claim_ref:
            raise ValueError("Claim was not preregistered with the analyzed frozen plan; no posthoc threshold switching")
        alignment = self.claim_check_plan(claim_ref, analysis["plan_ref"])
        if not alignment["can_test_conditionally"] or claim["response"] != analysis["response"] or claim["primary_term"] != analysis["primary_term"]:
            raise ValueError("Result is not aligned with the requested claim")
        low, high = analysis["interval"]
        oriented = (low, high) if claim["direction"] == "higher" else (-high, -low)
        if oriented[0] > 0:
            status = "supports_direction_under_assumptions"
        elif oriented[1] < 0:
            status = "opposite_direction_under_assumptions"
        else:
            status = "inconclusive"
        value = {"claim_ref": claim_ref, "analysis_ref": analysis_ref, "status": status,
            "practical_benefit_supported": oriented[0] > claim["practical_margin"], "interval": analysis["interval"],
            "evidence_scope": "synthetic_mock_only", "real_scientific_claim_verified": False,
            "limitations": ["Model assumptions and measurement independence not independently verified", "No causal or broad-domain generalization assertion", "Inconclusive is not equivalence"]}
        return {"assessment_ref": self.store.put("assessment", value), **value}

    def loop_next_action(self, assessment_ref):
        value = self.store.get(assessment_ref, "assessment")
        next_step = "report_result_and_limitations" if value["status"] != "inconclusive" else "report_uncertainty_then_consider_separately_preregistered_followup"
        return {"next_step": next_step, "automatic_retest": False, "change_success_threshold": False,
                "required_new_version_for_followup": True, "real_execution_authorized": False}

    def report_build(self, assessment_ref, workflow_ref):
        value = self.store.get(assessment_ref, "assessment")
        workflow = self.store.get(workflow_ref, "workflow")
        analysis = self.store.get(value["analysis_ref"], "analysis")
        if analysis["freeze_ref"] != workflow["freeze_ref"]:
            raise ValueError("Workflow and scientific evidence refer to different frozen plans")
        report = {"assessment_ref": assessment_ref, "workflow_ref": workflow_ref, "design_status": "conditionally_reviewed",
            "execution_status": "mock_completed", "statistical_evidence": value, "real_scientific_claim_verified": False,
            "next_action": self.loop_next_action(assessment_ref), "source": "synthetic_local_demo"}
        return {"report_ref": self.store.put("report", report), **report}
