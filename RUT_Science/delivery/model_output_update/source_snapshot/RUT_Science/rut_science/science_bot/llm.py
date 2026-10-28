"""Use the existing credential reader and shared request/token ledger."""
import json
from pathlib import Path
import time
from ..agents import JSONHTTPAgent
from ..configuration import load_api_config
from ..budget import RunBudget
from ..util import canonical, digest, write_json
from .model_output import read_output, validates_output

PROMPTS = Path(__file__).resolve().parents[2]/"prompts"


class ScienceLLM:
    def __init__(self, session):
        self.session = session
        self.last_output = None

    def _status(self, index, role, status, *, error_type=None, response_hash=None, model=None):
        value = {"request_index": index, "role": role, "status": status,
                 "model": model or self.session.meta["model"]}
        if error_type:
            value["error_type"] = error_type
        if response_hash:
            value["response_hash"] = response_hash
        write_json(self.session.folder/"model_calls"/f"{index:04d}_status.json", value)
        self.last_output = (index, role)
        return value

    def complete_validation(self, role, previous, status, error_type=None):
        if self.last_output is None or self.last_output == previous or self.last_output[1] != role:
            return
        index = self.last_output[0]
        saved = read_output(self.session.folder, str(index))
        if saved["status"] != "pending_validation":
            return
        value = self._status(index, role, status, error_type=error_type,
                             response_hash=digest(saved["response"]), model=saved["model"])
        self.session.emit("model_validation", value)

    def call(self, role, payload, final=False):
        s = self.session
        spec, env = s.spec, s.env
        ledger_path = s.folder/"llm_ledger.json"
        calls = json.loads(ledger_path.read_text(encoding="utf-8"))["calls"] if ledger_path.exists() else []
        # Reserve the last request and 4096 admitted tokens for terminal explanation.
        budget = RunBudget(max_requests=spec.llm_requests if final else max(0, spec.llm_requests-1),
                           max_tokens=spec.llm_tokens if final else max(0, spec.llm_tokens-4096),
                           max_context_bytes=50000, calls=calls, path=ledger_path)
        config = load_api_config()
        agent = JSONHTTPAgent(config["endpoint"], s.meta["model"], api_key=config["api_key"],
                              budget=budget, episode_id=s.meta["id"], protocol="plan", max_output_tokens=1800)
        agent.timeout = min(55, max(1, spec.active_seconds-env.state["active_seconds"]))
        system = (PROMPTS/"system_science_v1.md").read_text(encoding="utf-8")
        instruction = (PROMPTS/(role+".md")).read_text(encoding="utf-8")
        agent.reset(system+"\n"+instruction, [], 0)
        started = time.perf_counter()
        before = len(budget.calls)
        output_hash = None
        failure_status = "failed"
        try:
            result = agent.step([{"role": "user", "content": canonical(payload)}])
            if isinstance(result, dict) and result.get("type") == "invalid":
                failure_status = "schema_rejected"
                raise ValueError("Model returned invalid structured output")
            index = len(budget.calls)
            output_hash = digest(result)
            write_json(s.folder/"model_calls"/f"{index:04d}_response.json",
                       {"role": role, "request_index": index, "model": agent.actual_model or s.meta["model"],
                        "response": result, "response_hash": output_hash})
            schemas = {
                "intake_v2": ("intake_proposal_v2", {"schema_version", "fields", "missing_required", "conflicts", "questions"}),
                "candidate_generator_v1": ("candidate_proposal_v1", {"schema_version", "candidates", "unresolved"}),
                "llm_selector_v1": ("action_selection_v1", {"schema_version", "observation_ref", "action_id", "evidence_refs", "reason"}),
                "report_explainer_v1": ("report_explainer_v1", {"schema_version", "summary", "findings", "limitations", "artifact_refs"})}
            version, keys = schemas[role]
            if not isinstance(result, dict) or set(result) != keys or result.get("schema_version") != version:
                failure_status = "schema_rejected"
                raise ValueError("Model output schema mismatch")
            self._status(index, role, "pending_validation", response_hash=output_hash,
                         model=agent.actual_model)
            s.emit("model_output", {"request_index": index, "role": role,
                                    "status": "pending_validation"})
            return result
        except Exception as exc:
            if len(budget.calls) > before:
                value = self._status(len(budget.calls), role, failure_status,
                                     error_type=type(exc).__name__, response_hash=output_hash,
                                     model=agent.actual_model)
                s.emit("model_output", value)
            else:
                s.emit("model_call_failed", {"role": role, "error_type": type(exc).__name__})
            raise
        finally:
            elapsed = time.perf_counter()-started
            env.state["active_seconds"] += elapsed
            env.state["tokens"] = budget.snapshot()["accounted_tokens"]
            env.state["requests"] = len(budget.calls)
            for record in agent.call_records:
                write_json(s.folder/"model_calls"/f"{len(budget.calls):04d}_request.json",
                           {"role": role, "prompt_hash": digest(instruction), **record})
            s.save()

    @validates_output("llm_selector_v1")
    def choose(self, observation):
        response = self.call("llm_selector_v1", {"policy_observation": observation,
                            "legal_candidates": [c for c in observation["candidates"] if c["legal"]]})
        if response.get("observation_ref") != observation["observation_ref"]:
            raise ValueError("LLM selected from stale observation")
        legal = {c["id"] for c in observation["candidates"] if c["legal"]}
        if response.get("action_id") not in legal:
            raise ValueError("LLM selected an illegal action")
        references = {e["candidate_ref"] for e in observation["experiments"] if e["observed"]}
        if not set(response.get("evidence_refs", [])) <= references:
            raise ValueError("LLM cited unknown evidence")
        return response["action_id"]
