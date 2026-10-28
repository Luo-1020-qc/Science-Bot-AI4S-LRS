"""Evaluator-owned scientific reference and independent plan/trajectory audit."""
import json
from pathlib import Path

from .contracts import DialogueSpec
from .plan_spec import PlanSpec, accept_result, resolve_node
from dataclasses import asdict
from .research_spec import ResearchSpec
from .util import digest, state_diff, write_json


def environment_for(manifest):
    if manifest["workflow"] == "darcy":
        if manifest.get("research_model") == "validation_select":
            from .adaptive_workflow import SelectionDarcyEnvironment
            return SelectionDarcyEnvironment(Path(manifest["data"]))
        from .darcy_workflow import DarcyEnvironment
        return DarcyEnvironment(Path(manifest["data"]))
    from .environment import ScientificMLEnvironment
    return ScientificMLEnvironment()


def strict_session_score(manifest, spec, episode):
    if manifest["workflow"] == "darcy":
        if spec.model == "validation_select":
            from .adaptive_workflow import selection_reference, score_selection_episode
            reference = selection_reference(Path(manifest["data"]), spec)
            return score_selection_episode(Path(manifest["data"]), spec, episode, reference), reference
        from .darcy_workflow import independent_reference, score_episode
        folder = Path(manifest["data"])
        reference = independent_reference(folder, spec)
        return score_episode(folder, spec, episode, reference), reference
    from .benchmark import build_tasks
    from .evaluator import evaluate
    from .validation import replay_oracle
    if manifest["task_id"] == "intake_synthetic":
        from .contracts import TaskSpec, GoldAction
        from .plan_spec import public_control_plan
        plan = public_control_plan(spec)
        task = TaskSpec("intake_synthetic", spec.dataset_name, spec.target, spec.unit, spec.model,
            spec.train_fraction, spec.split_seed, [GoldAction(n.node_id, n.tool, n.arguments) for n in plan.nodes],
            [(d, n.node_id) for n in plan.nodes for d in n.depends_on])
    else:
        task = next(t for t in build_tasks() if t.task_id == manifest["task_id"])
    reference = replay_oracle(task)
    # Public confirmed parameters are the same; confirmation authority is the
    # operator for this CLI rather than the two-turn benchmark fixture.
    reference["final_state"]["research_spec"] = episode["final_state"]["research_spec"]
    task.expected_state_delta = state_diff(reference["initial_state"], reference["final_state"])
    dialogue = DialogueSpec(task.task_id, "ideal", ("operator_confirmed",), no_write_turns=())
    return evaluate(task, dialogue, episode), reference


def evaluate_session(manifest, spec, episode):
    from .recovery import apply_recovery_score
    strict, reference = strict_session_score(manifest, spec, episode)
    return apply_recovery_score(strict, manifest, episode, episode.get("planning_history", [])), reference


def artifact_hash(path):
    import hashlib
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def seal_artifacts(output):
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_hashes"] = {str(p.relative_to(output)).replace("\\", "/"): artifact_hash(p)
        for p in sorted(output.rglob("*")) if p.is_file() and p.name not in {"manifest.json", "verification.json", "session.lock"}}
    write_json(manifest_path, manifest)


