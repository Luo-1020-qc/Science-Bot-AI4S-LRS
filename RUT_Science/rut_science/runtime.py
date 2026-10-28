import copy
import math
import time

from .agents import JSONHTTPAgent, ModelServiceError
from .contracts import AgentAdapter, DialogueSpec, SYSTEM_PROMPT, WRITE_TOOLS
from .environment import ScientificMLEnvironment
from .util import canonical, digest, state_diff
from .budget import RunLimitError
from .research_spec import ResearchSpec


def run_episode(agent: AgentAdapter, environment: ScientificMLEnvironment,
                dialogue: DialogueSpec, seed: int = 0, max_steps: int = 20, max_seconds: float = 60,
                *, research_spec: ResearchSpec | None = None, confirmation_turn: int = 1,
                confirmation_source: str = "benchmark_user_fixture") -> dict:
    """Advance a user turn only after an assistant message; no future-turn exposure."""
    if max_steps < 1 or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("Positive step and time limits required")
    if research_spec is not None and (dialogue.mode != "execute" or
            confirmation_turn in dialogue.no_write_turns or not 0 <= confirmation_turn < len(dialogue.turns)):
        raise ValueError("Specification confirmation must bind an executable, authorized user turn")
    initial = environment.snapshot()
    messages, events, steps = [], [], 0
    started = time.monotonic()
    termination = "completed_dialogue"
    agent.reset(SYSTEM_PROMPT, environment.available_tools(), seed)
    for turn_index, content in enumerate(dialogue.turns):
        messages.append({"role": "user", "content": content})
        events.append({"event_type": "user_message", "turn_index": turn_index, "step_index": steps, "content": content})
        if research_spec is not None and turn_index == confirmation_turn:
            record = environment.confirm_research_spec(research_spec, source=confirmation_source,
                                                       reference=f"{dialogue.task_id}:turn_{turn_index}")
            events.append({"event_type": "research_spec_confirmed", "turn_index": turn_index,
                           "step_index": steps, **record})
            messages.append({"role": "system", "content": "TRUSTED_RUNTIME: User-confirmed ResearchSpec; actions must match: "
                             + canonical(record)})
        while True:
            remaining = max_seconds - (time.monotonic() - started)
            if steps >= max_steps or remaining <= 0:
                termination = "step_limit" if steps >= max_steps else "time_limit"
                break
            if isinstance(agent, JSONHTTPAgent):
                agent.timeout = min(20.0, remaining)
            call_started = time.monotonic()
            steps += 1
            try:
                decision = agent.step(copy.deepcopy(messages))
            except RunLimitError as exc:
                events.append({"event_type": "run_limit", "turn_index": turn_index, "step_index": steps, "message": str(exc)})
                termination = "run_limit"
                break
            except ModelServiceError as exc:
                events.append({"event_type": "service_error", "turn_index": turn_index, "step_index": steps, "message": str(exc)})
                termination = "service_error"
                break
            except Exception as exc:
                events.append({"event_type": "adapter_error", "turn_index": turn_index, "step_index": steps,
                               "exception_type": type(exc).__name__})
                termination = "adapter_error"
                break
            decision_latency = (time.monotonic() - call_started)*1000
            if time.monotonic() - started >= max_seconds:
                events.append({"event_type": "deadline_exceeded", "turn_index": turn_index,
                               "step_index": steps, "decision_latency_ms": decision_latency})
                termination = "time_limit"
                break
            if isinstance(decision, dict) and decision.get("type") == "tool_call" and isinstance(decision.get("name"), str):
                name, arguments = decision["name"], decision.get("arguments")
                before = environment.snapshot()
                execution_started = time.monotonic()
                if turn_index in dialogue.no_write_turns and name in WRITE_TOOLS:
                    result = {"status": "error", "error_code": "permission_denied", "message": "Resolve and confirm the request before research writes."}
                else:
                    result = environment.invoke(name, arguments)
                after = environment.snapshot()
                call_id = f"call_{steps:03d}"
                event = {
                    "event_type": "tool_call", "turn_index": turn_index, "step_index": steps,
                    "call_id": call_id, "tool_name": name, "arguments": arguments, "tool_result": result,
                    "is_write": name in WRITE_TOOLS, "state_hash_before": digest(before), "state_hash_after": digest(after),
                    "state_diff": state_diff(before, after), "state_before": before, "state_after": after,
                    "decision_latency_ms": decision_latency, "tool_latency_ms": (time.monotonic()-execution_started)*1000,
                }
                events.append(event)
                messages.append({"role": "assistant", "content": canonical(decision)})
                messages.append({"role": "tool", "name": name, "call_id": call_id, "result": result})
            elif (isinstance(decision, dict) and decision.get("type") == "message" and
                  isinstance(decision.get("content"), str) and decision["content"].strip()):
                events.append({"event_type": "assistant_message", "turn_index": turn_index, "step_index": steps,
                               "content": decision["content"], "response_mode": decision.get("response_mode", "answer"),
                               "decision_latency_ms": decision_latency})
                messages.append({"role": "assistant", "content": decision["content"]})
                break
            else:
                events.append({"event_type": "invalid_action", "turn_index": turn_index, "step_index": steps})
                messages.append({"role": "user", "content": "RUNTIME_FEEDBACK: Invalid action; return a documented JSON action or a nonempty message."})
        if termination != "completed_dialogue":
            break
    return {
        "initial_state": initial, "final_state": environment.snapshot(), "messages": messages, "events": events,
        "termination": termination, "steps": steps, "elapsed_seconds": time.monotonic()-started,
        "tokens": getattr(agent, "usage", {"prompt_tokens": 0, "completion_tokens": 0}),
        "actual_model": getattr(agent, "actual_model", None), "run_seed": seed,
        "model_calls": getattr(agent, "call_records", []),
        "max_steps": max_steps, "max_seconds": max_seconds,
    }
