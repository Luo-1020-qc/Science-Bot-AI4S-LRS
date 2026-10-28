"""Project identity, isolated state and bounded project-file access.

Opening a workspace never changes cwd, model credentials, datasets or policy
actions. Text reads stay local; this module never sends files to a model.
"""
from fnmatch import fnmatch
import hashlib
import json
import os
from pathlib import Path
import uuid
from ..util import write_json

SCHEMA = "science_workspace_v1"
READ_POLICY = "project_text_v1"
EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".sciencebot",
                 ".aws", ".ssh", ".codex", ".agents", ".pytest_cache", ".mypy_cache", ".ipynb_checkpoints"}
SENSITIVE_FILES = {"api_key_agent.json", ".local_token", "credentials", "credentials.json", "secrets.toml"}
MAX_TEXT_BYTES = 128*1024


def _root(path):
    try:
        root = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Workspace must be an existing project directory") from exc
    if not root.is_dir():
        raise ValueError("Workspace must be a directory")
    return root


def _excluded(relative):
    return (any(p.casefold() in EXCLUDED_DIRS for p in relative.parts)
            or relative.name.casefold() in SENSITIVE_FILES
            or relative.name.casefold().startswith((".env", "id_rsa", "id_ed25519"))
            or relative.suffix.casefold() in {".pem", ".key", ".p12", ".pfx"})


class Workspace:
    def __init__(self, root, binding):
        self.root, self.binding = root, binding
        self.state_dir = root/".sciencebot"
        self.sessions_dir = self.state_dir/"sessions"

    @classmethod
    def open(cls, path, *, create=True):
        root = _root(path)
        state_dir = root/".sciencebot"
        # Application state cannot be redirected through a symlink or junction.
        if state_dir.resolve() != state_dir:
            raise ValueError("Workspace state directory must not be redirected")
        config = state_dir/"workspace.json"
        if not create and not config.is_file():
            raise ValueError("Workspace metadata is missing; refusing to create a new identity while restoring")
        state_dir.mkdir(exist_ok=True)
        for child in (state_dir/"sessions", state_dir/".session.lock"):
            if child.resolve() != child:
                raise ValueError("Workspace state paths must not be redirected")
        from ..planning_agent import session_lock
        with session_lock(state_dir):
            if state_dir.resolve() != state_dir or config.resolve() != config or config.with_name("workspace.json.tmp").resolve() != config.with_name("workspace.json.tmp"):
                raise ValueError("Workspace metadata must stay inside its state directory")
            if config.exists():
                try:
                    binding = json.loads(config.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise ValueError("Invalid workspace metadata") from exc
                cls._validate_binding(binding, root)
            elif create:
                binding = {"schema_version": SCHEMA, "workspace_id": uuid.uuid4().hex,
                           "root": str(root), "read_policy": READ_POLICY}
                write_json(config, binding)
            else:
                raise ValueError("Workspace metadata disappeared while restoring")
        return cls(root, binding)

    @staticmethod
    def _validate_binding(binding, root):
        if not isinstance(binding, dict) or set(binding) != {"schema_version", "workspace_id", "root", "read_policy"}:
            raise ValueError("Unsupported workspace metadata")
        identity = binding["workspace_id"]
        if (binding["schema_version"] != SCHEMA or binding["read_policy"] != READ_POLICY
                or not isinstance(identity, str) or len(identity) != 32
                or any(c not in "0123456789abcdef" for c in identity)
                or not isinstance(binding["root"], str) or Path(binding["root"]) != root):
            raise ValueError("Workspace identity, path or read policy mismatch")

    @classmethod
    def restore(cls, binding, expected_root=None):
        if not isinstance(binding, dict) or not isinstance(binding.get("root"), str):
            raise ValueError("Invalid session workspace binding")
        if expected_root is not None and _root(expected_root) != _root(binding["root"]):
            raise ValueError("Session belongs to another workspace")
        workspace = cls.open(binding["root"], create=False)
        if workspace.binding != binding:
            raise ValueError("Workspace identity changed since session creation")
        return workspace

    def describe(self):
        return {**self.binding, "sessions_dir": str(self.sessions_dir), "max_text_bytes": MAX_TEXT_BYTES,
                "excluded_directories": sorted(EXCLUDED_DIRS), "file_reads": "local_only"}

    def resolve_file(self, relative):
        if not isinstance(relative, (str, Path)) or not str(relative).strip():
            raise ValueError("Provide a project file path")
        value = str(relative).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        candidate = self.root/Path(value)
        try:
            # Check both the named path and link target, including excluded aliases.
            lexical = Path(os.path.abspath(candidate))
            resolved = candidate.resolve(strict=True)
            if not lexical.is_relative_to(self.root) or not resolved.is_relative_to(self.root):
                raise ValueError("File is outside this workspace")
            if _excluded(lexical.relative_to(self.root)) or _excluded(resolved.relative_to(self.root)):
                raise ValueError("File is excluded by the workspace read policy")
        except (OSError, RuntimeError) as exc:
            raise ValueError("Project file cannot be resolved") from exc
        if not resolved.is_file():
            raise ValueError("Provide a file, not a directory")
        return resolved

    def read_text(self, relative):
        path = self.resolve_file(relative)
        with path.open("rb") as stream:
            raw = stream.read(MAX_TEXT_BYTES+1)
        if len(raw) > MAX_TEXT_BYTES:
            raise ValueError(f"Text file exceeds {MAX_TEXT_BYTES} bytes; use a dedicated data tool")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Project text reads require UTF-8; binary data needs a dedicated tool") from exc
        if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
            raise ValueError("Binary or terminal control characters are not accepted in project text")
        return {"path": path.relative_to(self.root).as_posix(), "text": text,
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    def files(self, pattern="*", *, limit=200, scan_limit=20000):
        if not isinstance(pattern, str) or len(pattern) > 200 or not 1 <= limit <= 1000:
            raise ValueError("Invalid file-list pattern or limit")
        result, scanned, truncated = [], 0, False
        def walkable(path):
            if _excluded(path.relative_to(self.root)):
                return False
            try:
                return path.resolve() == path
            except (OSError, RuntimeError):
                return False
        for directory, directories, filenames in os.walk(self.root, followlinks=False):
            scanned += 1
            if scanned > scan_limit:
                truncated = True; break
            folder = Path(directory)
            directories[:] = sorted(d for d in directories if walkable(folder/d))
            for name in sorted(filenames):
                scanned += 1
                if scanned > scan_limit:
                    truncated = True; break
                path = folder/name
                relative = path.relative_to(self.root)
                if _excluded(relative) or not fnmatch(relative.as_posix(), pattern):
                    continue
                try:
                    safe = self.resolve_file(relative)
                    size = safe.stat().st_size
                except (ValueError, OSError):
                    continue
                if len(result) >= limit:
                    truncated = True; break
                result.append({"path": relative.as_posix(), "bytes": size})
            if truncated:
                break
        return {"files": result, "truncated": truncated, "scanned": min(scanned, scan_limit), "pattern": pattern}
