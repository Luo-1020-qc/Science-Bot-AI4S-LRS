"""Versioned real-tool candidate protocol; actor never receives scenario labels."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT/"tool_runtime"
sys.dont_write_bytecode = True
sys.path.insert(0, str(RUNTIME))
import core as tools_core
import doe_adapter
from catalog import CATALOG, validate as validate_tool_schema

# Same frozen G2.4 implementation, invoked in this dedicated offline trainer.
# No live Agent imports, external service, or read/write outside this dataset.
tools_core.adapter = lambda action, **payload: doe_adapter.execute({"action": action, **payload})
Library = tools_core.Library
VERSION = "tool_harness_rl_v2"
REWARD_VERSION = "public_evidence_completion_v2"
ACTION_SPECS = [
    ("review", "plan_review"), ("align_claim", "claim_check_plan"), ("diff", "plan_diff"),
    ("model_two_arm", "plan_patch"), ("model_additive_blocks", "plan_patch"),
    ("model_full_factorial", "plan_patch"), ("model_blocked_full_factorial", "plan_patch"),
    ("repair_response", "plan_patch"), ("repair_budget", "plan_patch"),
    ("resolve", "review_resolve"), ("freeze", "plan_freeze"),
    ("workflow", "workflow_compile"), ("verify_workflow", "workflow_verify"),
    ("reconcile", "job_reconcile_mock"), ("run_mock", "job_run_mock"), ("poll", "job_poll_mock"),
    ("analyze", "result_analyze"), ("assess", "claim_assess"), ("next", "loop_next_action"),
    ("report", "report_build"), ("read_plan", "artifact_read"),
    ("ask_variance", "host.ask_user"), ("stop", "host.stop_with_evidence")]
ACTION_IDS = tuple(row[0] for row in ACTION_SPECS)
FEATURE_NAMES = ("cvit", "family_crd", "family_rcbd", "family_factorial", "variance_available", "public_unavailable",
    "public_tool_failure", "has_parent", "model_two_arm", "model_additive_blocks", "model_full_factorial", "model_blocked_full_factorial",
    "response_matches_request", "declared_budget_fraction", "review_exists", "review_current", "review_passed", "old_review_pending",
    "alignment_current", "alignment_passed", "freeze_exists", "workflow_exists", "workflow_checked", "job_queried", "job_exists",
    "analysis_exists", "assessment_exists", "next_step_exists", "report_exists", "turn_fraction", "last_call_failed", "bias")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value, *, lines=False, fresh=False):
    path = Path(path).absolute()
    if not path.is_relative_to(ROOT) or path.resolve() != path:
        raise ValueError("Dataset output must be a non-redirected child of v2")
    path.parent.mkdir(parents=True, exist_ok=True)
    if fresh and path.exists():
        raise ValueError("Never overwrite an existing release or sampling batch")
    text = "".join(canonical(row)+"\n" for row in value) if lines else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
    path.write_text(text, encoding="utf-8")


def rows(path):
    return [tools_core.strict(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_runtime():
    manifest = json.loads((RUNTIME/"source_manifest.json").read_text(encoding="utf-8"))
    for row in manifest:
        if sha(RUNTIME/row["copy"]) != row["copy_sha256"]:
            raise ValueError("Pinned offline tool implementation changed")
    return digest(CATALOG)


def validate_task(task):
    keys = {"schema_version", "task_id", "policy_split", "root_group", "data_lineage", "public", "simulator", "expert_review"}
    if type(task) is not dict or set(task) != keys or task["schema_version"] != VERSION:
        raise ValueError("Task must use the closed v2 task envelope")
    if task["policy_split"] not in {"train", "development", "evaluation_example"}:
        raise ValueError("Unknown task split")
    for key in ("task_id", "root_group"):
        if type(task[key]) is not str or not task[key].strip():
            raise ValueError("Task identity/source group required")
    p = task["public"]
    required = {"domain", "user_request", "family", "factors", "unit_definition", "response", "primary_term", "direction",
        "practical_margin", "minimum_effect", "sigma", "variance_source", "target_power", "resource_budget", "max_decisions"}
    if type(p) is not dict or set(p) != required or p["domain"] not in {"darcy", "cvit"} or p["family"] not in {"crd_two_arm", "rcbd_two_arm", "factorial_2x2"}:
        raise ValueError("Unsupported or open public goal schema")
    if type(p["max_decisions"]) is not int or not 8 <= p["max_decisions"] <= 80:
        raise ValueError("Invalid decision budget")
    if p["direction"] not in {"lower", "higher"} or any(type(p[key]) is not str or not p[key].strip() for key in ("user_request", "unit_definition", "response", "primary_term")):
        raise ValueError("Explicit claim, unit and response declarations required")
    for field in ("minimum_effect", "target_power", "resource_budget", "practical_margin"):
        if type(p[field]) not in (int, float) or p[field] < 0:
            raise ValueError("Numeric planning inputs required")
    if not .5 <= p["target_power"] <= .9999 or p["minimum_effect"] <= 0 or p["resource_budget"] <= 0:
        raise ValueError("Planning inputs outside supported range")
    factors = p["factors"]
    if type(factors) is not list or len(factors) != (2 if p["family"] == "factorial_2x2" else 1):
        raise ValueError("Factor count differs from the registered family")
    for f in factors:
        if type(f) is not dict or set(f) != {"name", "levels"} or type(f["name"]) is not str or type(f["levels"]) is not list or len(f["levels"]) != 2 or any(type(v) is not str or not v for v in f["levels"]) or len(set(f["levels"])) != 2:
            raise ValueError("Factor names and two distinct string levels required")
    if p["sigma"] is not None and (type(p["sigma"]) not in (int, float) or p["sigma"] <= 0 or not p["variance_source"]):
        raise ValueError("Known variance needs a positive value and source")
    if p["sigma"] is None and p["variance_source"] is not None:
        raise ValueError("Unknown variance must not carry a fabricated source")
    simulator = task["simulator"]
    if set(simulator) != {"initial_fault", "outcome_scenario", "user_variance_answer", "existing_job", "job_failure"}:
        raise ValueError("Unknown simulator schema")
    if simulator["initial_fault"] not in {"none", "wrong_model", "wrong_response", "low_budget", "stale_review"} or simulator["outcome_scenario"] not in {"benefit", "null", "harm"}:
        raise ValueError("Unregistered simulator fixture")
    if type(simulator["existing_job"]) is not bool or simulator["job_failure"] not in {None, "mock_oom"}:
        raise ValueError("Invalid mock job fixture")
    if simulator["user_variance_answer"] is not None:
        raise ValueError("Provide known sigma/source in public fields; this simulator version only scripts unavailable answers")
    lineage = task["data_lineage"]
    if set(lineage) != {"source_ancestor_ids", "scientific_partitions", "source_kind"} or lineage["source_kind"] not in {"synthetic_reference_only", "expert_authored_metadata_no_raw_arrays"}:
        raise ValueError("Source ancestry and synthetic provenance are mandatory")
    if type(lineage["source_ancestor_ids"]) is not list or not lineage["source_ancestor_ids"] or any(type(x) is not str or not x for x in lineage["source_ancestor_ids"]):
        raise ValueError("Source ancestor ids required")
    partitions = lineage["scientific_partitions"]
    if set(partitions) != {"train", "validation", "test"} or len(set(partitions.values())) != 3:
        raise ValueError("Scientific train/validation/test identities must differ")
    review = task["expert_review"]
    if set(review) != {"status", "reviewer", "reason", "reviewed_at"} or review["status"] not in {"pending", "approved", "rejected"}:
        raise ValueError("Expert review schema invalid")
    canonical(task)
    return True


def read_tasks(split, *, purpose, extension=None):
    if split not in {"train", "development", "evaluation_example"}:
        raise ValueError("Unknown split")
    if purpose in {"training", "review", "ppo"} and split != "train":
        raise PermissionError("Training/review/PPO cannot consume development or evaluation tasks")
    tasks = rows(ROOT/"tasks"/(split+".jsonl"))
    for task in tasks:
        validate_task(task)
    if extension is not None:
        if split != "train": raise PermissionError("Task extensions are for training only")
        path = Path(extension).absolute()
        if path.resolve() != path or not path.is_relative_to(ROOT): raise ValueError("Extension must remain inside v2")
        value = tools_core.strict(path.read_text(encoding="utf-8"))
        certificate = tools_core.strict(path.with_suffix(".preflight.json").read_text(encoding="utf-8"))
        if value["version"] != "expert_task_extension_v2" or digest(value["records"]) != value["records_hash"] or not certificate["passed"] or certificate["records_hash"] != value["records_hash"] or certificate["catalog_hash"] != verify_runtime() or certificate["environment_hash"] != sha(ROOT/"environment.py") or certificate["reward_protocol_hash"] != sha(ROOT/"protocol.py"):
            raise ValueError("Extension lacks a matching successful tool-environment preflight")
        for task in value["records"]:
            validate_task(task)
            if task["policy_split"] != "train" or task["expert_review"]["status"] != "approved": raise ValueError("Unapproved/non-training extension task")
        tasks += value["records"]
    return tasks


def validate_observation(obs):
    if type(obs) is not dict or set(obs) != {"schema_version", "goal", "current_contract", "artifact_refs", "flags", "evidence", "history", "turn", "last_call_failed", "candidates", "real_execution_allowed"}:
        raise ValueError("Observation leaks curator metadata or misses required fields")
    if obs["real_execution_allowed"] is not False or obs["schema_version"] != VERSION or len(obs["candidates"]) != len(ACTION_IDS):
        raise ValueError("Observation permissions/protocol mismatch")
    catalog = {row["name"]: row for row in CATALOG}
    for index, candidate in enumerate(obs["candidates"]):
        if set(candidate) != {"action_id", "tool", "arguments", "available"} or (candidate["action_id"], candidate["tool"]) != ACTION_SPECS[index] or type(candidate["available"]) is not bool:
            raise ValueError("Candidate does not match the pinned tool action protocol")
        if candidate["available"] and not candidate["tool"].startswith("host."):
            spec = catalog[candidate["tool"]]
            if spec["implementation"] != "offline_implemented": raise ValueError("A disabled tool entered the actor action space")
            arguments = json.loads(canonical(candidate["arguments"]))
            if candidate["tool"] == "job_run_mock":
                if arguments["scenario"] != {"$host": "private_mock_fixture"}: raise ValueError("Policy cannot choose its mock outcome")
                arguments["scenario"] = "null"  # Schema check with a legal stand-in, not the hidden outcome.
            validate_tool_schema(arguments, spec["input_schema"])
    canonical(obs)


def expected_reward(row, milestones):
    action, result = row["action"]["action_id"], row["feedback"]["result"]
    reward = -.02
    if row["feedback"]["error"]:
        reward -= 1
    elif action == "ask_variance": reward += .1
    elif action == "stop":
        before = {r["id"] for r in row["observation"]["evidence"] if r["kind"] in {"user_unavailable", "mock_tool_failure"}}
        ids = set(row["action"]["arguments"]["evidence_ids"])
        reward += 10 if ids and ids.issubset(before) else -10
    else:
        key = "review_pass" if action == "review" and result.get("ready_for_review") else "alignment_pass" if action == "align_claim" and result.get("can_test_conditionally") else action if action in {"freeze", "verify_workflow", "reconcile", "analyze", "assess"} else None
        if key and key not in milestones:
            milestones.add(key); reward += .2
        if action == "report" and row["classification"] == "completed_mock_research_loop": reward += 10
    if row["classification"] == "decision_budget_exhausted": reward -= 2
    return reward
