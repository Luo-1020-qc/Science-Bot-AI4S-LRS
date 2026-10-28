"""Host-validated tools; model proposals never grant file access or budget."""
from copy import deepcopy
import math
from pathlib import Path

from ..workspace import Workspace
from .contracts import ToolSpec


def _validate(value, schema, label="arguments"):
    """Validate the deliberately small JSON-schema subset used by G1 tools."""
    kind = schema.get("type")
    valid = {"object": lambda v: type(v) is dict, "array": lambda v: type(v) is list,
             "string": lambda v: type(v) is str, "integer": lambda v: type(v) is int,
             "number": lambda v: type(v) in {int, float} and math.isfinite(v),
             "boolean": lambda v: type(v) is bool, "null": lambda v: v is None}
    if kind is not None and (kind not in valid or not valid[kind](value)):
        raise ValueError(f"Invalid {label}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"Invalid {label}: unsupported value")
    if kind == "object":
        properties = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", [])):
            raise ValueError(f"Invalid {label}: missing required parameter")
        if schema.get("additionalProperties") is False and any(key not in properties for key in value):
            raise ValueError(f"Invalid {label}: unknown parameter")
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], f"{label}.{key}")
    if kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", math.inf):
            raise ValueError(f"Invalid {label}: item count")
        for item in value:
            _validate(item, schema.get("items", {}), label+"[]")
    if kind == "string" and not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", math.inf):
        raise ValueError(f"Invalid {label}: string length")
    if kind in {"integer", "number"} and not schema.get("minimum", -math.inf) <= value <= schema.get("maximum", math.inf):
        raise ValueError(f"Invalid {label}: outside allowed range")
    if kind in {"integer", "number"} and "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
        raise ValueError(f"Invalid {label}: outside allowed range")


def _workspace(context):
    workspace = context.get("workspace")
    if not isinstance(workspace, Workspace):
        raise ValueError("Select a project workspace before using project tools")
    return workspace


def _relative(workspace, value):
    """Normalize spelling, but never accept traversal or an outside reference."""
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError("Provide an explicitly selected project path")
    value = str(value).strip().strip('"\'').replace("\\", "/")
    path = Path(value)
    if ".." in path.parts:
        raise ValueError("Parent traversal is not a project input reference")
    if path.is_absolute():
        try:
            path = path.relative_to(workspace.root)
        except ValueError as exc:
            raise ValueError("File is outside this workspace") from exc
    # Workspace.resolve_file checks excluded directories, sensitive files and
    # resolved link/junction targets. Keep the selected spelling for permission.
    workspace.resolve_file(path)
    return path.as_posix()


def _project_list(arguments, context):
    workspace = _workspace(context)
    pattern = arguments.get("pattern", "*")
    if any(char in pattern for char in "\x00\r\n") or ".." in Path(pattern).parts:
        raise ValueError("Invalid project-list pattern")
    return workspace.files(pattern, limit=arguments.get("limit", 100))


def _project_read(arguments, context):
    workspace = _workspace(context)
    selected = _relative(workspace, arguments["path"])
    allowed = context.get("allowed_paths", ())
    if not isinstance(allowed, (list, tuple, set, frozenset)):
        raise ValueError("Invalid host file scope")
    normalized = set()
    for path in allowed:
        try:
            normalized.add(_relative(workspace, path))
        except ValueError:
            continue
    if selected not in normalized:
        raise ValueError("File content was not explicitly selected by the user")
    start = arguments.get("start_line", 1)
    end = arguments.get("end_line", start+199)
    if end < start or end-start+1 > 400:
        raise ValueError("Read a contiguous range of at most 400 lines")
    cap = context.get("max_read_bytes", 32768)
    remaining = context.get("remaining_read_bytes", cap)
    if type(cap) is not int or type(remaining) is not int or not 0 <= remaining <= cap <= 128*1024:
        raise ValueError("Invalid host project-context budget")
    result = workspace.read_text(selected)
    lines = result["text"].splitlines(keepends=True)
    if start > max(1, len(lines)):
        raise ValueError("Requested start line is beyond this file")
    end = min(end, max(1, len(lines)))
    snippet = "".join(lines[start-1:end])
    used = len(snippet.encode("utf-8"))
    if used > remaining:
        raise ValueError("Selected file range exceeds the remaining project-context byte budget")
    ref = f"{result['path']}:L{start}-L{end}#{result['sha256'][:12]}"
    output = {"path": result["path"], "sha256": result["sha256"], "text": snippet,
              "start_line": start, "end_line": end, "line_numbers": list(range(start, end+1)) if lines else [],
              "bytes": used, "file_bytes": result["bytes"], "total_lines": len(lines),
              "truncated": start > 1 or end < len(lines), "evidence_ref": ref}
    context["remaining_read_bytes"] = remaining-used
    return output


