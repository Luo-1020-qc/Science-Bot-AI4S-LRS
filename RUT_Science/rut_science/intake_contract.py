"""Public catalog, provenance-aware draft building and trusted confirmation."""
import copy
import json
import math
from pathlib import Path
import re

from .environment import make_initial_state
from .research_spec import ResearchSpec
from .util import digest

FIELDS = {"dataset_name", "target", "model", "train_fraction", "split_seed", "alpha", "max_train_calls", "max_test_calls"}
ALIASES = {
    "dataset_name": {"Darcy-Published-CPU-v1": ("darcy",), "Materials-A": ("materials-a", "材料a"),
                     "Materials-B": ("materials-b", "材料b"), "Materials-C": ("materials-c", "材料c")},
    "target": {"pressure_field": ("pressure_field", "pressure", "压力"), "conductivity": ("conductivity", "电导率"), "modulus": ("modulus", "模量")},
    "model": {"ridge_field": ("ridge_field", "岭回归", "ridge"), "mean_field": ("mean_field", "均值", "mean"),
              "linear": ("linear", "线性"), "mean": ("mean", "均值"),
              "validation_select": ("validation_select", "验证集择优", "择优", "比较基线", "自动选择", "compare")}}
NUMERIC_PATTERNS = {"split_seed": r"(?:seed|种子)\s*[:：=]?\s*(\d+)",
    "alpha": r"(?:alpha|正则(?:化)?系数)\s*[:：=]?\s*([0-9.]+)",
    "train_fraction": r"(?:训练比例|训练集比例|train_fraction)\s*[:：=]?\s*([0-9.]+)\s*(%)?",
    "max_train_calls": r"(?:最多训练|训练次数|拟合次数|max_train_calls)\s*[:：=]?\s*(\d+)",
    "max_test_calls": r"(?:测试次数|最多测试|max_test_calls)\s*[:：=]?\s*(\d+)"}


def build_catalog(data: Path | None = None):
    entries = {}
    for dataset in make_initial_state()["datasets"].values():
        entries[dataset["name"]] = {"dataset_name": dataset["name"], "dataset_hash": digest(dataset), "target": dataset["target"],
            "unit": dataset["unit"], "workflow": "synthetic", "data": None, "models": ["linear", "mean"],
            "defaults": {"model": "linear", "train_fraction": 0.6, "split_seed": 11, "max_train_calls": 1, "max_test_calls": 1},
            "split_policy": "random_three_way", "metric": "MAE"}
    if data is not None and (Path(data)/"dataset.json").exists():
        metadata = json.loads((Path(data)/"dataset.json").read_text(encoding="utf-8-sig"))
        identity = metadata.pop("dataset_hash")
        if digest(metadata) != identity:
            raise ValueError("Darcy catalog manifest hash mismatch")
        entries[metadata["name"]] = {"dataset_name": metadata["name"], "dataset_hash": identity, "target": "pressure_field", "unit": "nondimensional",
            "workflow": "darcy", "data": str(Path(data).resolve()), "models": ["ridge_field", "mean_field", "validation_select"],
            "defaults": {"model": "ridge_field", "train_fraction": 0.8, "split_seed": 2026, "alpha": 1.0, "max_train_calls": 1, "max_test_calls": 1},
            "split_policy": "published_train_test", "metric": "mean_relative_l2"}
    return entries


def is_negated(text, position):
    return bool(re.search(r"不要|不用|不使用|不是|禁止|不能|not\s|no\s", text[max(0, position-8):position], re.I))


def evidence_matches(field, value, evidence, text):
    if not isinstance(evidence, str) or not evidence or evidence not in text:
        return False
    if field in ALIASES:
        for alias in ALIASES[field].get(value, (str(value).lower(),)):
            for snippet in re.finditer(re.escape(evidence), text):
                for match in re.finditer(re.escape(alias), evidence, re.I):
                    if not is_negated(text, snippet.start()+match.start()):
                        return True
        return False
    if field in NUMERIC_PATTERNS:
        for match in re.finditer(NUMERIC_PATTERNS[field], text, re.I):
            parsed = float(match.group(1))
            if field == "train_fraction" and match.group(2):
                parsed /= 100
            if match.group(0) in evidence and parsed == value and not is_negated(text, match.start()):
                return True
    return False


