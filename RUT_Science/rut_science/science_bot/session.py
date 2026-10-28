"""Persistent session service used by all user entry points."""
from dataclasses import replace
import json
from pathlib import Path
import re
import threading
import uuid
from .contracts import BudgetedResearchSpec, confirmation_hash, catalog, validate_proposals
from .environment import BudgetedEnvironment
from .numerics import load_data
from .policies import RulePolicy, LearnedPolicy
from .llm import ScienceLLM
from .workspace import Workspace
from .model_output import read_output, validates_output
from ..util import canonical, digest, write_json

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT/"models"/"planner"/"v1"
DEFAULT_POLICY = MODELS/"selected"


def verify_explanation(report, evidence, explanation):
    """Check numeric evidence with tolerance determined by stated decimal precision."""
    report_text = canonical({"report": report, "evidence": evidence})
    permitted = [float(x) for x in re.findall(r"\d+\.\d+", report_text)]
    for value in re.findall(r"\d+\.\d+", canonical(explanation)):
        tolerance = 0.5*10**(-len(value.split(".")[1])) + 1e-10
        if not any(abs(float(value)-known) <= tolerance for known in permitted):
            raise ValueError("Explanation contains an unsupported numeric claim")
    if not set(explanation.get("artifact_refs", [])) <= {"report.json", "report.md"}:
        raise ValueError("Explanation cited unknown artifact")