def _prepare_numeric(arguments, context):
    if context.get("numeric_dataset") != arguments["dataset"]:
        raise ValueError("Numeric preparation requires an explicitly routed dataset")
    callback = context.get("prepare_numeric")
    if not callable(callback):
        raise ValueError("Numeric engine adapter is unavailable")
    return callback(deepcopy(arguments))


class ToolRegistry:
    """Explicitly registered handlers; persistence/idempotence belongs to the caller."""
    def __init__(self, *, builtins=True):
        self._tools = {}
        if builtins:
            self.register(ToolSpec("project_list",
                "List project file names and byte sizes only; never reads content. Use before selecting a file. "
                "Cannot list excluded credentials, dependencies or outside paths.",
                {"type": "object", "properties": {"pattern": {"type": "string", "minLength": 1, "maxLength": 200},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, "additionalProperties": False},
                {"type": "object", "properties": {
                 "files": {"type": "array", "items": {"type": "object", "properties": {
                     "path": {"type": "string"}, "bytes": {"type": "integer", "minimum": 0}},
                     "required": ["path", "bytes"], "additionalProperties": False}},
                 "truncated": {"type": "boolean"}, "scanned": {"type": "integer", "minimum": 0},
                 "pattern": {"type": "string"}}, "required": ["files", "truncated", "scanned", "pattern"],
                 "additionalProperties": False},
                preconditions=("workspace_selected",), resource_estimate={"max_scan_entries": 20000}), _project_list)
            self.register(ToolSpec("project_read",
                "Read a UTF-8 line range from a file explicitly selected by the user; returns SHA-256 and line evidence. "
                "Listing a file does not authorize its content. Cannot read credentials, binary, outside files or run code.",
                {"type": "object", "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 2048},
                 "start_line": {"type": "integer", "minimum": 1, "maximum": 1000000},
                 "end_line": {"type": "integer", "minimum": 1, "maximum": 1000000}},
                 "required": ["path"], "additionalProperties": False},
                {"type": "object", "properties": {
                 "path": {"type": "string"}, "sha256": {"type": "string", "minLength": 64, "maxLength": 64},
                 "text": {"type": "string"}, "start_line": {"type": "integer", "minimum": 1},
                 "end_line": {"type": "integer", "minimum": 1}, "line_numbers": {"type": "array", "items": {"type": "integer"}},
                 "bytes": {"type": "integer", "minimum": 0}, "file_bytes": {"type": "integer", "minimum": 0},
                 "total_lines": {"type": "integer", "minimum": 0}, "truncated": {"type": "boolean"},
                 "evidence_ref": {"type": "string"}}, "required": ["path", "sha256", "text", "start_line", "end_line",
                     "line_numbers", "bytes", "file_bytes", "total_lines", "truncated", "evidence_ref"], "additionalProperties": False},
                preconditions=("workspace_selected", "user_selected_file", "context_budget_available"),
                resource_estimate={"default_context_bytes": 32768, "max_lines_per_read": 400}), _project_read)
            self.register(ToolSpec("prepare_numeric_experiment",
                "Prepare the existing generated/Darcy mean-ridge experiment draft for a user's explicit numeric task. "
                "Does not run a job; execution uses the existing specification confirmation workflow. "
                "Cannot introduce new datasets or methods.",
                {"type": "object", "properties": {
                 "dataset": {"type": "string", "enum": ["generated", "darcy"]},
                 "budget": {"type": "integer", "minimum": 1, "maximum": 100000},
                 "quality_threshold": {"type": "number", "exclusiveMinimum": 0, "maximum": 10}},
                 "required": ["dataset", "budget", "quality_threshold"], "additionalProperties": False},
                domain="numeric", read_only=False, preconditions=("explicit_numeric_task", "numeric_adapter_available"),
                resource_estimate={"preparation_compute_units": 0}), _prepare_numeric)

    def register(self, spec, handler):
        if not isinstance(spec, ToolSpec) or not callable(handler):
            raise ValueError("Register a ToolSpec and a callable host handler")
        if spec.name in self._tools:
            raise ValueError("Tool is already registered")
        self._tools[spec.name] = (deepcopy(spec), handler)
        return self

    def specs(self):
        return [spec.to_dict() for spec, _ in self._tools.values()]

    def schemas(self):
        return [spec.provider_schema() for spec, _ in self._tools.values()]

    provider_tools = schemas

    def execute(self, name, arguments, context):
        if not isinstance(name, str) or name not in self._tools:
            raise ValueError("Unknown or unavailable registered tool")
        if type(context) is not dict:
            raise ValueError("Tool context must be supplied by the host")
        spec, handler = self._tools[name]
        _validate(arguments, spec.input_schema)
        result = handler(deepcopy(arguments), context)
        _validate(result, spec.output_schema, "tool result")
        return result

