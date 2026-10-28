"""LangGraph orchestration with validated plans and atomic local checkpoints.

The planner sees public contracts/results only. Checkpoints and evaluation
artifacts are host-owned; this is not an arbitrary-code execution sandbox.
"""
import copy
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
import importlib.metadata
import json
import math
from pathlib import Path
import time
from typing import TypedDict

from . import __version__
from .agents import JSONHTTPAgent, ModelServiceError
from .budget import RunBudget, RunLimitError
from .configuration import DEFAULT_API_CONFIG, load_api_config
from .environment import ScientificMLEnvironment
from .plan_spec import (PlanSpec, PlanValidationError, accept_result, public_control_plan, resolve_node)
from .research_spec import ResearchSpec
from .util import canonical, digest, state_diff, write_json
from .recovery import RecoveryPolicy, RETRYABLE_CODES

PLAN_PROMPT = """You create a complete executable scientific plan, not individual tool actions.
Return exactly one planspec_v1 JSON object. No Markdown, prose or wrapper.
Top-level fields: schema_version='planspec_v1', plan_id (safe ASCII identifier), version=1,
research_spec_hash (copy supplied hash), parent_plan_hash=null, max_tool_calls (copy requested_tool_budget), nodes (six nodes).
Each node has exactly: node_id, tool, arguments, depends_on, outputs, acceptance.
Use each stage once: inspect_dataset -> validate_dataset -> split_dataset -> train_model -> evaluate_model -> write_report.
Node IDs are your choice; dependencies must enforce the scientific order.
Use exact supplied ResearchSpec parameters, enum strings, and documented tool schemas.
IDs do not exist yet: validation dataset_id must reference inspection; split dataset_id may reference inspection or validation;
split_id must reference the split output;
model_id the train output; evaluation_id the evaluation output. Reference syntax: '$node_id.output_field'.
depends_on must be a JSON array of node-ID strings, even when empty.
outputs MUST be a JSON ARRAY containing one string, e.g. ["dataset_id"], NEVER an object or a mapping.
The output string is dataset_id for inspect and validate, split_id for split, model_id for train,
evaluation_id for evaluate, report_id for report. acceptance={'status':'ok'} for all stages;
also valid=true for validate, sealed=true for evaluate, evidence_complete=true for report.
Example node schema: {"node_id":"inspect","tool":"inspect_dataset","arguments":{"dataset_name":"COPY_SPEC_DATASET_NAME"},"depends_on":[],"outputs":["dataset_id"],"acceptance":{"status":"ok"}}.
Do not generate shell/Python code, invented IDs, extra tools, retries, or alternative model names.
The host will validate the plan before any tool execution. The confirmed research specification is immutable.
You receive no Gold, sealed data, private state snapshots, or independent reference predictions.
"""


class GraphState(TypedDict):
    phase: str


SELECTION_PROMPT = """Return only a planspec_v2 JSON object for the confirmed validation_select protocol.
Top-level fields exactly: schema_version='planspec_v2', plan_id (ASCII identifier), version=1,
research_spec_hash (copy supplied hash), parent_plan_hash=null, max_tool_calls (copy requested_tool_budget), nodes.
Exactly eight nodes; every node has node_id, role, tool, arguments, depends_on (array of node IDs),
outputs (array of one string), acceptance (object).
Roles/tools: inspect:inspect_dataset; validate:validate_dataset; split:split_dataset;
fit_ridge:train_model(model='ridge_field'); fit_mean:train_model(model='mean_field');
select:select_model; evaluate:evaluate_model; report:write_report.
Precedence: inspect -> validate -> split -> BOTH fits -> select -> evaluate -> report.
Use exact ResearchSpec parameters. IDs must be '$node_id.output_field' references to ancestor outputs.
validate.dataset_id references inspect; split.dataset_id references inspect or validate;
fits.split_id references split; select.ridge_model_id references fit_ridge.model_id;
select.mean_model_id references fit_mean.model_id; evaluate.model_id MUST reference select.model_id;
report.evaluation_id references evaluate.evaluation_id.
outputs=['dataset_id'] for inspect/validate, ['split_id'] for split, ['model_id'] for fits/select,
['evaluation_id'] for evaluate, ['report_id'] for report. acceptance={'status':'ok'};
add valid=true for validate, selected=true for select, sealed=true for evaluate, evidence_complete=true for report.
Both fits are pre-authorized. Select by validation error; exactly one chosen model gets a sealed test.
No code, invented IDs, extra fields, or test-based selection. Public contracts only.
"""