def offline_extract(text, current=None):
    """Finite bilingual control parser, not an open-domain language model."""
    fields = {}
    for field, values in ALIASES.items():
        found = []
        for value, aliases in values.items():
            for alias in aliases:
                match = re.search(re.escape(alias), text, re.I)
                if match and not is_negated(text, match.start()):
                    found.append((value, match.group(0)))
                    break
        if field == "model" and any(v == "validation_select" for v, _ in found):
            found = [(v, e) for v, e in found if v == "validation_select"]
        if field == "model":
            dataset = fields.get("dataset_name", {}).get("value") or (current or {}).get("dataset_name", {}).get("value")
            darcy = dataset == "Darcy-Published-CPU-v1"
            found = [(v, e) for v, e in found if v not in ({"linear", "mean"} if darcy else {"ridge_field", "mean_field", "validation_select"})]
        if len(found) == 1:
            value, evidence = found[0]
            fields[field] = {"value": value, "evidence": evidence}
        elif len(found) > 1:
            fields[field] = {"value": "__ambiguous__", "evidence": text}
    for field, pattern in NUMERIC_PATTERNS.items():
        found = list(re.finditer(pattern, text, re.I))
        parsed = []
        for match in found:
            value = float(match.group(1)) if field in {"alpha", "train_fraction"} else int(match.group(1))
            if field == "train_fraction" and match.group(2):
                value /= 100
            parsed.append(value)
            fields[field] = {"value": value, "evidence": match.group(0)}
        if len(set(parsed)) > 1:
            fields[field] = {"value": "__ambiguous__", "evidence": text}
    return {"fields": fields, "questions": [], "conflicts": []}


def apply_extraction(current, extraction, text, turn):
    if type(extraction) is not dict or set(extraction) != {"fields", "questions", "conflicts"} or type(extraction["fields"]) is not dict:
        raise ValueError("Extractor must return only fields, questions, conflicts; it cannot confirm or execute")
    if not set(extraction["fields"]) <= FIELDS or any(type(extraction[k]) is not list or any(type(x) is not str for x in extraction[k]) for k in ("questions", "conflicts")):
        raise ValueError("Invalid extractor fields or questions")
    updated = copy.deepcopy(current)
    for field, item in extraction["fields"].items():
        if type(item) is not dict or set(item) != {"value", "evidence"} or type(item["evidence"]) is not str:
            raise ValueError("Extracted fields require a value and evidence")
        value = item["value"]
        if not (type(value) is str or type(value) in (int, float) and math.isfinite(value)):
            raise ValueError("Extracted values must be strings or finite numbers")
        explicit = evidence_matches(field, value, item["evidence"], text)
        if not explicit and updated.get(field, {}).get("origin") == "user":
            continue
        updated[field] = {"value": value, "origin": "user" if explicit else "model_suggestion",
                          "evidence": item["evidence"] if explicit else "", "turn": turn}
    return updated


def update_constraints(constraints, text):
    constraints = dict(constraints)
    if re.search(r"禁止训练|不要训练|不允许训练|不能训练|不训练|no training", text, re.I):
        constraints["training_allowed"] = False
    elif re.search(r"允许训练|可以训练|同意训练|allow training", text, re.I):
        constraints["training_allowed"] = True
    if re.search(r"禁止测试|不要测试|不允许测试|no test", text, re.I):
        constraints["testing_allowed"] = False
    elif re.search(r"允许测试|可以测试|同意测试|allow test", text, re.I):
        constraints["testing_allowed"] = True
    return constraints


