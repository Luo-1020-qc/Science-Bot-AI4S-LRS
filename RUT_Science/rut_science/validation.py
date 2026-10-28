from .benchmark import build_dialogues, resolve_arguments
from .contracts import BEHAVIORS, DialogueSpec, TaskSpec, WRITE_TOOLS
from .environment import PARAMETERS, ScientificMLEnvironment, make_initial_state
from .evaluator import evaluate
from .util import digest, state_diff
from .research_spec import ResearchSpec


def replay_oracle(task: TaskSpec, initial: dict | None = None) -> dict:
    env = ScientificMLEnvironment(initial if initial is not None else make_initial_state())
    before, bindings, events = env.snapshot(), {}, []
    env.confirm_research_spec(ResearchSpec.from_task(task, before), source="benchmark_user_fixture",
                              reference=f"{task.task_id}:turn_1")
    for step, node in enumerate(task.oracle, 1):
        arguments = resolve_arguments(node.arguments, bindings)
        state_before = env.snapshot()
        result = env.invoke(node.tool, arguments)
        if result["status"] != "ok":
            raise ValueError(f"Oracle {task.task_id}/{node.node_id} is not executable: {result}")
        bindings[node.node_id] = result
        state_after = env.snapshot()
        events.append({"event_type": "tool_call", "turn_index": 1, "step_index": step,
                       "tool_name": node.tool, "arguments": arguments, "tool_result": result,
                       "is_write": node.tool in WRITE_TOOLS, "state_before": state_before, "state_after": state_after,
                       "state_diff": state_diff(state_before, state_after),
                       "state_hash_before": digest(state_before), "state_hash_after": digest(state_after)})
    return {"initial_state": before, "final_state": env.snapshot(), "events": events,
            "termination": "completed_dialogue", "steps": len(events)}


def validate_benchmark(tasks: list[TaskSpec]) -> dict:
    reports = []
    for task in tasks:
        replay = replay_oracle(task)
        task.expected_state_delta = state_diff(replay["initial_state"], replay["final_state"])
        score = evaluate(task, DialogueSpec(task.task_id, "ideal", ("", "")), replay)
        if not score["execution_success"]:
            raise ValueError(f"Oracle failed independent checks: {task.task_id}: {score}")
        dialogues = build_dialogues(task)
        if tuple(d.behavior for d in dialogues) != BEHAVIORS or any(len(d.turns) != 2 for d in dialogues):
            raise ValueError("Incomplete paired dialogue set")
        hidden_ids = ("ds_1", "ds_2", "ds_3", "split_", "model_", "eval_", "report_")
        for dialogue in dialogues:
            text = "\n".join(dialogue.turns)
            if any(name in text for name in PARAMETERS) or any(identifier in text for identifier in hidden_ids):
                raise ValueError(f"Tool or ID leakage: {task.task_id}/{dialogue.behavior}")
        # Schema/leak checks are mechanical. Authored semantics still require review.
        reports.append({"task_id": task.task_id, "oracle_verified": True,
                        "oracle_steps": task.optimal_action_budget,
                        "initial_state_hash": digest(replay["initial_state"]),
                        "expected_state_delta_hash": digest(task.expected_state_delta),
                        "paired_schema_and_leakage_checks": True,
                        "dialogue_semantic_review": "authored_and_reviewed_during_implementation; independent_review_pending"})
    # Error atomicity / repeatability exercise independently of successful oracle replay.
    env = ScientificMLEnvironment()
    initial = env.snapshot()
    errors = [env.invoke("train_model", {"split_id": "unobserved", "model": "linear"}),
              env.invoke("inspect_dataset", {"dataset_name": "missing"}),
              env.invoke("edit_test_labels", {"dataset_id": "ds_1"})]
    if not all(e["status"] == "error" for e in errors) or env.snapshot() != initial:
        raise ValueError("Failed tool calls changed environment state")
    return {"status": "passed", "task_count": len(tasks), "paired_instance_count": len(tasks)*len(BEHAVIORS),
            "environment_error_atomicity": True, "tasks": reports,
            "source": "project_extension_not_official_RUT_reproduction"}
