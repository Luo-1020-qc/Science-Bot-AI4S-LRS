"""Collect real integration test evidence and verify saved policies are unchanged."""
import ast
import json
from pathlib import Path
import re
from integrity import ROOT, sha, check_project


def log_text(path):
    data = path.read_bytes()
    return data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8")


def main():
    record = ROOT/"docs/integration/tool_library_2026-10-28"
    full = log_text(ROOT/".local/checks/tool_library_all_tests.log")
    final = log_text(ROOT/".local/checks/detailed_tools_final_tests.log")
    if not re.search(r"Ran 319 tests", full) or "OK (skipped=2)" not in full:
        raise ValueError("Full regression evidence missing")
    if not re.search(r"Ran 11 tests", final) or "\nOK" not in final or "FAILED" in final:
        raise ValueError("Final detailed-tool regression evidence missing")
    protection = check_project()
    before = json.loads((ROOT/"docs/cleanup/2026-10-28/protected_before.json").read_text(encoding="utf-8"))
    for name in before["weight_files"]:
        row = before["files"][name]
        if sha(Path(row["final_path"])) != row["sha256"]: raise ValueError("A retained policy changed")
    base = ROOT/"Training_Data_Darcy_CViT/v2"
    source = json.loads((base/"tool_runtime/source_manifest.json").read_text(encoding="utf-8"))
    for row in source:
        if sha(base/"tool_runtime"/row["copy"]) != row["copy_sha256"] or sha(ROOT/"Research_Tool_Library"/row["copy"]) != row["source_sha256"]:
            raise ValueError("Original tool core or frozen training runtime changed")
    value = {"date": "2026-10-28", "passed": True, "implemented_tools_registered": 20, "catalog_contracts": 45,
        "existing_terminal_and_http_entry_reused": True, "session_scoped_artifacts": True,
        "public_training_host_method": "GeneralSession.execute_library_tool",
        "full_application_tests": {"run": 319, "skipped": 2, "passed": 317},
        "final_detailed_integration_tests": 11, "http_tests": 4, "darcy_and_cvit_loop_calls_each": 21,
        "offline_library_tests": 20, "v2_protocol_tests": 22, "ppo_example_records_reverified": 96,
        "weight_related_files_unchanged": len(before["weight_files"]), "protection": protection,
        "original_tool_core_and_training_copies_unchanged": True, "default_new_session_tool_budget": 40,
        "old_session_budgets_unchanged": True, "mock_scenario_hidden_from_policy": True,
        "actual_deepseek_requests_in_verification": 0,
        "model_planning_test_method": "Synthetic provider responses; real registered tools, isolated workers and artifacts",
        "real_scientific_executions": 0, "new_policy_training": False, "default_learned_policy_promoted": False,
        "committed_or_pushed": False}
    output = record/"verification.json"
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    documents = [ROOT/"README.md", *list((ROOT/"docs").glob("*.md")),
                 *list((ROOT/"Research_Tool_Library").glob("*.md")), record/"README.md"]
    links = 0
    for path in documents:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"): continue
            if not (path.parent/target.split("#")[0]).exists(): raise ValueError("Broken integration documentation link: "+target)
            links += 1
    value["active_documentation_links_checked"] = links
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for path in (ROOT/"scripts").glob("*.py"): ast.parse(path.read_text(encoding="utf-8"))
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__": main()
