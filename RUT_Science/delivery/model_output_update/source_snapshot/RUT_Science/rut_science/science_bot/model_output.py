"""Read-only model output history, separate from scientific evidence and budgets."""
from functools import wraps
import json
from pathlib import Path
import re

from ..util import digest

ROLE_LABELS = {
    "intake_v2": "需求理解",
    "candidate_generator_v1": "候选提议",
    "llm_selector_v1": "LLM 行动选择",
    "report_explainer_v1": "报告解释",
}
STATUS_LABELS = {
    "pending_validation": "模型提议 · 待宿主校验",
    "accepted": "宿主契约检查通过",
    "needs_input": "需要补充信息 · 尚未授权执行",
    "rejected": "宿主拒绝 · 未采用此输出",
    "schema_rejected": "输出格式错误 · 未采用此输出",
    "failed": "模型调用失败 · 无可展示的解析结果",
    "legacy_unverified": "历史输出 · 未记录宿主校验状态",
}
MAX_OUTPUT_BYTES = 512 * 1024


def _read_json(path, folder):
    # Only numbered response/status files are read; request bodies and headers
    # never participate in terminal replay. Refuse redirected history files.
    if path.resolve() != path or path.parent.resolve() != folder.resolve():
        raise ValueError("Model output path must stay in the session history")
    if path.stat().st_size > MAX_OUTPUT_BYTES:
        raise ValueError("Model output exceeds the display size limit")
    return json.loads(path.read_text(encoding="utf-8"))


def read_output(session_folder, selector="latest"):
    """Return a saved call or an index without writes, events or network access."""
    folder = Path(session_folder).resolve() / "model_calls"
    if folder.resolve() != folder:
        raise ValueError("Model output history must not be redirected")
    selector = str(selector).strip() or "latest"
    if selector not in {"latest", "list"} and not re.fullmatch(r"[0-9]{1,9}", selector):
        raise ValueError("Usage: /model-output [list|positive call number]")
    if selector not in {"latest", "list"} and int(selector) < 1:
        raise ValueError("Call number must be positive")
    indices = sorted({int(p.name.split("_", 1)[0]) for p in folder.glob("*.json")
                      if re.fullmatch(r"[0-9]{4,9}_(?:response|status)\.json", p.name)})
    if selector == "list":
        rows = []
        for index in indices:
            item = read_output(session_folder, str(index))
            rows.append({k: item[k] for k in ("request_index", "role", "model", "status", "output_ref")})
        return {"calls": rows}
    if not indices and selector == "latest":
        return None
    index = indices[-1] if selector == "latest" else int(selector)
    if index not in indices:
        raise ValueError("No saved model output for that call number")
    response_path = folder / f"{index:04d}_response.json"
    status_path = folder / f"{index:04d}_status.json"
    response = _read_json(response_path, folder) if response_path.exists() else None
    status = _read_json(status_path, folder) if status_path.exists() else {}
    if not isinstance(status, dict) or (response is not None and not isinstance(response, dict)):
        raise ValueError("Invalid saved model output metadata")
    if response is not None and ("response" not in response or
                                 response.get("response_hash") != digest(response["response"])):
        raise ValueError("Saved model output hash mismatch")
    if response is not None and status.get("response_hash", response["response_hash"]) != response["response_hash"]:
        raise ValueError("Model output status does not match the saved response")
    role = (response or status).get("role", "unknown")
    return {"request_index": index, "role": role,
            "model": (response or status).get("model", "未记录"),
            "status": status.get("status", "legacy_unverified"),
            "error_type": status.get("error_type"),
            "output_ref": f"model_calls/{response_path.name if response is not None else status_path.name}",
            "response": response["response"] if response is not None else None}


def validates_output(role):
    """Mark only a newly returned, schema-valid call after host validation.

    Legacy/mocked language components need no synthetic model output records.
    A format/service failure keeps its more specific status from ScienceLLM.call.
    """
    def decorate(function):
        @wraps(function)
        def wrapped(owner, *args, **kwargs):
            llm = getattr(owner, "llm", owner)
            previous = llm.last_output
            try:
                result = function(owner, *args, **kwargs)
            except Exception as exc:
                llm.complete_validation(role, previous, "rejected", type(exc).__name__)
                raise
            status = "needs_input" if isinstance(result, dict) and "questions" in result else "accepted"
            llm.complete_validation(role, previous, status)
            return result
        return wrapped
    return decorate