@contextmanager
def session_lock(output: Path):
    """OS advisory lock; released by the OS if the process exits/crashes."""
    output.mkdir(parents=True, exist_ok=True)
    with (output / "session.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            import os
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError("Another process is using this planning session") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_checkpoint(output: Path) -> dict:
    wrapped = json.loads((output / "checkpoint.json").read_text(encoding="utf-8"))
    if set(wrapped) != {"state", "state_hash"} or digest(wrapped["state"]) != wrapped["state_hash"]:
        raise ValueError("Checkpoint content hash mismatch")
    return wrapped["state"]


class PlanningSession:
    def __init__(self, output: Path, environment, manifest: dict, state: dict, transport=None, budget=None, progress=None):
        self.output, self.env, self.manifest = output, environment, manifest
        self.state, self.transport, self.budget = state, transport, budget
        self.progress = progress or (lambda message: None)
        self.started = time.monotonic()
        self.base_elapsed = state["elapsed_seconds"]
        self.stop_after = None
        self.invocation_successes = 0

    @classmethod
    def create(cls, output: Path, environment, spec: ResearchSpec, *, workflow="darcy", data=None, task_id="darcy_cpu_001",
               backend="offline", plan_file=None, model=None, api_config=DEFAULT_API_CONFIG, profile=0, credential_field="API",
               max_seconds=180, max_tool_calls=12, max_plan_attempts=3, max_requests=3, max_tokens=80_000, progress=None,
               recovery_policy=None, fault_injection=None, intake_receipt=None, shared_budget_path=None):
        if any(output.iterdir()):
            # The advisory lock file is the only permitted pre-existing artifact.
            if any(p.name != "session.lock" for p in output.iterdir()):
                raise ValueError("Use a new planning output directory")
        if backend not in {"offline", "api", "file"} or (backend == "file" and plan_file is None):
            raise ValueError("Select offline, api, or file backend with --plan-file")
        if type(max_tool_calls) is not int or not 6 <= max_tool_calls <= 12 or type(max_plan_attempts) is not int or not 1 <= max_plan_attempts <= 5:
            raise ValueError("Host tool limit must be 6..12 and plan attempts 1..5")
        if not math.isfinite(max_seconds) or max_seconds <= 0 or min(max_requests, max_tokens) < 1:
            raise ValueError("Positive time and request/token limits required")
        policy = RecoveryPolicy.from_dict(recovery_policy)
        fault = fault_injection or {"tool": None, "count": 0, "error_code": "transient_unavailable"}
        if set(fault) != {"tool", "count", "error_code"} or type(fault["count"]) is not int or not 0 <= fault["count"] <= 3 or (
                fault["count"] and fault["tool"] not in {t["name"] for t in environment.available_tools()}) or fault["error_code"] not in RETRYABLE_CODES:
            raise ValueError("Fault injection must be a bounded before-invocation fixture")
        if intake_receipt is not None:
            from .intake_contract import validate_receipt
            validate_receipt(intake_receipt, spec)
            confirmed_policy = intake_receipt["draft"]["execution_policy"]
            actual_policy = {"backend": backend, "model": model, "max_requests": max_requests, "max_tokens": max_tokens,
                "max_seconds": max_seconds, "max_tool_calls": max_tool_calls, "max_plan_attempts": max_plan_attempts,
                "recovery_policy": policy.to_dict(), "fault_injection": fault}
            if (confirmed_policy != actual_policy or intake_receipt["draft"]["workflow"] != workflow
                    or intake_receipt["draft"]["data"] != (str(Path(data).resolve()) if data is not None else None)):
                raise ValueError("Execution differs from the confirmed intake policy or dataset location")
        minimum = 8 if spec.model == "validation_select" else 6
        requested_budget = minimum + (policy.max_total_retries if policy.enabled else 0)
        if requested_budget > max_tool_calls:
            raise ValueError("Tool budget cannot cover the workflow and recovery policy")
        prompt = SELECTION_PROMPT if spec.model == "validation_select" else PLAN_PROMPT
        if policy.enabled:
            prompt += "\nSet max_tool_calls to requested_tool_budget; recovery is exclusively managed by the trusted host."
        initial = environment.snapshot()
        reference = f"intake:{intake_receipt['confirmation_hash']}" if intake_receipt else f"{task_id}:turn_0"
        record = environment.confirm_research_spec(spec, source="operator_config", reference=reference)
        config = load_api_config(api_config, profile, credential_field) if backend == "api" else None
        model = model or (config["model"] if config else None)
        if backend == "api" and not model:
            raise ValueError("--model is required because API_key_Agent.json has no model field")
        sources = {p.name: digest(p.read_text(encoding="utf-8")) for p in sorted(Path(__file__).parent.glob("*.py"))}
        manifest = {"version": __version__, "protocol": "structured_science_plan_v1", "workflow": workflow,
            "data": str(Path(data).resolve()) if data is not None else None, "task_id": task_id, "backend": backend,
            "created_utc": datetime.now(timezone.utc).isoformat(), "source_hashes": sources,
            "research_spec_hash": spec.spec_hash, "dataset_hash": spec.dataset_hash, "tools_hash": digest(environment.available_tools()),
            "planner_prompt_hash": digest(prompt), "langgraph_version": importlib.metadata.version("langgraph"),
            "research_model": spec.model, "recovery_policy": policy.to_dict(), "requested_tool_budget": requested_budget,
            "fault_injection": fault, "intake_confirmation": intake_receipt,
            "shared_budget_path": str(Path(shared_budget_path).resolve()) if shared_budget_path else None,
            "max_seconds": max_seconds, "max_tool_calls": max_tool_calls, "max_plan_attempts": max_plan_attempts,
            "max_requests": max_requests, "max_tokens": max_tokens, "model": model,
            "api_config": str(Path(api_config).resolve()) if config else None, "api_profile": profile if config else None,
            "credential_field": credential_field if config else None, "api_endpoint": config["endpoint"] if config else None,
            "plan_file": str(Path(plan_file).resolve()) if plan_file is not None else None,
            "state_boundary": "Checkpoint contains private local state; planner receives public ResearchSpec/tool registry only",
            "status": "planning", "active_plan_hash": None}
        state = {"phase": "planning", "spec": spec.to_dict(), "initial_state": initial,
                 "environment_state": environment.snapshot(), "plan": None, "candidate": None,
                 "node_status": {}, "results": {}, "plan_attempts": 0, "tool_calls": 0,
                 "elapsed_seconds": 0.0, "model_calls": [], "tokens": {"prompt_tokens": 0, "completion_tokens": 0},
                 "validation_errors": [], "history": [], "score": None,
                 "recovery_count": 0, "recovery_draft": None, "faults_remaining": fault["count"],
                 "events": [{"event_type": "user_message", "turn_index": 0, "step_index": 0,
                             "content": "Confirmed ResearchSpec_JSON: " + canonical(spec.to_dict())},
                            {"event_type": "research_spec_confirmed", "turn_index": 0, "step_index": 0, **record}]}
        for name in sources:
            path = output / "source_snapshot" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text((Path(__file__).parent / name).read_text(encoding="utf-8"), encoding="utf-8")
        write_json(output / "manifest.json", manifest)
        write_json(output / "research_spec.json", spec.to_dict())
        session = cls(output, environment, manifest, state, progress=progress)
        if config is not None:
            session._configure_transport(config)
        session.save()
        return session

    @classmethod
    def restore(cls, output: Path, environment, progress=None):
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        state = read_checkpoint(output)
        current_sources = {p.name: digest(p.read_text(encoding="utf-8")) for p in sorted(Path(__file__).parent.glob("*.py"))}
        if manifest["source_hashes"] != current_sources or manifest["langgraph_version"] != importlib.metadata.version("langgraph"):
            raise ValueError("Resume requires the same code and LangGraph version; use the frozen source or a new run")
        spec = ResearchSpec(**state["spec"])
        if spec.spec_hash != manifest["research_spec_hash"] or digest(environment.available_tools()) != manifest["tools_hash"]:
            raise ValueError("Resume specification/tool contract mismatch")
        if environment.snapshot() != state["initial_state"]:
            raise ValueError("Resume dataset or initial environment changed")
        if any(status == "running" for status in state["node_status"].values()):
            raise ValueError("An interrupted node has uncertain effects; automatic replay is refused")
        if state["plan"] is not None:
            plan = PlanSpec.from_dict(state["plan"])
            plan.validate(spec, environment.available_tools(), manifest["max_tool_calls"])
            saved = output / "plans" / f"plan_v{plan.version:03d}.json"
            if not saved.exists() or json.loads(saved.read_text(encoding="utf-8")) != plan.to_dict():
                raise ValueError("Checkpoint plan differs from its saved plan version")
        environment.reset(state["environment_state"])
        session = cls(output, environment, manifest, state, progress=progress)
        if manifest["backend"] == "api" and state["phase"] in {"planning", "validation"}:
            config = load_api_config(Path(manifest["api_config"]), manifest["api_profile"], manifest["credential_field"])
            if config["endpoint"] != manifest["api_endpoint"]:
                raise ValueError("Resume API endpoint changed")
            session._configure_transport(config)
        return session

    def _configure_transport(self, config):
        self.budget = RunBudget(self.manifest["max_requests"], self.manifest["max_tokens"], 60_000,
                                path=Path(self.manifest["shared_budget_path"]) if self.manifest.get("shared_budget_path") else self.output / "budget.json")
        if self.budget.path.exists():
            self.budget.calls = json.loads(self.budget.path.read_text(encoding="utf-8"))["calls"]
        self.transport = JSONHTTPAgent(config["endpoint"], self.manifest["model"], api_key=config["api_key"],
                                      budget=self.budget, episode_id=self.manifest["task_id"], protocol="plan", max_output_tokens=4096)
        prompt = SELECTION_PROMPT if self.state["spec"]["model"] == "validation_select" else PLAN_PROMPT
        if self.manifest.get("recovery_policy", {}).get("enabled"):
            prompt += "\nSet max_tool_calls to requested_tool_budget; recovery is exclusively managed by the trusted host."
        self.transport.reset(prompt, self.env.available_tools(), 0)
        self.transport.call_records = copy.deepcopy(self.state["model_calls"])
        self.transport.usage = copy.deepcopy(self.state["tokens"])
        self.budget.persist()

    def save(self):
        self.state["elapsed_seconds"] = self.base_elapsed + time.monotonic() - self.started
        self.state["environment_state"] = self.env.snapshot()
        if self.transport is not None:
            self.state["model_calls"] = copy.deepcopy(self.transport.call_records)
            self.state["tokens"] = copy.deepcopy(self.transport.usage)
        write_json(self.output / "checkpoint.json", {"state": self.state, "state_hash": digest(self.state)})
        self.manifest.update(status=self.state["phase"], active_plan_hash=digest(self.state["plan"]) if self.state["plan"] else None)
        write_json(self.output / "manifest.json", self.manifest)
        write_json(self.output / "status.json", self.public_status())

    def public_status(self):
        return {"phase": self.state["phase"], "workflow": self.manifest["workflow"], "backend": self.manifest["backend"],
                "plan_version": self.state["plan"]["version"] if self.state["plan"] else None,
                "plan_attempts": self.state["plan_attempts"], "tool_calls": self.state["tool_calls"],
                "recovery_count": self.state.get("recovery_count", 0),
                "nodes": copy.deepcopy(self.state["node_status"]), "elapsed_seconds": self.state["elapsed_seconds"],
                "tokens": self.state["tokens"], "validation_errors": self.state["validation_errors"],
                "execution_success": self.state["score"]["execution_success"] if self.state["score"] else None}

    def remaining_seconds(self):
        return self.manifest["max_seconds"] - (self.base_elapsed + time.monotonic() - self.started)

    def halt(self, phase, detail):
        self.state["phase"] = phase
        self.state["history"].append({"event": phase, "detail": detail})
        self.progress(f"STOP: {phase}: {detail}")
        self.save()
        return {"phase": phase}

    def propose(self, _):
        if self.remaining_seconds() <= 0 or self.state["plan_attempts"] >= self.manifest["max_plan_attempts"]:
            return self.halt("limit_reached", "Planning time/attempt limit reached")
        self.state["plan_attempts"] += 1
        self.save()  # Persist admission before network call.
        spec = ResearchSpec(**self.state["spec"])
        self.progress(f"PLAN attempt {self.state['plan_attempts']} ({self.manifest['backend']})")
        try:
            if self.manifest["backend"] == "offline":
                candidate = replace(public_control_plan(spec), max_tool_calls=self.manifest["requested_tool_budget"]).to_dict()
            elif self.manifest["backend"] == "file":
                candidate = json.loads(Path(self.manifest["plan_file"]).read_text(encoding="utf-8-sig"))
            else:
                self.transport.timeout = min(55.0, self.remaining_seconds())
                context = {"research_spec": spec.to_dict(), "research_spec_hash": spec.spec_hash,
                           "host_max_tool_calls": self.manifest["max_tool_calls"], "validation_feedback": self.state["validation_errors"],
                           "requested_tool_budget": self.manifest["requested_tool_budget"]}
                candidate = self.transport.step([{"role": "user", "content": "Generate the complete PlanSpec for this confirmed public research specification:\n" + canonical(context)}])
            if len(canonical(candidate).encode()) > 60_000:
                raise ValueError("Plan proposal exceeds the size limit")
            self.state["candidate"] = candidate
            write_json(self.output / "proposals" / f"attempt_{self.state['plan_attempts']:03d}.json", candidate)
            self.state["phase"] = "validation"
            self.save()
            return {"phase": "validation"}
        except (ModelServiceError, RunLimitError) as exc:
            return self.halt("service_error" if isinstance(exc, ModelServiceError) else "limit_reached", str(exc))
        except (ValueError, OSError) as exc:
            return self.halt("plan_rejected", str(exc))

    def validate(self, _):
        try:
            plan = PlanSpec.from_dict(self.state["candidate"])
            result = plan.validate(ResearchSpec(**self.state["spec"]), self.env.available_tools(), self.manifest["max_tool_calls"])
            if plan.version != 1:
                raise PlanValidationError("Initial plan must be version 1")
            if plan.max_tool_calls < self.manifest["requested_tool_budget"]:
                raise PlanValidationError("Plan budget must include the pre-authorized recovery allowance")
            self.install_plan(plan, result)
            self.progress(f"VALIDATED: plan v{plan.version}, {len(plan.nodes)} nodes")
            return {"phase": "executing"}
        except (PlanValidationError, TypeError, ValueError) as exc:
            message = str(exc)
            self.state["validation_errors"].append(message)
            self.state["history"].append({"event": "plan_rejected", "attempt": self.state["plan_attempts"], "detail": message})
            self.progress("REJECTED: " + message)
            if self.manifest["backend"] == "api" and self.state["plan_attempts"] < self.manifest["max_plan_attempts"]:
                self.state["phase"] = "planning"
                self.save()
                return {"phase": "planning"}
            return self.halt("plan_rejected", message)

    def install_plan(self, plan, validation):
        path = self.output / "plans" / f"plan_v{plan.version:03d}.json"
        if path.exists() and json.loads(path.read_text(encoding="utf-8")) != plan.to_dict():
            raise PlanValidationError("Cannot overwrite an existing plan version")
        write_json(path, plan.to_dict())
        write_json(self.output / "plans" / f"validation_v{plan.version:03d}.json", validation)
        old_status = self.state["node_status"]
        self.state["node_status"] = {n.node_id: "succeeded" if old_status.get(n.node_id) == "succeeded" else "pending" for n in plan.nodes}
        self.state["plan"] = plan.to_dict()
        self.state["phase"] = "executing"
        self.save()

    def execute(self, _):
        if self.remaining_seconds() <= 0:
            return self.halt("limit_reached", "Active execution time limit reached")
        plan = PlanSpec.from_dict(self.state["plan"])
        plan.validate(ResearchSpec(**self.state["spec"]), self.env.available_tools(), self.manifest["max_tool_calls"])
        if all(status == "succeeded" for status in self.state["node_status"].values()):
            self.state["phase"] = "verification"
            self.save()
            return {"phase": "verification"}
        if self.stop_after is not None and self.invocation_successes >= self.stop_after:
            return self.halt("paused", "Paused at a completed-node boundary; resume does not rerun completed nodes")
        if self.state["tool_calls"] >= min(plan.max_tool_calls, self.manifest["max_tool_calls"]):
            return self.halt("limit_reached", "Cumulative tool attempt limit reached")
        ready = [n for n in plan.nodes if self.state["node_status"][n.node_id] == "pending" and
                 all(self.state["node_status"].get(d) == "succeeded" for d in n.depends_on)]
        if not ready:
            return self.halt("execution_failed", "No runnable node; failed predecessors cannot be skipped")
        node = ready[0]
        arguments = resolve_node(node, self.state["results"])
        self.state["node_status"][node.node_id] = "running"
        self.state["tool_calls"] += 1
        self.save()  # Running marker prevents uncertain-effect replay after a crash.
        before = self.env.snapshot()
        started = time.monotonic()
        fault = self.manifest.get("fault_injection", {})
        injected = self.state.get("faults_remaining", 0) > 0 and node.tool == fault.get("tool")
        if injected:
            self.state["faults_remaining"] -= 1
            result = {"status": "error", "error_code": fault["error_code"], "message": "Explicit before-invocation fault fixture; no tool effects applied"}
        else:
            result = self.env.invoke(node.tool, arguments)
        after = self.env.snapshot()
        self.state["events"].append({"event_type": "tool_call", "turn_index": 0, "step_index": self.state["tool_calls"],
            "call_id": f"call_{self.state['tool_calls']:03d}", "plan_version": plan.version, "plan_hash": plan.plan_hash,
            "node_id": node.node_id, "tool_name": node.tool, "arguments": arguments, "tool_result": result,
            "state_before": before, "state_after": after, "state_hash_before": digest(before), "state_hash_after": digest(after),
            "state_diff": state_diff(before, after), "tool_latency_ms": (time.monotonic()-started)*1000,
            "is_write": node.tool not in {"inspect_dataset", "validate_dataset"}, "fault_injected": injected})
        accepted = accept_result(node, result)
        self.state["node_status"][node.node_id] = "succeeded" if accepted else "failed"
        if result.get("status") == "ok":
            self.state["results"][node.node_id] = result
        self.progress(f"NODE {node.node_id}: {node.tool} -> {'succeeded' if accepted else 'failed'}")
        self.save()
        if not accepted:
            policy = RecoveryPolicy.from_dict(self.manifest.get("recovery_policy"))
            event = self.state["events"][-1]
            if (policy.permits(event, self.state["history"], self.state["recovery_count"]) and self.remaining_seconds() > 0
                    and self.state["tool_calls"] < min(plan.max_tool_calls, self.manifest["max_tool_calls"])):
                self.state["phase"] = "recovering"
                self.save()
                return {"phase": "recovering"}
            return self.halt("execution_failed", "Tool call or node acceptance failed; effects/errors are retained")
        self.invocation_successes += 1
        if node.tool == "select_model":
            self.state["phase"] = "branch_ridge" if result["selected_method"] == "ridge_field" else "branch_mean"
            self.save()
            return {"phase": self.state["phase"]}
        return {"phase": "executing"}

    def recover(self, _):
        event = next(e for e in reversed(self.state["events"]) if e["event_type"] == "tool_call")
        draft = self.state.get("recovery_draft")
        if draft is None or draft["failed_call_id"] != event["call_id"]:
            policy = RecoveryPolicy.from_dict(self.manifest.get("recovery_policy"))
            if not policy.permits(event, self.state["history"], self.state["recovery_count"]) or self.remaining_seconds() <= 0:
                return self.halt("execution_failed", "Recovery is not authorized or no longer has budget")
            old = PlanSpec.from_dict(self.state["plan"])
            new = replace(old, version=old.version+1, parent_plan_hash=old.plan_hash)
            draft = {"failed_call_id": event["call_id"], "plan": new.to_dict()}
            self.state["recovery_draft"] = draft
            self.state["recovery_count"] += 1
            self.state["history"].append({"event": "recovery_decision", "strategy": "retry_same_node", "node_id": event["node_id"],
                "failed_call_id": event["call_id"], "error_code": event["tool_result"]["error_code"],
                "from_plan_hash": old.plan_hash, "to_plan_hash": new.plan_hash,
                "retained_nodes": [n for n, status in self.state["node_status"].items() if status == "succeeded"]})
            self.save()
        self.revise(PlanSpec.from_dict(draft["plan"]), "Automatic bounded retry of atomic transient failure: " + event["call_id"])
        self.state["phase"], self.state["recovery_draft"] = "executing", None
        self.progress(f"RECOVERY: retry {event['node_id']}; retained completed nodes; plan v{self.state['plan']['version']}")
        self.save()
        return {"phase": "executing"}

    def branch(self, _):
        selection = next(iter(self.env.snapshot()["selections"].values()))
        self.state["history"].append({"event": "branch_decision", "selected_method": selection["selected_method"],
            "model_id": selection["model_id"], "validation_scores": selection["validation_scores"],
            "selection_policy": selection["policy"], "phase": self.state["phase"]})
        self.progress("BRANCH: validation selected " + selection["selected_method"])
        self.state["phase"] = "executing"
        self.save()
        return {"phase": "executing"}

    def revise(self, plan: PlanSpec, reason: str):
        if self.state["plan"] is None or self.state["phase"] in {"complete", "verification"} or not isinstance(reason, str) or not reason.strip():
            raise PlanValidationError("Only an unfinished saved plan can be revised with a nonempty reason")
        old = PlanSpec.from_dict(self.state["plan"])
        validation = plan.validate(ResearchSpec(**self.state["spec"]), self.env.available_tools(), self.manifest["max_tool_calls"])
        if plan.plan_id != old.plan_id or plan.version != old.version+1 or plan.parent_plan_hash != old.plan_hash:
            raise PlanValidationError("Revision must retain plan ID, increment version, and bind parent hash")
        new_nodes = {n.node_id: n for n in plan.nodes}
        for node in old.nodes:
            if self.state["node_status"][node.node_id] == "succeeded" and (node.node_id not in new_nodes or asdict(new_nodes[node.node_id]) != asdict(node)):
                raise PlanValidationError("A revision cannot change or invalidate an already executed node")
        if any(e.get("tool_result", {}).get("status") == "ok" and self.state["node_status"].get(e.get("node_id")) == "failed"
               for e in self.state["events"] if e["event_type"] == "tool_call"):
            raise PlanValidationError("A failed acceptance check has applied effects; retry requires manual reconciliation")
        self.state["history"].append({"event": "plan_revision", "reason": reason, "old_plan_hash": old.plan_hash,
            "new_plan_hash": plan.plan_hash, "old_version": old.version, "new_version": plan.version,
            "superseded_pending_nodes": [n.node_id for n in old.nodes if self.state["node_status"][n.node_id] != "succeeded"]})
        self.install_plan(plan, validation)
        self.state["phase"] = "paused"
        self.save()

    def episode(self):
        return {"initial_state": self.state["initial_state"], "final_state": self.env.snapshot(), "events": self.state["events"],
                "messages": [], "termination": "completed_dialogue" if self.state["phase"] in {"verification", "complete"} else self.state["phase"],
                "steps": self.state["tool_calls"], "elapsed_seconds": self.state["elapsed_seconds"], "tokens": self.state["tokens"],
                "model_calls": self.state["model_calls"], "actual_model": (self.state["model_calls"][-1].get("actual_model", self.manifest["model"])
                    if self.state["model_calls"] else self.manifest["model"]),
                "run_seed": 0}

    def verify(self, _):
        from .planning_evaluation import evaluate_session
        episode = self.episode()
        episode["planning_history"] = copy.deepcopy(self.state["history"])
        score, reference = evaluate_session(self.manifest, ResearchSpec(**self.state["spec"]), episode)
        self.state["score"] = score
        self.state["phase"] = "complete"
        self.save()
        completed_episode = self.episode()
        completed_episode["planning_history"] = copy.deepcopy(self.state["history"])
        write_json(self.output / "episode.json", {"episode": completed_episode, "score": score})
        write_json(self.output / "reference.json", reference)
        write_json(self.output / "scientific_reports.json", self.env.snapshot()["reports"])
        write_json(self.output / "planning_history.json", self.state["history"])
        write_json(self.output / "model_calls.json", self.state["model_calls"])
        budget_path = Path(self.manifest["shared_budget_path"]) if self.manifest.get("shared_budget_path") else self.output / "budget.json"
        if budget_path.exists():
            write_json(self.output / "budget_snapshot.json", json.loads(budget_path.read_text(encoding="utf-8")))
        reports = self.env.snapshot()["reports"]
        report = next(iter(reports.values()), {})
        node_rows = "\n".join(f"| {node_id} | {status} |" for node_id, status in self.state["node_status"].items())
        report_text = (f"# Structured scientific planning run\n\nWorkflow: {self.manifest['workflow']}; backend: {self.manifest['backend']}; "
            f"plan version: {self.state['plan']['version']}; scientific execution success: {score['execution_success']}.\n\n"
            f"Tool attempts: {self.state['tool_calls']}; planner attempts: {self.state['plan_attempts']}; "
            f"input/output tokens: {self.state['tokens']['prompt_tokens']}/{self.state['tokens']['completion_tokens']}.\n\n"
            f"Final metric: {report.get('metric')} = {report.get('value')} {report.get('metric_unit', report.get('unit', ''))}.\n\n"
            "| Node | Status |\n|---|---|\n" + node_rows + "\n\n"
            "[Plan](plans/plan_v" + f"{self.state['plan']['version']:03d}" + ".json) · [ResearchSpec](research_spec.json) · "
            "[Trajectory](trajectory.jsonl) · [Scientific reports](scientific_reports.json) · [Verification](verification.json)\n\n"
            f"Strict execution success: {score.get('strict_execution_success', score['execution_success'])}; "
            f"recovery success: {score.get('recovery_success', 'disabled')}; original failures: {score.get('failure_count', 0)}.\n\n"
            "Development workflow with host-constrained decisions; no planning gain, generalization, or paper reproduction claim.\n")
        (self.output / "report.md").write_text(report_text, encoding="utf-8")
        (self.output / "trajectory.jsonl").write_text("\n".join(canonical(e) for e in self.state["events"])+"\n", encoding="utf-8")
        if self.manifest["workflow"] == "darcy":
            import numpy as np
            evaluation = next(iter(self.env.snapshot()["evaluations"].values()))
            np.savez_compressed(self.output / "test_predictions.npz", prediction=np.asarray(evaluation["predictions"]).reshape(32, 15, 15),
                                target=self.env.arrays["test"]["sol"], coefficient=self.env.arrays["test"]["coeff"])
        self.progress(f"VERIFIED: scientific execution success={score['execution_success']}")
        from .planning_evaluation import seal_artifacts, verify_artifacts
        seal_artifacts(self.output)
        verify_artifacts(self.output)
        return {"phase": "complete"}

    def run(self, stop_after=None):
        if stop_after is not None and (type(stop_after) is not int or stop_after < 1):
            raise ValueError("--stop-after must be a positive completed-node count")
        if self.state["phase"] == "complete":
            if "artifact_hashes" in self.manifest:
                from .planning_evaluation import verify_artifacts
                verify_artifacts(self.output)
                self.progress("Already complete; no model or tool calls repeated")
                return self.public_status()
            # A crash between the completed checkpoint and artifact sealing can
            # safely retry evaluation/export; never repeat scientific tool calls.
            self.state["phase"] = "verification"
            self.progress("Recovering interrupted result publication; scientific tools will not repeat")
        if self.state["phase"] == "paused":
            self.state["phase"] = "executing"
        if self.state["phase"] not in {"planning", "validation", "executing", "verification", "recovering", "branch_ridge", "branch_mean"}:
            raise ValueError("This session is halted; inspect status and revise explicitly where allowed")
        self.stop_after = stop_after
        from langgraph.graph import END, START, StateGraph
        graph = StateGraph(GraphState)
        graph.add_node("propose", self.propose)
        graph.add_node("validate", self.validate)
        graph.add_node("execute", self.execute)
        graph.add_node("verify", self.verify)
        graph.add_node("recover", self.recover)
        graph.add_node("branch_ridge", self.branch)
        graph.add_node("branch_mean", self.branch)
        routes = {"planning": "propose", "validation": "validate", "executing": "execute", "verification": "verify",
                  "recovering": "recover", "branch_ridge": "branch_ridge", "branch_mean": "branch_mean"}
        def route(value):
            return routes.get(value["phase"], END)
        destinations = {name: name for name in routes.values()} | {END: END}
        graph.add_conditional_edges(START, route, destinations)
        for name in routes.values():
            graph.add_conditional_edges(name, route, destinations)
        compiled = graph.compile()
        try:
            compiled.invoke({"phase": self.state["phase"]}, {"recursion_limit": 64})
        except KeyboardInterrupt:
            # Never mask a running marker; restore will refuse uncertain effects.
            if "running" not in self.state["node_status"].values():
                self.halt("paused" if self.state["plan"] else "planning", "Interrupted between nodes")
            raise
        return self.public_status()