def verify_artifacts(output: Path):
    from .planning_agent import read_checkpoint
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "complete":
        raise ValueError("Scientific verification requires a completed run")
    for name, checksum in manifest["artifact_hashes"].items():
        path = (output / name).resolve()
        if not path.is_relative_to(output.resolve()) or artifact_hash(path) != checksum:
            raise ValueError("Planning artifact identity mismatch")
    for name, checksum in manifest["source_hashes"].items():
        if digest((output / "source_snapshot" / name).read_text(encoding="utf-8")) != checksum:
            raise ValueError("Frozen planning source changed")
    checkpoint = read_checkpoint(output)
    record = json.loads((output / "episode.json").read_text(encoding="utf-8"))
    spec = ResearchSpec(**json.loads((output / "research_spec.json").read_text(encoding="utf-8")))
    if manifest.get("intake_confirmation") is not None:
        from .intake_contract import validate_receipt
        receipt = manifest["intake_confirmation"]
        validate_receipt(receipt, spec)
        if any(manifest[key] != value for key, value in receipt["draft"]["execution_policy"].items()):
            raise ValueError("Execution manifest differs from confirmed intake policy")
        confirmation = record["episode"]["final_state"]["research_spec"]["confirmation"]
        if confirmation != {"source": "operator_config", "reference": "intake:"+receipt["confirmation_hash"]}:
            raise ValueError("Scientific execution does not cite its intake confirmation")
    env = environment_for(manifest)
    if spec.spec_hash != manifest["research_spec_hash"] or env.snapshot() != record["episode"]["initial_state"]:
        raise ValueError("Planning specification or original dataset changed")
    plans = {}
    previous = None
    for path in sorted((output / "plans").glob("plan_v*.json")):
        plan = PlanSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))
        plan.validate(spec, env.available_tools(), manifest["max_tool_calls"])
        if previous is not None and (plan.version != previous.version+1 or plan.parent_plan_hash != previous.plan_hash or plan.plan_id != previous.plan_id):
            raise ValueError("Plan revision chain is inconsistent")
        if previous is None and plan.version != 1:
            raise ValueError("Plan history must start at version 1")
        plans[plan.version] = plan
        previous = plan
    current = record["episode"]["initial_state"]
    completed, results, calls = set(), {}, 0
    previous_event_plan = None
    for event in record["episode"]["events"]:
        if event["event_type"] == "research_spec_confirmed":
            current = json.loads(json.dumps(current))
            current["research_spec"] = {k: event[k] for k in ("spec", "spec_hash", "confirmation")}
            current["budget"]["max_train_calls"] = spec.max_train_calls
            current["budget"]["max_test_calls"] = spec.max_test_calls
            if current["research_spec"]["spec"] != spec.to_dict() or current["research_spec"]["spec_hash"] != spec.spec_hash:
                raise ValueError("Confirmation does not bind saved specification")
        if event["event_type"] != "tool_call":
            continue
        calls += 1
        plan = plans[event["plan_version"]]
        if calls > min(plan.max_tool_calls, manifest["max_tool_calls"]):
            raise ValueError("Cumulative tool attempt budget exceeded")
        if previous_event_plan is not None and plan.version != previous_event_plan.version:
            if plan.version < previous_event_plan.version:
                raise ValueError("Tool trajectory reverted to an obsolete plan version")
            old_nodes = {n.node_id: n for n in previous_event_plan.nodes}
            new_nodes = {n.node_id: n for n in plan.nodes}
            if any(node_id not in new_nodes or asdict(old_nodes[node_id]) != asdict(new_nodes[node_id]) for node_id in completed):
                raise ValueError("Plan revision altered completed execution evidence")
        previous_event_plan = plan
        if plan.plan_hash != event["plan_hash"]:
            raise ValueError("Tool event refers to a different plan")
        nodes = {n.node_id: n for n in plan.nodes}
        node = nodes[event["node_id"]]
        if not set(node.depends_on) <= completed or event["node_id"] in completed or event["tool_name"] != node.tool:
            raise ValueError("Tool event executed a nonready/duplicate/mismatched node")
        if resolve_node(node, results) != event["arguments"]:
            raise ValueError("Tool arguments differ from validated plan bindings")
        before, after = event["state_before"], event["state_after"]
        if before != current or digest(before) != event["state_hash_before"] or digest(after) != event["state_hash_after"] or state_diff(before, after) != event["state_diff"]:
            raise ValueError("Planning environment state chain is inconsistent")
        current = after
        if accept_result(node, event["tool_result"]):
            completed.add(node.node_id)
            results[node.node_id] = event["tool_result"]
    if current != record["episode"]["final_state"] or current != checkpoint["environment_state"] or calls != checkpoint["tool_calls"]:
        raise ValueError("Final checkpoint differs from trajectory")
    if (previous is None or previous.to_dict() != checkpoint["plan"] or completed != set(checkpoint["node_status"])
            or any(value != "succeeded" for value in checkpoint["node_status"].values()) or results != checkpoint["results"]):
        raise ValueError("Completed plan state differs from saved results")
    for call in record["episode"]["model_calls"]:
        if digest(call["request_body"]) != call["request_body_hash"]:
            raise ValueError("Planner model request hash mismatch")
    if spec.model == "validation_select":
        branches = [h for h in checkpoint["history"] if h.get("event") == "branch_decision"]
        selection = next(iter(current["selections"].values()))
        if (len(branches) != 1 or branches[0]["selected_method"] != selection["selected_method"] or branches[0]["model_id"] != selection["model_id"]
                or branches[0]["validation_scores"] != selection["validation_scores"]):
            raise ValueError("Validation branch evidence is inconsistent")
    if "recovery_policy" in manifest and record["episode"].get("planning_history", []) != checkpoint["history"]:
        raise ValueError("Recovery/branch history differs from checkpoint")
    rescored, reference = evaluate_session(manifest, spec, record["episode"])
    if rescored != record["score"] or reference != json.loads((output / "reference.json").read_text(encoding="utf-8")):
        raise ValueError("Independent planning scientific rescoring differs")
    if manifest["workflow"] == "darcy":
        import numpy as np
        evaluation = next(iter(current["evaluations"].values()))
        with np.load(output / "test_predictions.npz", allow_pickle=False) as arrays:
            if not (np.array_equal(arrays["prediction"].reshape(32, 225), evaluation["predictions"]) and
                    np.array_equal(arrays["target"], env.arrays["test"]["sol"]) and np.array_equal(arrays["coefficient"], env.arrays["test"]["coeff"])):
                raise ValueError("Prediction artifact differs from scientific state")
    result = {"status": "passed", "execution_success": rescored["execution_success"], "artifact_hashes_verified": True,
              "source_snapshot_verified": True, "checkpoint_verified": True, "plan_versions": len(plans),
              "plan_readiness_and_bindings_verified": True, "state_chain_verified": True,
              "scientific_rescoring_verified": True, "model_request_hashes_verified": True}
    write_json(output / "verification.json", result)
    return result