class ScienceSession:
    def __init__(self, folder, meta, state=None):
        self.folder, self.meta = Path(folder), meta
        self.workspace = Workspace.restore(meta["workspace"]) if meta.get("workspace") else None
        self.spec = BudgetedResearchSpec(**meta["spec"])
        self.lock = threading.RLock()
        self.pause_requested = threading.Event()
        self.cancel_requested = threading.Event()
        self.event_callback = None
        if meta["planner"] in {"rl", "bc"}:
            self.policy = LearnedPolicy(meta["checkpoint"])
        elif meta["planner"] == "llm":
            if meta["backend"] != "api":
                raise ValueError("LLM selector requires backend=api")
            self.policy = None
        else:
            self.policy = RulePolicy(meta["planner"])
        self.policy_identity = self.policy.identity if self.policy else digest({"llm_selector": meta["model"], "prompt": "v1"})
        if meta.get("policy_identity") and meta["policy_identity"] != self.policy_identity:
            raise ValueError("Policy changed; create and confirm a new session")
        self.meta["policy_identity"] = self.policy_identity
        data = load_data(self.spec, ROOT/"data"/"darcy_cpu_v1")
        self.env = BudgetedEnvironment(self.spec, data, folder=self.folder, state=state)
        self.llm = ScienceLLM(self)
        self.confirmation = self._confirmation_hash(data.identity)

    def _confirmation_hash(self, data_identity):
        research_hash = confirmation_hash(self.spec, data_identity, self.policy_identity)
        return digest({"research": research_hash, "workspace": self.workspace.binding}) if self.workspace else research_hash

    @classmethod
    def create(cls, base=None, *, backend="api", planner="rl", checkpoint=None, model="deepseek-flash", spec=None, workspace=None):
        if backend not in {"api", "offline"} or planner not in {"rl", "bc", "llm", "adaptive", "cheap", "dense", "search", "random"}:
            raise ValueError("Invalid backend/planner")
        spec = spec or BudgetedResearchSpec(split="demo")
        project = Workspace.open(workspace) if workspace is not None else None
        base = Path(base).expanduser().resolve() if base is not None else (project.sessions_dir if project else ROOT/"outputs"/"science_bot")
        session_id = uuid.uuid4().hex
        folder = Path(base)/session_id
        if planner == "bc" and checkpoint is None:
            checkpoint = MODELS/"bc"
        meta = {"id": session_id, "backend": backend, "planner": planner,
                "checkpoint": str(Path(checkpoint or DEFAULT_POLICY).resolve()), "model": model,
                "spec": spec.to_dict(), "confirmed": None, "candidates_ready": False,
                "messages": [], "command_results": {}, "phase": "draft", "error": None}
        if project:
            meta["workspace"] = project.binding
        obj = cls(folder, meta)
        obj.save()
        obj.emit("created", {"backend": backend, "planner": planner})
        return obj

    @classmethod
    def restore(cls, folder, *, workspace=None):
        folder = Path(folder).expanduser()
        if workspace is not None and not folder.is_absolute() and not folder.is_dir():
            folder = Workspace.open(workspace, create=False).sessions_dir/folder
        folder = folder.resolve()
        meta = json.loads((folder/"session.json").read_text(encoding="utf-8"))
        if meta.get("engine_version") == "general_v1":
            from .general.conversation import GeneralSession
            return GeneralSession.restore(folder, workspace=workspace)
        if workspace is not None:
            if not meta.get("workspace"):
                raise ValueError("Legacy session has no workspace binding; start a new workspace session")
            Workspace.restore(meta["workspace"], expected_root=workspace)
        envelope = json.loads((folder/"environment.json").read_text(encoding="utf-8"))
        if digest(envelope["state"]) != envelope["hash"]:
            raise ValueError("Environment snapshot hash mismatch")
        obj = cls(folder, meta, envelope["state"])
        if obj.env.data.identity != envelope["data_identity"]:
            raise ValueError("Data changed since checkpoint")
        # Calls may have been admitted immediately before a process crash.
        ledger_path = folder/"llm_ledger.json"
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            obj.env.state.update(tokens=ledger["accounted_tokens"], requests=ledger["requests"])
        if obj.meta["phase"] == "running":
            obj.meta["phase"] = "paused"
        return obj

    def save(self):
        self.env.save()
        write_json(self.folder/"session.json", self.meta)

    def emit(self, kind, payload):
        events = self.events()
        event = {"seq": len(events)+1, "kind": kind, "payload": payload}
        with (self.folder/"events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(canonical(event)+"\n")
        if self.event_callback:
            self.event_callback(event)

    def events(self, after=0):
        path = self.folder/"events.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line][after:]

    def status(self):
        return {"id": self.meta["id"], "phase": self.meta["phase"], "backend": self.meta["backend"],
                "workspace": self.workspace.describe() if self.workspace else None,
                "planner": self.meta["planner"], "policy_hash": self.policy_identity,
                "draft_hash": self.confirmation, "confirmed": self.meta["confirmed"] == self.confirmation,
                "spec": self.spec.to_dict(), "observation": self.env.observe(), "error": self.meta["error"],
                "report_available": self.env.state["report"] is not None}

    def model_output(self, selector="latest"):
        return read_output(self.folder, selector)

    @validates_output("intake_v2")
    def message(self, text):
        with self.lock:
            if self.env.done or self.env.state["decisions"]:
                raise ValueError("Execution already started; create a new session to change the research specification")
            if not isinstance(text, str) or not text.strip() or len(text) > 12000:
                raise ValueError("Provide a nonempty research request (max 12000 characters)")
            self.meta["confirmed"] = None
            self.meta["messages"].append(text)
            self.meta["phase"] = "draft"
            self.save()  # revision revokes authority even if extraction subsequently fails
            changes = {}
            if self.meta["backend"] == "api":
                proposal = self.llm.call("intake_v2", {"latest_user_text": text,
                        "current_draft": self.spec.to_dict(), "catalog_public": {"datasets": ["generated", "Darcy"],
                        "target": "pressure_field for Darcy; regression_output for generated"}, "unresolved_items": []})
                if proposal.get("missing_required") or proposal.get("conflicts"):
                    self.meta["phase"] = "needs_input"; self.save()
                    return {"questions": proposal.get("questions", []), "proposal": proposal}
                fields = proposal.get("fields", {})
                if not isinstance(fields, dict):
                    raise ValueError("Intake fields must be an object")
                for name, item in fields.items():
                    if not isinstance(item, dict) or set(item) != {"value", "source", "evidence"} or item["source"] not in {"user", "suggestion"}:
                        raise ValueError("Invalid field provenance schema")
                    if item.get("source") != "user":
                        continue
                    evidence = item.get("evidence", "")
                    if not evidence or evidence not in text:
                        raise ValueError("Intake field lacks verbatim user evidence")
                    if name == "dataset_name":
                        value = str(item["value"]).lower()
                        if value not in {"darcy", "generated"} or value not in evidence.lower():
                            raise ValueError("Unverified dataset mapping")
                        changes["dataset"] = value
                    elif name in {"compute_units", "quality_threshold"}:
                        value = item["value"]
                        numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", evidence)]
                        if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in numbers:
                            raise ValueError("Unverified numeric extraction")
                        label = r"(?:预算|budget|compute_units|计算单位|CU)" if name == "compute_units" else r"(?:门槛|threshold|quality_threshold)"
                        forward = any(float(v) == value for v in re.findall(label+r"\s*[:：=]?\s*(\d+(?:\.\d+)?)", evidence, re.I))
                        backward = name == "compute_units" and any(float(v) == value for v in re.findall(r"(\d+(?:\.\d+)?)\s*(?:个?计算单位|CU)", evidence, re.I))
                        if not forward and not backward:
                            raise ValueError("Numeric evidence does not authorize this resource or goal field")
                        changes[name] = value
                    elif name in {"target", "objective_metric", "allowed_method_family", "tool_attempts", "split_seed"}:
                        # Unsupported alterations must not be silently treated as granted.
                        allowed = {"target": {"pressure_field", "regression_output"},
                                   "objective_metric": {"mean_relative_l2"}, "allowed_method_family": {"ridge", "mean", "mean_ridge"}}
                        if name not in allowed or item["value"] not in allowed[name]:
                            raise ValueError("Requested specification field is outside the registered protocol")
                    else:
                        raise ValueError("Unknown intake field")
            else:
                lower = text.lower()
                if "darcy" in lower:
                    changes["dataset"] = "darcy"
                elif "generated" in lower or "合成" in lower or "生成" in lower:
                    changes["dataset"] = "generated"
                budget = re.search(r"(?:预算|budget)\s*[:：=]?\s*(\d+)", lower)
                if budget:
                    changes["compute_units"] = int(budget[1])
                threshold = re.search(r"(?:门槛|threshold)\s*[:：=]?\s*(\d+(?:\.\d+)?)", lower)
                if threshold:
                    changes["quality_threshold"] = float(threshold[1])
            new_spec = replace(self.spec, **changes)
            data = load_data(new_spec, ROOT/"data"/"darcy_cpu_v1")
            self.spec = new_spec; self.meta["spec"] = new_spec.to_dict()
            self.env.spec, self.env.data = new_spec, data
            self.confirmation = self._confirmation_hash(data.identity)
            self.meta.update(phase="draft", candidates_ready=False, error=None)
            self.save(); self.emit("draft", {"spec": new_spec.to_dict(), "draft_hash": self.confirmation})
            return self.status()

    def confirm(self, value):
        with self.lock:
            if value != self.confirmation or self.meta["phase"] not in {"draft", "paused"}:
                raise ValueError("Confirmation does not match current reviewable draft")
            self.meta["confirmed"] = value
            self.meta["phase"] = "confirmed"
            self.save(); self.emit("confirmed", {"draft_hash": value})

    @validates_output("candidate_generator_v1")
    def propose(self):
        if self.meta["candidates_ready"]:
            return
        if self.meta["backend"] == "api":
            proposal = self.llm.call("candidate_generator_v1", {"confirmed_spec": self.spec.to_dict(),
                    "allowed_catalog": [{"template_id": c["kind"], "parameters": c["parameters"]} for c in catalog()],
                    "observed_evidence": [], "budget_policy": self.env.observe()["budget"]})
            selected = validate_proposals(proposal.get("candidates"))
            # Full-directory completion is pre-registered and identical for all policies.
            self.emit("candidate_supply", {"proposed_count": len(selected), "pool_mode": "host_complete_full_catalog"})
        self.meta["candidates_ready"] = True
        self.save()

    def step(self):
        if self.meta["confirmed"] != self.confirmation:
            raise ValueError("Current specification has not been confirmed")
        self.propose()
        if (self.env.state["active_seconds"] >= self.spec.active_seconds
                or (self.meta["planner"] == "llm" and self.env.state["requests"] >= self.spec.llm_requests-1)
                or self.env.state["tokens"] >= self.spec.llm_tokens-4096):
            self.env.finalize("host_finalize_due_to_budget"); return
        obs = self.env.observe()
        chooser = self.llm if self.meta["planner"] == "llm" else self.policy
        action = chooser.choose(obs)
        if (self.env.state["active_seconds"] >= self.spec.active_seconds
                or self.env.state["tokens"] > self.spec.llm_tokens):
            self.env.finalize("host_finalize_due_to_budget")
            return
        self.emit("selected", {"action": action, "observation_ref": obs["observation_ref"],
                               "budget": obs["budget"]})
        result = self.env.step_action(action, obs["observation_ref"], f"{self.meta['id']}_{obs['observation_ref']}_{action}")
        self.emit("tool_result", {"action": action, "result": result, "observation": self.env.observe()})
        self.save()

    @validates_output("report_explainer_v1")
    def _explain_report(self):
        explanation = self.llm.call("report_explainer_v1", {"verified_report": self.env.state["report"],
            "public_evidence_index": self.env.observe()["experiments"], "artifact_allowlist": ["report.json", "report.md"]}, final=True)
        verify_explanation(self.env.state["report"], self.env.observe()["experiments"], explanation)
        write_json(self.folder/"explanation.json", explanation)

    def finish(self):
        self.meta["phase"] = self.env.state["phase"]
        if self.env.done and self.meta["backend"] == "api" and not self.meta.get("explanation_attempted"):
            self.meta["explanation_attempted"] = True; self.save()
            try:
                self._explain_report()
            except Exception as exc:
                self.meta["explanation_error"] = type(exc).__name__
                self.emit("explanation_failed", {"error_type": type(exc).__name__})
        if self.env.state["report"]:
            report = self.env.state["report"]
            report["resources"].update(llm_requests=self.env.state["requests"], llm_tokens=self.env.state["tokens"],
                                       active_seconds=self.env.state["active_seconds"])
            write_json(self.folder/"report.json", report)
        self.save()
        self.emit("finished", {"report": self.env.state["report"]})

    def run(self, *, max_steps=None):
        from .graph import run_graph
        from ..planning_agent import session_lock
        # Reuse the existing cross-process lock; HTTP also serializes in-process.
        with self.lock, session_lock(self.folder):
            if self.env.done:
                return self.env.state["report"]
            if self.meta["confirmed"] != self.confirmation:
                raise ValueError("Confirm the displayed draft hash before running")
            self.pause_requested.clear()
            self.meta["phase"] = "running"; self.meta["error"] = None; self.save()
            try:
                run_graph(self, max_steps=max_steps)
            except Exception as exc:
                self.meta["phase"] = "paused"
                self.meta["error"] = {"type": type(exc).__name__, "detail": str(exc)[:180]}
                self.save(); self.emit("error", self.meta["error"])
                raise
            return self.env.state["report"]

    def pause(self):
        self.pause_requested.set()

    def cancel(self):
        self.cancel_requested.set()
        self.pause_requested.set()
