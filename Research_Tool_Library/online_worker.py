"""Session-scoped adapter to the original offline library; never starts live jobs."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
import core
import doe_adapter
from catalog import CATALOG


def main():
    payload = core.strict(sys.stdin.read(300001))
    if type(payload) is not dict or set(payload) != {"session_folder", "tool", "arguments", "inspect_refs"}:
        raise ValueError("Closed worker envelope required")
    folder = Path(payload["session_folder"]).absolute()
    if folder.resolve() != folder or not (folder/"session.json").is_file():
        raise ValueError("Host-created session required")
    meta = core.strict((folder/"session.json").read_text(encoding="utf-8"))
    if meta.get("engine_version") != "general_v1" or meta.get("id") != folder.name:
        raise ValueError("Session identity mismatch")
    sandbox = folder/"tool_library"
    if sandbox.resolve() != sandbox: raise ValueError("Redirected tool sandbox")

    # Reuse immutable Store methods, changing only its host-chosen sandbox root.
    # No original library source or v2 training copy is modified.
    class SessionStore(core.Store):
        def __init__(self, selected):
            self.folder = Path(selected).absolute()
            if self.folder != sandbox or self.folder.resolve() != self.folder:
                raise ValueError("Store outside host session")
            self.folder.mkdir(exist_ok=True)
            objects = self.folder/"objects"
            if objects.resolve() != objects: raise ValueError("Redirected object store")
            objects.mkdir(exist_ok=True)

    core.Store = SessionStore
    core.adapter = lambda action, **kw: doe_adapter.execute({"action": action, **kw})

    def guard(event, args):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.startfile", "os.posix_spawn", "os.exec", "os.spawn"}:
            raise PermissionError("Offline tools cannot use network or process execution")
        if event == "import" and str(args[0]).split(".")[0] in {"rut_science", "dynamic_cvit"}:
            raise PermissionError("No live Agent/scientific executor imports")
        if event == "open":
            path, mode, flags = args
            writing = isinstance(mode, str) and any(c in mode for c in "wax+") or isinstance(flags, int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)
            if isinstance(path, (str, bytes)):
                selected = Path(os.fsdecode(path)).absolute()
                if selected.name.casefold() == "api_key_agent.json": raise PermissionError("No credential reads")
                if writing and (not selected.is_relative_to(sandbox) or selected.resolve() != selected):
                    raise PermissionError("Writes confined to current tool session")
        if event == "os.mkdir":
            selected = Path(args[0]).absolute()
            if not selected.is_relative_to(sandbox) or selected.resolve() != selected: raise PermissionError("Outside mkdir")
        if event in {"os.remove", "os.rmdir", "os.rename", "os.replace", "os.link", "os.symlink", "os.truncate"}:
            raise PermissionError("No destructive filesystem tools")
    sys.addaudithook(guard)
    library = core.Library(sandbox)
    for reference in payload["inspect_refs"]: library.store.get(reference)
    if payload["tool"] is None:
        return {"inspected_refs": len(payload["inspect_refs"]), "catalog_hash": core.digest(CATALOG),
                "artifacts": {ref: library.store.get(ref) for ref in payload["inspect_refs"]}}
    result = library.call(payload["tool"], payload["arguments"])
    return {**result, "catalog_hash": core.digest(CATALOG)}


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr): stream.reconfigure(encoding="utf-8", errors="replace")
    try: print(json.dumps({"ok": True, "result": main(), "real_execution": False}, ensure_ascii=False, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:600], "real_execution": False}, ensure_ascii=False))
        raise SystemExit(1)
