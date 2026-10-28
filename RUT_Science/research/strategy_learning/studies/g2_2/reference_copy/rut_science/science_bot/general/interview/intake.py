"""Conservative local parsing and quote-grounded native extraction.

The model may extract declarations, never supply scientific defaults or choose
tools. Unmatched statements remain questions rather than guessed facts.
"""
import json
import re

from ..contracts import ToolSpec
from ..provider import _strict_json
from ..registry import _validate
from .state import FIELDS, ENUMS, check_value

ALIASES = {
    "design": {"独立两组": "independent", "独立组": "independent", "配对": "paired", "预测比较": "prediction"},
    "provenance": {"观察性": "observational", "观察数据": "observational", "随机分配": "randomized", "合成": "synthetic"},
    "unit_structure": {"每行是不同的独立单位": "independent_rows", "每行不同独立单位": "independent_rows",
                       "每行都是不同独立单位": "independent_rows", "同一单位两个条件": "paired_units",
                       "同一单位在两个条件下测量": "paired_units", "有聚类": "clustered", "时间依赖": "temporal"},
    "missing_policy": {"拒绝缺失": "reject", "完整案例删除": "drop_complete_case", "删除完整缺失单位": "drop_complete_case"},
}
LABELS = {"研究问题": "research_question", "数据路径": "data_path", "响应列": "response", "实验单位列": "unit",
          "因素列": "factor", "水平": "levels", "特征": "features", "来源": "provenance", "样本依据": "sampling_note",
          "随机化说明": "randomization_note", "单位关系": "unit_structure", "设计": "design"}


def value_for(field, text):
    text = text.strip().strip("。；;")
    if field in ALIASES and text in ALIASES[field]:
        return ALIASES[field][text]
    if field in {"features", "levels"}:
        try:
            value = _strict_json(text)
        except ValueError:
            value = [item.strip().strip("'\"") for item in re.split(r"[,，、]", text.strip("[]")) if item.strip()]
        return value
    if field in {"alpha", "seed"}:
        return _strict_json(text)
    return text.strip('"\'')


def local_extract(text, pending=None):
    """Return declarations plus exact evidence; never infer from CSV column names."""
    text = text.strip()
    if text.startswith("{"):
        updates = _strict_json(text)
        if type(updates) is not dict:
            raise ValueError("/answer 后需要字段JSON对象")
        for field, value in updates.items():
            check_value(field, value)
        return updates, {field: text for field in updates}, []
    if text in {"不知道", "不清楚", "unknown", "I don't know", "不确定"}:
        if pending and pending.get("field"):
            return {}, {}, [pending["field"]]
        raise ValueError("请明确哪个字段尚不清楚")
    if pending and pending.get("options"):
        for option in pending["options"]:
            if text in {str(option["number"]), option["value"]}:
                return {pending["field"]: option["value"]}, {pending["field"]: text}, []
    names = sorted(set(FIELDS) | set(LABELS), key=len, reverse=True)
    pattern = r"(?<![A-Za-z0-9_])("+"|".join(map(re.escape, names))+r")\s*[:：=]\s*"
    matches = list(re.finditer(pattern, text))
    updates, quotes = {}, {}
    for i, match in enumerate(matches):
        field = LABELS.get(match[1], match[1])
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        raw = text[match.end():end].strip().rstrip("，,；;。\n ")
        value = value_for(field, raw)
        check_value(field, value)
        if field in updates and updates[field] != value:
            raise ValueError("同一回复中字段值冲突："+field)
        updates[field], quotes[field] = value, text[match.start():end].strip()
    if updates:
        return updates, quotes, []
    if pending and pending.get("field"):
        field = pending["field"]
        # An explicit answer command grants only the pending slot. A concept
        # question is routed to general chat before this function is called.
        value = value_for(field, text)
        try:
            check_value(field, value)
        except ValueError:
            return {}, {}, []
        return {field: value}, {field: text}, []
    return {}, {}, []


def grounded(field, value, quote):
    """Accept literal values or an explicit, small semantic alias vocabulary."""
    if re.search(r"不知道|不确定|不是|并非|不独立|未随机|not\b|unknown|uncertain", quote, re.I):
        return False
    if value is None:
        return quote.strip().casefold() in {"null", "清除", "删除字段"}
    if field in ALIASES and any(alias in quote and target == value for alias, target in ALIASES[field].items()):
        return True
    values = value if type(value) is list else [value]
    for item in values:
        spelling = str(item)
        if re.fullmatch(r"[A-Za-z0-9_.-]+", spelling):
            if not re.search(r"(?<![A-Za-z0-9_])"+re.escape(spelling)+r"(?![A-Za-z0-9_])", quote, re.I):
                return False
        elif spelling not in quote:
            return False
    return True


EXTRACTION_SPEC = ToolSpec("record_design_fields", "Extract only explicit user declarations from this turn with exact quotes. Never infer source, independence, randomization, sample basis, column names or method. No execution or permissions. Omit absent fields; preserve uncertainty.",
    {"type": "object", "properties": {"updates": {"type": "array", "maxItems": len(FIELDS), "items": {
        "type": "object", "properties": {"field": {"type": "string", "enum": list(FIELDS)},
            "value_json": {"type": "string", "maxLength": 4096}, "quote": {"type": "string", "minLength": 1, "maxLength": 4096}},
        "required": ["field", "value_json", "quote"], "additionalProperties": False}}},
     "required": ["updates"], "additionalProperties": False}, domain="interview")


def model_extract(session, text):
    provider = session.provider()
    response = provider.complete([
        {"role": "system", "content": "将当前用户明确声明提取成record_design_fields调用。只提取可逐字引用的信息。"
         "design取independent/paired/prediction；provenance取observational/randomized/synthetic；"
         "unit_structure取independent_rows/paired_units/clustered/temporal。不得根据常识、CSV或历史推断。"
         "自由文本research_question和sampling_note必须原样摘录，不改写。缺失项不提取，不输出实验结果。"},
        {"role": "user", "content": text}], tools=[EXTRACTION_SPEC.provider_schema()], role="design_intake")
    try:
        if session.cancel_requested.is_set() or session.pause_requested.is_set():
            raise ValueError("访谈已暂停")
        calls = response["tool_calls"]
        if len(calls) != 1 or calls[0]["name"] != EXTRACTION_SPEC.name:
            raise ValueError("字段提取必须为一个受限工具提议")
        args = calls[0]["arguments"]
        _validate(args, EXTRACTION_SPEC.input_schema)
        updates, quotes = {}, {}
        for item in args["updates"]:
            field, quote = item["field"], item["quote"]
            value = _strict_json(item["value_json"])
            check_value(field, value)
            if quote not in text or not grounded(field, value, quote) or field in updates:
                raise ValueError("字段提议缺少当前用户原文依据，或字段重复")
            updates[field], quotes[field] = value, quote
        provider.mark_validation("accepted" if updates else "needs_input")
        return updates, quotes, []
    except (ValueError, TypeError, KeyError):
        provider.mark_validation("rejected", "UngroundedDesignFields")
        raise
