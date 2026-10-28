"""Verify current v2 delivery against portable Harness protection, without retired v1."""
import ast
import json
from pathlib import Path
import re
import runpy
from protocol import ROOT, sha, digest, verify_runtime, rows, write
from validate import validate_data
from ppo_smoke import verify_rollout


def verify():
    project = ROOT.parent.parent
    value = validate_data()
    tests = json.loads((ROOT/"verification.json").read_text(encoding="utf-8"))
    if not tests.get("tests_passed"): raise ValueError("Run validate_current.py --tests first")
    protected = runpy.run_path(str(project/"scripts/integrity.py"))["check_project"](project)
    runtime = json.loads((ROOT/"tool_runtime/source_manifest.json").read_text(encoding="utf-8"))
    for record in runtime:
        if sha(project/"Research_Tool_Library"/record["copy"]) != record["source_sha256"]:
            raise ValueError("Detailed tool source changed")
    verify_runtime()
    behavior = json.loads((ROOT/"ppo_smoke/behavior_policy.json").read_text(encoding="utf-8"))
    updated = json.loads((ROOT/"ppo_smoke/updated_policy.json").read_text(encoding="utf-8"))
    smoke = json.loads((ROOT/"ppo_smoke/verification.json").read_text(encoding="utf-8"))
    rollout = verify_rollout(rows(ROOT/"ppo_smoke/rollout.jsonl"), behavior)
    if digest(behavior) != smoke["behavior_policy_hash"] or digest(updated) != smoke["updated_policy_hash"] or digest(behavior) == digest(updated):
        raise ValueError("Saved PPO snapshots changed")
    sources = list(ROOT.glob("*.py"))+list((ROOT/"tests").glob("*.py"))+list((ROOT/"tool_runtime").glob("*.py"))
    sources += [ROOT.parent/"validate_current.py"]
    for path in sources: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    write(ROOT/"source_freeze.json", {"version": "tool_harness_rl_v2_cleaned_layout", "sha256": {p.relative_to(ROOT.parent).as_posix(): sha(p) for p in sources},
        "environment_hash": sha(ROOT/"environment.py"), "reward_protocol_hash": sha(ROOT/"protocol.py"), "catalog_hash": verify_runtime(),
        "scope": "Current source inventory; original policies and training environment retained byte-for-byte"})
    value.update(tests=tests["tests"], tests_passed=True, protected_harness_files_checked=protected["protected_files_checked"],
        retired_v1_required=False, original_tool_library_sources_verified=len(runtime), ppo_recomputed=rollout,
        ppo_parameters_changed=True, main_agent_entry_modified=False)
    write(ROOT/"delivery_verification.json", value)
    docs = [ROOT.parent/"README_训练数据说明.md", ROOT/"README_可训练数据集.md", ROOT.parent/"RL训练数据_专家交接文档.md"]
    links = 0
    for path in docs:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"): continue
            if not (path.parent/target.split("#")[0]).exists(): raise ValueError("Broken link: "+target)
            links += 1
    value["local_documentation_links_verified"] = links
    write(ROOT/"delivery_verification.json", value)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__": verify()
