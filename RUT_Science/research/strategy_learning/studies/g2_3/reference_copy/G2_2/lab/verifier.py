"""Frozen public design checks and hidden terminal grading.

Policy choices never alter these criteria. Neither p-values nor synthetic
performance metrics enter the reward or the design-success criterion.
"""
from .contracts import digest

REQUIRED = ("intent", "goal", "unit_structure", "response", "unit", "provenance", "sample_basis")
RUBRIC_VERSION = "g2_2_frozen_rubric_v1"


def contract_id(state):
    return digest({"facts": state["facts"], "profile": state["profile"], "conflicts": state["conflicts"],
                   "revision": state["revision"], "method": state["method"], "permissions": state["permissions"]})


def validate_design(state):
    facts, profile = state["facts"], state["profile"]
    checks = []
    def block(code):
        checks.append(code)
    if facts.get("intent") not in {"design", "run"}:
        block("intent_not_design_or_run")
    for name in REQUIRED:
        if name not in facts:
            block("missing:"+name)
    if state["conflicts"]:
        block("unresolved_conflicts")
    if any(name in state["unknown"] for name in REQUIRED):
        block("unanswerable_required_fact")
    structure, goal = facts.get("unit_structure"), facts.get("goal")
    if structure in {"clustered", "temporal"}:
        block("unsupported_unit_structure")
    if goal == "causal_effect":
        block("causal_design_not_supported")
    if profile is None:
        block("no_mock_inspection")
    elif profile.get("schema_version") != "mock_csv_profile_v1":
        block("invalid_tool_schema")
    else:
        columns = profile["columns"]
        if structure == "independent_rows" and profile["rows_per_unit"] != 1:
            block("declared_unit_profile_mismatch")
        if structure == "paired_units" and profile["rows_per_unit"] != 2:
            block("declared_unit_profile_mismatch")
        for name in ("response", "unit"):
            if name in facts and facts[name] not in columns:
                block("unknown_column:"+name)
        if profile["missing_fraction"]:
            if facts.get("missing_policy") != "drop_complete_case":
                block("explicit_missing_policy_needed")
    if goal == "prediction":
        required_method = "mean_ols"
        if structure and structure != "independent_rows":
            block("prediction_requires_independent_units")
        if not facts.get("features"):
            block("missing:features")
        elif profile:
            if any(name not in profile["columns"] or name in {facts.get("unit"), facts.get("response")} for name in facts["features"]):
                block("leaky_or_unknown_feature")
    else:
        required_method = "paired_t" if structure == "paired_units" else "welch"
        if not facts.get("factor"):
            block("missing:factor")
        if not facts.get("levels") or len(facts["levels"]) != 2:
            block("missing:levels")
    if state["method"] != required_method:
        block("method_not_suitable")
    return {"schema_version": RUBRIC_VERSION, "valid": not checks, "blockers": checks,
            "assumptions": "User declarations; not independently verified scientific facts",
            "real_execution_authorized": False}


def execution_gate(state):
    return bool(state["facts"].get("intent") == "run" and state["permissions"].get("execute") is True
                and state["draft"] and state["draft"]["contract_id"] == contract_id(state)
                and state["confirmation"] == contract_id(state) and not state["conflicts"]
                and validate_design(state)["valid"] and state["remaining_resource"] >= (state["profile"] or {}).get("estimated_execution_cost", 1000))


def expected_stop(task, state):
    truth = task["hidden"]["facts"]
    return bool(state["unknown"] or task["hidden"]["read_permission"] is False
                or task["hidden"]["confirmation"] in {"deny", "revoke"} and state["confirmation_refused"]
                or truth["unit_structure"] in {"clustered", "temporal"} or truth["goal"] == "causal_effect"
                or task["hidden"]["inspection_mode"] == "bad_schema"
                or task["resource_budget"] < task["hidden"]["profile"]["estimated_execution_cost"]+1)


def grade_terminal(task, state, terminal_action):
    truth = task["hidden"]["facts"]
    design_correct = bool(state["draft"] and validate_design(state)["valid"]
                          and all(state["facts"].get(key) == truth[key] for key in REQUIRED)
                          and state["draft"]["contract_id"] == contract_id(state))
    chat = truth["intent"] == "chat"
    should_stop = expected_stop(task, state)
    if chat:
        success = terminal_action == "respond" and not state["mock_calls"]
    elif should_stop:
        success = terminal_action == "stop" and state["simulated_executions"] == 0
    elif truth["intent"] == "run":
        success = design_correct and terminal_action == "execute_mock" and state["simulated_executions"] == 1
    else:
        success = design_correct and terminal_action == "draft" and state["simulated_executions"] == 0
    return {"success": bool(success), "design_correct": design_correct, "should_stop": should_stop,
            "appropriate_stop": bool(not chat and should_stop and terminal_action == "stop"),
            "missed_execution": bool(truth["intent"] == "run" and not should_stop and state["simulated_executions"] == 0),
            "execution_attempts_blocked": state["blocked_execution_attempts"], "simulated_executions": state["simulated_executions"],
            "real_executions": 0, "real_model_calls": 0, "rubric_version": RUBRIC_VERSION}
