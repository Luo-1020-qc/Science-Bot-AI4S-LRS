"""A frozen bilingual development rubric, with human review still required."""
import re

RUBRIC_VERSION = "bilingual_development_v2"
CONCEPTS = {
    "data": ("数据", "资料", "数据集", "dataset", "data set", "data source"),
    "target": ("目标", "性质", "指标", "预测什么", "预测哪", "target", "property", "predict"),
    "train": ("训练", "拟合", "建模", "train", "fit", "model"),
    "conflict": ("冲突", "矛盾", "无法同时", "不能同时", "不兼容", "尚未", "未训练", "不可能", "无法提供", "无法给出",
                 "conflict", "contradict", "incompatible", "cannot", "can't", "without training"),
    "question": ("?", "？", "请确认", "请选择", "请提供", "请指定", "请问", "是否", "需要您", "需要你", "能否", "提供一下",
                 "please confirm", "please provide", "please specify", "which", "could you", "would you"),
}


def contains(text: str, concept: str) -> bool:
    lowered = text.casefold()
    return any(word in lowered for word in CONCEPTS[concept])


def check_clarification(content: str, behavior: str) -> dict:
    relevant = ((contains(content, "data") and contains(content, "target")) if behavior == "missing_critical_context"
                else contains(content, "train") and contains(content, "conflict"))
    unsupported_numeric_claim = bool(re.search(r"(?:MAE|测试误差|平均绝对误差)\s*(?:为|是|=|:|：|is)\s*\d", content, re.I))
    return {"relevant": relevant, "requests_resolution": contains(content, "question"),
            "no_invented_metric": not unsupported_numeric_claim, "rubric_version": RUBRIC_VERSION}
