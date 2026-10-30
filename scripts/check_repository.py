"""Offline portable acceptance; never calls a model API or scientific executor."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_path(path):
    value = str(path.absolute())
    return "\\\\?\\"+value if os.name == "nt" and not value.startswith("\\\\?\\") else value


def git_binary():
    found = shutil.which("git")
    if found: return found
    for ancestor in ROOT.parents:
        candidate = ancestor/".tools/MinGit/cmd/git.exe"
        if candidate.is_file(): return str(candidate)
    return None


def run(command, *, cwd=ROOT, body=None):
    result = subprocess.run(command, cwd=cwd, input=body, encoding="utf-8", errors="strict",
                            capture_output=True, timeout=60)
    if result.returncode:
        # Commands are fixed local checks; credentials are never supplied.
        raise ValueError("Local check failed: "+str(command[-1])+"\n"+(result.stderr or result.stdout)[-1800:])
    return result.stdout


def check_frozen(root):
    hub = root/"RUT_Science/research/strategy_learning"
    manifest = json.loads((hub/"online_artifacts.json").read_text(encoding="utf-8"))["studies"]
    count = 0
    for study, files in manifest.items():
        for relative, checksum in files.items():
            if sha(hub/"studies"/study/relative) != checksum:
                raise ValueError("Frozen research changed: "+study+"/"+relative)
            count += 1
    return count


def worker_checks(root):
    worker = root/"RUT_Science/research/strategy_learning/online_worker.py"
    requests = [{"study": study, "action": "verify"} for study in ("g2_2", "g2_3", "g2_4")]
    requests += [{"study": "g2_3", "action": "simulate", "policy": "bc_ppo", "seed": 37,
                  "domain": "cvit", "scenario": "existing_running"}, {"study": "g2_4", "action": "demo"}]
    summaries = []
    for request in requests:
        value = json.loads(run([sys.executable, "-I", "-B", str(worker)], cwd=root, body=json.dumps(request)))
        if not value["ok"] or any(value[key] != 0 for key in
                ("real_tool_executions", "real_model_requests", "real_gpu_jobs", "formal_training_transitions")):
            raise ValueError("Offline research boundary violation")
        summaries.append({"request": request, "passed": True, "result_sha256":
            hashlib.sha256(json.dumps(value["result"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()})
    return summaries


def check(root, git):
    docs = [root/"README.md", root/"CONTRIBUTING.md", root/"CHANGELOG.md", *sorted((root/"docs").glob("*.md"))]
    link_count = 0
    for path in docs:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"): continue
            target = target.strip("<>").split("#")[0]
            if not (path.parent/target).resolve().exists(): raise ValueError("Broken link in "+path.name+": "+target)
            link_count += 1
    for path in (root/"scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    key_ignored = None
    if git:
        prefix = [git, "-c", "core.excludesFile=NUL", "-c", "core.quotePath=false"]
        for path in ("API_key_Agent.json", "RUT_Science/.venv/", "Training_Data/v2/tool_runtime/sessions/", "Training_Data/v2/expert/imports/"):
            run(prefix+["check-ignore", "--no-index", path], cwd=root)
        if run(prefix+["ls-files", "--", "API_key_Agent.json"], cwd=root).strip():
            raise ValueError("Local credential file is tracked")
        key_ignored = True
    import runpy
    protected = runpy.run_path(str(root/"scripts/integrity.py"))["check_project"](root)
    dataset = root/"Training_Data/v2"
    manifest = json.loads((dataset/"manifest.json").read_text(encoding="utf-8"))
    for path, checksum in manifest["artifact_sha256"].items():
        if sha(dataset/path) != checksum: raise ValueError("Current v2 dataset changed: "+path)
    runtime = root/"Training_Data/v2/tool_runtime"
    for record in json.loads((runtime/"source_manifest.json").read_text(encoding="utf-8")):
        if sha(runtime/record["copy"]) != record["copy_sha256"] or sha(root/"Research_Tool_Library"/record["copy"]) != record["source_sha256"]:
            raise ValueError("Original/copied detailed tool source changed")
    preview = run([sys.executable, "-B", "-m", "rut_science", "science", "--backend", "offline", "--preview"], cwd=root/"RUT_Science")
    if "Bot" not in preview: raise ValueError("Terminal preview missing")
    return {"passed": True, "local_links_checked": link_count, "credential_ignored_and_untracked": key_ignored,
        "current_v2_artifacts_checked": len(manifest["artifact_sha256"]), "protected_harness_files_checked": protected["protected_files_checked"],
        "frozen_research_artifacts_checked": check_frozen(root),
        "terminal_preview": True, "research_checks": worker_checks(root), "network_or_model_api_calls": 0,
        "real_scientific_executions": 0, "training_requested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relocation-smoke", action="store_true", help="Copy only Git-shareable files to a fresh ignored path and check them")
    args = parser.parse_args()
    git = git_binary()
    before_key = sha(ROOT/"API_key_Agent.json") if (ROOT/"API_key_Agent.json").exists() else None
    result = check(ROOT, git)
    result["checked_utc"] = datetime.now(timezone.utc).isoformat()
    if args.relocation_smoke:
        if not git: raise ValueError("Git is needed to enumerate the shareable file set")
        names = run([git, "-c", "core.excludesFile=NUL", "-c", "core.quotePath=false", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]).split("\0")
        names = sorted({name for name in names if name})
        folder = ROOT/".local/relocation_smoke"/uuid.uuid4().hex[:12]
        folder.mkdir(parents=True, exist_ok=False)
        for name in names:
            source, target = ROOT/name, folder/name
            if source.is_file():
                Path(native_path(target.parent)).mkdir(parents=True, exist_ok=True)
                shutil.copyfile(native_path(source), native_path(target))
        if (folder/"API_key_Agent.json").exists() or (folder/"RUT_Science/.venv").exists():
            raise ValueError("Credential/environment entered shareable snapshot")
        result["relocation_smoke"] = check(folder, None)
        if result["research_checks"] != result["relocation_smoke"]["research_checks"]:
            raise ValueError("Research outputs differ in relocated snapshot")
        result["relocation_smoke"].update(files_copied=len(names), no_api_key_or_venv=True,
            same_interpreter_used=True, fresh_machine_install_tested=False)
    after_key = sha(ROOT/"API_key_Agent.json") if (ROOT/"API_key_Agent.json").exists() else None
    if before_key != after_key: raise ValueError("Local key file changed")
    result["local_api_key_unchanged"] = True
    target = ROOT/".local/checks/repository_check.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__": raise SystemExit(main())
