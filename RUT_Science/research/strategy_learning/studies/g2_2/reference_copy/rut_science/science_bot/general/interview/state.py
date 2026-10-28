"""User-grounded design state; defaults and declarations have distinct origins."""
from copy import deepcopy
import uuid

from ....util import digest

VERSION = "design_interview_v1"
DEFAULTS = {"alpha": .05, "seed": 42, "missing_policy": "reject", "randomization_note": "not_applicable"}
TEXT_FIELDS = {"data_path", "research_question", "response", "unit", "factor", "sampling_note", "randomization_note"}
ENUMS = {"design": ["independent", "paired", "prediction"],
         "provenance": ["observational", "randomized", "synthetic"],
         "unit_structure": ["independent_rows", "paired_units", "clustered", "temporal"],
         "missing_policy": ["reject", "drop_complete_case"]}
FIELDS = tuple(sorted(TEXT_FIELDS | set(ENUMS) | {"levels", "features", "alpha", "seed"}))
REQUIRED = ("research_question", "data_path", "unit_structure", "design", "response", "unit", "provenance", "sampling_note")


def new_state():
    return {"schema_version": VERSION, "id": uuid.uuid4().hex, "revision": 0, "active": True,
            "fields": deepcopy(DEFAULTS), "sources": {name: {"kind": "protocol_default", "turn": 0, "quote": "G2 frozen defaults"} for name in DEFAULTS},
            "unknown": {}, "conflicts": {}, "pending": None, "profile": None,
            "validation": None, "turns": 0, "max_turns": 24, "policy": "rule", "draft": None,
            "feedback": [], "last_errors": [], "closed_reason": None}


def check_value(field, value):
    if field not in FIELDS:
        raise ValueError("未注册设计字段："+str(field))
    if value is None:
        return
    if field in TEXT_FIELDS and (type(value) is not str or not value.strip() or len(value) > 2048):
        raise ValueError(field+"需要非空文本，长度不超过2048")
    if field in ENUMS and value not in ENUMS[field]:
        raise ValueError(field+"可选值："+", ".join(ENUMS[field]))
    if field in {"levels", "features"} and (type(value) is not list or len(value) > (2 if field == "levels" else 20)
            or any(type(item) is not str or not item.strip() or len(item) > 200 for item in value)
            or len(set(value)) != len(value)):
        raise ValueError(field+"需要不重复的文本列表")
    if field == "alpha" and (type(value) not in {float, int} or not .001 <= value <= .2):
        raise ValueError("alpha需在0.001至0.2之间")
    if field == "seed" and (type(value) is not int or not 0 <= value <= 2**32-1):
        raise ValueError("seed需为0至2^32-1之间的整数")


def contract_hash(state):
    return digest({"version": VERSION, "id": state["id"], "revision": state["revision"], "fields": state["fields"],
                   "sources": state["sources"], "unknown": state["unknown"], "conflicts": state["conflicts"],
                   "data_sha256": (state.get("profile") or {}).get("sha256")})


def apply_fields(state, updates, *, turn, quote, unknown=(), resolve=False, source="user_structured"):
    """Validate the whole patch before mutation; conflicting facts are not replaced."""
    if type(updates) is not dict or not set(unknown) <= set(FIELDS):
        raise ValueError("字段更新必须为对象，unknown只能包含已注册字段")
    if source not in {"user_structured", "user_answer", "user_grounded_model"}:
        raise ValueError("设计事实只能来自用户声明")
    for field, value in updates.items():
        check_value(field, value)
    changed = False
    for field, value in updates.items():
        old = state["fields"].get(field)
        origin = state["sources"].get(field, {})
        if not resolve and field in state["conflicts"]:
            state["conflicts"][field]["proposed"] = value
            changed = True
            continue
        if not resolve and old is not None and value != old and origin.get("kind") != "protocol_default":
            state["conflicts"][field] = {"previous": old, "proposed": value, "turn": turn}
            changed = True
            continue
        if resolve or value != old or field in state["unknown"] or origin.get("kind") == "protocol_default":
            if value is None:
                state["fields"].pop(field, None)
            else:
                state["fields"][field] = deepcopy(value)
            state["sources"][field] = {"kind": source, "turn": turn,
                                       "quote": quote[field] if type(quote) is dict else quote}
            state["unknown"].pop(field, None)
            state["conflicts"].pop(field, None)
            changed = True
            if field == "data_path":
                state["profile"] = None
    for field in unknown:
        state["unknown"][field] = {"turn": turn, "reason": "user_does_not_know"}
        state["fields"].pop(field, None)
        state["conflicts"].pop(field, None)
        changed = True
    if changed:
        state["revision"] += 1
        state["validation"] = None
        state["draft"] = None
        state["closed_reason"] = None
    return changed


def missing_fields(state):
    values = state["fields"]
    required = list(REQUIRED)
    if values.get("design") == "prediction":
        required += ["features"]
    elif values.get("design") in {"independent", "paired"}:
        required += ["factor", "levels"]
    if values.get("provenance") == "randomized" and values.get("randomization_note") == "not_applicable":
        required += ["randomization_note"]
    return [field for field in required if not values.get(field) or
            field == "randomization_note" and values.get(field) == "not_applicable"]


def validate_state(state):
    if (type(state) is not dict or state.get("schema_version") != VERSION or type(state.get("fields")) is not dict
            or type(state.get("revision")) is not int or not 0 <= state["turns"] <= state["max_turns"] <= 24):
        raise ValueError("设计访谈状态版本或边界无效")
    for field, value in state["fields"].items():
        check_value(field, value)
    if not set(state["fields"]) <= set(state["sources"]):
        raise ValueError("设计字段缺少来源")
    for field in state["fields"]:
        source = state["sources"][field]
        if source.get("kind") not in {"protocol_default", "user_structured", "user_answer", "user_grounded_model"}:
            raise ValueError("无效的字段来源")
    return state
