"""Fixed read-only bridge to frozen G2.4 math; no live tool imports."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
HUB = PROJECT/"RUT_Science/research/strategy_learning"
STUDY = HUB/"studies/g2_4"


def guard():
    def audit(event, args):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.startfile", "os.posix_spawn", "os.exec", "os.spawn"}:
            raise PermissionError("Read-only DOE adapter has no network/process tools")
        if event == "import" and str(args[0]).split(".")[0] in {"rut_science", "dynamic_cvit"}:
            raise PermissionError("Live Agent and CViT imports prohibited")
        if event == "open":
            path, mode, flags = args
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
                raise PermissionError("Read-only adapter")
            if isinstance(path, (str, bytes)) and Path(os.fsdecode(path)).name.casefold() == "api_key_agent.json":
                raise PermissionError("No credential reads")
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.replace", "os.truncate", "os.chmod", "os.utime", "os.link", "os.symlink"}:
            raise PermissionError("Read-only adapter")
    sys.addaudithook(audit)


def execute(value):
    if type(value) is not dict or set(value)-{"action", "family", "contract", "request"}:
        raise ValueError("Unknown DOE adapter input")
    manifest = json.loads((HUB/"online_artifacts.json").read_text(encoding="utf-8"))["studies"]["g2_4"]
    for relative, checksum in manifest.items():
        if hashlib.sha256((STUDY/relative).read_bytes()).hexdigest() != checksum:
            raise ValueError("Frozen G2.4 dependency changed")
    sys.path.insert(0, str(STUDY))
    from doe.compiler import compile_plan
    from doe.validation import validate
    from doe.schema import CONTRACT_SCHEMA, errors, FAMILIES
    if value["action"] == "template":
        from doe.tasks import base_contract
        if value["family"] not in FAMILIES:
            raise ValueError("Unsupported DOE family")
        request, contract = base_contract(value["family"], 73)
        return {"request": request, "contract": contract}
    contract, request = value["contract"], value["request"]
    if value["action"] == "compile":
        if errors(contract, CONTRACT_SCHEMA):
            raise ValueError("Contract schema invalid before compilation")
        contract["run_plan"] = compile_plan(contract)
        return {"request": request, "contract": contract}
    if value["action"] == "review":
        try:
            return validate(contract, request)
        except (ValueError, ArithmeticError) as exc:
            return {"ready_for_review": False, "checks": [{"code": "numeric_failure", "status": "blocked", "detail": str(exc)[:200]}],
                    "diagnostics": None, "execution_authorized": False, "scientific_success": None}
    raise ValueError("Unknown DOE adapter action")


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    guard()
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="strict")
    try:
        raw = sys.stdin.read(300001)
        if len(raw) > 300000:
            raise ValueError("Adapter input too large")
        result = execute(json.loads(raw))
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:1000]}, ensure_ascii=False))
        raise SystemExit(1)
