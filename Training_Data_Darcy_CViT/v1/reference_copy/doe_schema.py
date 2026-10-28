"""Closed DOE protocol and JSON-schema subset used by the validator."""
import math
import re

VERSION = "doe_contract_v1"
FAMILIES = ("crd_two_arm", "rcbd_two_arm", "factorial_2x2")
CLAIM_PATHS = ("/question", "/factors", "/response", "/experimental_unit", "/blocks", "/assumptions", "/analysis", "/resources")


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def string(*, values=None, limit=2000):
    value = {"type": "string", "minLength": 1, "maxLength": limit}
    if values is not None:
        value["enum"] = list(values)
    return value


def number(low, high):
    return {"type": "number", "minimum": low, "maximum": high}


def integer(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


def array(items, low=0, high=1000, unique=False):
    value = {"type": "array", "items": items, "minItems": low, "maxItems": high}
    if unique:
        value["uniqueItems"] = True
    return value


FACTOR = obj({"name": {**string(limit=40), "pattern": "[A-Za-z][A-Za-z0-9_]*"},
              "levels": array(string(limit=80), 2, 2, True)})
ANALYSIS = obj({"model": string(values=("two_arm", "additive_blocks", "full_factorial", "blocked_full_factorial")),
    "primary_term": string(limit=100), "alpha": number(.001, .2), "minimum_effect": number(1e-8, 1e6),
    "sigma": number(1e-8, 1e6), "target_power": number(.5, .9999),
    "multiplicity": string(values=("single_primary",)), "missing_policy": string(values=("stop_and_review",)),
    "decision_rule": string(values=("two_sided_t_ci_practical_relevance_separate",))})
CONTRACT_SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", **obj({
    "schema_version": string(values=(VERSION,)), "request_hash": {**string(limit=64), "pattern": "[a-f0-9]{64}"},
    "revision": integer(1, 1000), "question": string(), "family": string(values=FAMILIES),
    "factors": array(FACTOR, 1, 2), "response": obj({"name": string(), "unit": string(), "direction": string(values=("lower", "higher"))}),
    "experimental_unit": obj({"definition": string(), "independence_basis": string(), "measurement_repeats": integer(1, 100)}),
    "blocks": array(string(limit=50), 0, 100, True), "replicates": integer(1, 100),
    "assumptions": array(string(values=("normal_iid_errors", "constant_error_variance", "no_treatment_block_interaction")), 2, 3, True),
    "randomization": obj({"seed": integer(0, 2**31-1), "algorithm": string(values=("shuffle_v1",))}),
    "analysis": ANALYSIS, "resources": obj({"per_run": number(.001, 1e6), "budget": number(.001, 1e6)}),
    "provenance": array(obj({"path": string(values=CLAIM_PATHS), "evidence_id": string(limit=80)}), 8, 8),
    "run_plan": array(obj({"run": integer(1, 1000), "unit_id": string(limit=100), "block": string(limit=50),
                           "levels": array(string(limit=80), 1, 2)}), 4, 1000)})}
REQUEST_SCHEMA = obj({"schema_version": string(values=("doe_request_v1",)), "scope": string(values=("design_only",)),
    "requested_family": string(limit=100), "execution_permission": string(values=("denied",)),
    "evidence": array(obj({"id": string(limit=80), "path": string(values=(*CLAIM_PATHS, "/family")),
        "value": {}, "status": string(values=("provided", "unanswered", "unavailable")),
        "source": string(values=("synthetic_fixture", "user_declaration", "pilot_estimate")), "reference": string()}), 9, 9)})


def errors(value, schema, path="$"):
    """Implements exactly the keywords used above; not a general JSON-schema engine."""
    checks = {"object": lambda v: type(v) is dict, "array": lambda v: type(v) is list,
        "string": lambda v: type(v) is str, "integer": lambda v: type(v) is int,
        "number": lambda v: type(v) in (int, float) and math.isfinite(v)}
    kind = schema.get("type")
    if kind and not checks[kind](value):
        return [path+": invalid "+kind]
    result = []
    if "enum" in schema and value not in schema["enum"]:
        result.append(path+": unsupported value")
    if kind == "object":
        props = schema["properties"]
        if set(value) != set(schema["required"]):
            result.append(path+": missing or extra keys")
        for key in set(value)&set(props):
            result += errors(value[key], props[key], path+"/"+key)
    elif kind == "array":
        if not schema["minItems"] <= len(value) <= schema["maxItems"]:
            result.append(path+": invalid item count")
        if schema.get("uniqueItems") and len({repr(v) for v in value}) != len(value):
            result.append(path+": duplicate values")
        for i, item in enumerate(value):
            result += errors(item, schema["items"], path+"/"+str(i))
    elif kind == "string":
        if not schema["minLength"] <= len(value) <= schema["maxLength"]:
            result.append(path+": invalid length")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            result.append(path+": invalid pattern")
    elif kind in {"integer", "number"} and not schema["minimum"] <= value <= schema["maximum"]:
        result.append(path+": outside bounds")
    return result


def request_errors(request):
    result = errors(request, REQUEST_SCHEMA)
    if result:
        return result
    evidence = request["evidence"]
    if len({r["id"] for r in evidence}) != len(evidence) or {r["path"] for r in evidence} != set((*CLAIM_PATHS, "/family")):
        result.append("Evidence ids/paths must be unique and cover the request")
    for row in evidence:
        if row["status"] != "provided" and row["value"] is not None:
            result.append("Unknown facts cannot carry an invented value")
    scope = next((r for r in evidence if r["path"] == "/family"), None)
    if scope is None or scope["value"] != request["requested_family"] or scope["status"] != "provided":
        result.append("Requested scope needs an immutable public evidence record")
    return result
