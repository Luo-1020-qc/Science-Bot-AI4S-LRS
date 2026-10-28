"""Read-only source comparisons and sealed dataset/RL delivery verification."""
import ast
import json
from pathlib import Path
import re
from protocol import ROOT, sha, digest, verify_runtime, write
from validate import validate_data


def verify():
    dataset, project = ROOT.parent, ROOT.parent.parent
    result = validate_data()
    validation = json.loads((ROOT/"verification.json").read_text(encoding="utf-8"))
    if not validation.get("tests_passed"):
        raise ValueError("Run validate_current.py --tests before delivery verification")

    snapshot = json.loads((ROOT/"v1_snapshot.json").read_text(encoding="utf-8"))["files"]
    archive_errors = [p for p, h in snapshot.items() if sha(dataset/"v1"/p) != h]
    if archive_errors: raise ValueError("Original v1 archive differs: "+str(archive_errors))

    runtime = json.loads((ROOT/"tool_runtime/source_manifest.json").read_text(encoding="utf-8"))
    for row in runtime:
        if sha(Path(row["source"])) != row["source_sha256"]:
            raise ValueError("Original detailed tool library source changed")
        original = Path(row["source"]).read_text(encoding="utf-8")
        if row["copy"] == "doe_adapter.py":
            original = original.replace('PROJECT = ROOT.parent', 'PROJECT = next(p for p in ROOT.parents if (p/"RUT_Science/research/strategy_learning").is_dir())')
        if (ROOT/"tool_runtime"/row["copy"]).read_text(encoding="utf-8") != original:
            raise ValueError("Runtime differs beyond declared adapter relocation/newline normalization")
    verify_runtime()

    baseline_dir = project/"RUT_Science/delivery/research_online_update"
    baseline = json.loads((baseline_dir/"protected_before.json").read_text(encoding="utf-8"))["files"]
    overlay = json.loads((baseline_dir/"authorized_source_changes.json").read_text(encoding="utf-8"))["files"]
    changed = [p for p, h in baseline.items() if sha(project/p) != overlay.get(p, {}).get("sha256", h)]
    if changed: raise ValueError("Protected live project differs from accepted hashes: "+str(changed))

    from ppo_smoke import verify_rollout
    from protocol import rows
    smoke = json.loads((ROOT/"ppo_smoke/verification.json").read_text(encoding="utf-8"))
    behavior = json.loads((ROOT/"ppo_smoke/behavior_policy.json").read_text(encoding="utf-8"))
    updated = json.loads((ROOT/"ppo_smoke/updated_policy.json").read_text(encoding="utf-8"))
    rollout = verify_rollout(rows(ROOT/"ppo_smoke/rollout.jsonl"), behavior)
    if digest(behavior) != smoke["behavior_policy_hash"] or digest(updated) != smoke["updated_policy_hash"] or digest(behavior) == digest(updated):
        raise ValueError("PPO update snapshot/hash mismatch")

    # AST checks read source only, avoiding pycache changes to archived or live files.
    sources = list(ROOT.glob("*.py"))+list((ROOT/"tests").glob("*.py"))+list((ROOT/"tool_runtime").glob("*.py"))
    sources += [dataset/"prepare_v2.py", dataset/"validate_current.py"]
    for path in sources: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    source_freeze = {p.relative_to(dataset).as_posix(): sha(p) for p in sources}
    source_freeze.update({p.relative_to(dataset).as_posix(): sha(p) for p in (ROOT/"schemas").glob("*.json")})
    source_freeze["v2/tool_runtime/source_manifest.json"] = sha(ROOT/"tool_runtime/source_manifest.json")
    write(ROOT/"source_freeze.json", {"version": "tool_harness_rl_v2", "sha256": source_freeze,
        "environment_hash": sha(ROOT/"environment.py"), "reward_protocol_hash": sha(ROOT/"protocol.py"),
        "catalog_hash": verify_runtime(), "scope": "Local reproducibility hashes; not a cryptographic signature or proof of scientific validity"})

    # Report exists before checking documentation links to the report itself.
    result.update(tests=validation["tests"], tests_passed=True, v1_archived_files_verified=len(snapshot),
        original_tool_library_sources_verified=len(runtime), protected_live_project_files_verified=len(baseline),
        unexpected_protected_file_changes=[], source_files_parsed=len(sources), ppo=smoke,
        ppo_recomputed=rollout, main_agent_entry_modified=False,
        scope="Bounded offline tool-candidate RL compatibility; no efficacy/generalization claim")
    write(ROOT/"delivery_verification.json", result)
    documents = [dataset/"README_训练数据说明.md", ROOT/"README_可训练数据集.md", ROOT/"专家扩展数据库_交接手册.md"]
    count = 0
    for document in documents:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"): continue
            path = (document.parent/target.split("#")[0]).resolve()
            if not path.exists(): raise ValueError("Broken local documentation link: "+str(path))
            count += 1
    result["local_documentation_links_verified"] = count
    write(ROOT/"delivery_verification.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "ppo"}, ensure_ascii=False))


if __name__ == "__main__": verify()