def build_draft(fields, constraints, catalog, version, execution_policy):
    issues = []
    name = fields.get("dataset_name", {}).get("value")
    if name not in catalog or fields["dataset_name"].get("origin") != "user":
        return None, ["请指定可用数据集：" + "、".join(catalog)]
    entry = catalog[name]
    target = fields.get("target", {}).get("value")
    if not target or fields["target"].get("origin") != "user":
        return None, [f"请确认预测目标，例如该数据支持 {entry['target']}。"]
    if target != entry["target"]:
        issues.append(f"数据 {name} 仅支持目标 {entry['target']}，请修正目标或数据。")
    if constraints.get("training_allowed") is False:
        issues.append("当前协议需要拟合新模型，但你禁止训练；请明确是否允许训练。")
    if constraints.get("testing_allowed") is False:
        issues.append("当前报告协议要求一次封存测试，但你禁止测试；请明确是否允许测试。")
    values = dict(entry["defaults"])
    provenance = {key: {"origin": "system_default", "value": value} for key, value in values.items()}
    for key, record in fields.items():
        if key in FIELDS:
            values[key] = record["value"]
            provenance[key] = copy.deepcopy(record)
    method = values["model"]
    required_fits = 2 if method == "validation_select" else 1
    if "max_train_calls" not in fields:
        values["max_train_calls"] = required_fits
        provenance["max_train_calls"] = {"origin": "method_contract", "value": required_fits}
    if method not in entry["models"]:
        issues.append("不支持或有歧义的方法；可选：" + "、".join(entry["models"]))
    try:
        spec = ResearchSpec(name, entry["dataset_hash"], target, entry["unit"], method, values["train_fraction"], values["split_seed"],
            split_policy=entry["split_policy"], metric=entry["metric"], max_train_calls=values["max_train_calls"],
            max_test_calls=values["max_test_calls"], model_parameters={"alpha": values["alpha"]} if entry["workflow"] == "darcy" else {})
    except (ValueError, KeyError, TypeError) as exc:
        issues.append("研究规格未通过校验：" + str(exc))
        spec = None
    if issues or spec is None:
        return None, issues
    draft = {"version": version, "spec": spec.to_dict(), "provenance": provenance, "execution_policy": copy.deepcopy(execution_policy),
             "workflow": entry["workflow"], "data": entry["data"]}
    draft["draft_hash"] = digest(draft)
    return draft, []


def make_receipt(draft, command, actor, turn):
    if actor not in {"terminal_user", "scripted_operator"}:
        raise ValueError("Only a trusted operator input may confirm a specification")
    parts = command.strip().split()
    if command.strip() not in {"确认", "确认执行", "/confirm"} and not (len(parts) == 2 and parts[0] in {"确认", "/confirm"} and parts[1] == draft["draft_hash"]):
        raise ValueError("Confirmation must bind the displayed current draft hash")
    receipt = {"schema_version": "intake_confirmation_v1", "draft": copy.deepcopy(draft), "spec_hash": ResearchSpec(**draft["spec"]).spec_hash,
               "bound_draft_hash": draft["draft_hash"], "actor": actor, "command": command.strip(), "turn": turn}
    receipt["confirmation_hash"] = digest(receipt)
    validate_receipt(receipt, ResearchSpec(**draft["spec"]))
    return receipt


def validate_receipt(receipt, spec):
    if type(receipt) is not dict:
        raise ValueError("Invalid confirmation receipt")
    expected = {"schema_version", "draft", "spec_hash", "bound_draft_hash", "actor", "command", "turn", "confirmation_hash"}
    if set(receipt) != expected or receipt["schema_version"] != "intake_confirmation_v1" or receipt["actor"] not in {"terminal_user", "scripted_operator"}:
        raise ValueError("Confirmation receipt was not issued by the trusted input boundary")
    if type(receipt["turn"]) is not int or receipt["turn"] < 0:
        raise ValueError("Confirmation requires a concrete operator turn")
    payload = {k: v for k, v in receipt.items() if k != "confirmation_hash"}
    draft = dict(receipt["draft"])
    draft_hash = draft.pop("draft_hash")
    if (digest(payload) != receipt["confirmation_hash"] or digest(draft) != draft_hash or draft_hash != receipt["bound_draft_hash"]
            or receipt["spec_hash"] != spec.spec_hash or draft["spec"] != spec.to_dict()):
        raise ValueError("Confirmation receipt does not bind the exact specification and execution policy")
    command = receipt["command"]
    if command not in {"确认", "确认执行", "/confirm", f"确认 {draft_hash}", f"/confirm {draft_hash}"}:
        raise ValueError("Invalid confirmation command")
    return True
