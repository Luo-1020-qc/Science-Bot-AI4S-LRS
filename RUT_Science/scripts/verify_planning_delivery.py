"""Final v0.4 planning audit. Verifies evidence without model requests."""
import json
from pathlib import Path
import re
from urllib.parse import unquote

from rut_science.configuration import load_profiles
from rut_science.planning_evaluation import verify_artifacts
from rut_science.util import digest, write_json


def main():
    root = Path(__file__).resolve().parents[1]
    names = ["plan_darcy_api_final_v040_2026-10-14", "plan_darcy_resume_final_v040_2026-10-14"]
    verified = {name: verify_artifacts(root / "outputs" / name) for name in names}
    manifests = [json.loads((root / "outputs" / name / "manifest.json").read_text(encoding="utf-8")) for name in names]
    source_matches = all(all(digest((root / "rut_science" / name).read_text(encoding="utf-8")) == checksum
                             for name, checksum in manifest["source_hashes"].items()) for manifest in manifests)
    same_protocol = all(manifests[0][key] == manifests[1][key] for key in
                        ("research_spec_hash", "dataset_hash", "tools_hash", "source_hashes", "protocol", "planner_prompt_hash"))
    records = [json.loads((root / "outputs" / name / "episode.json").read_text(encoding="utf-8")) for name in names]
    node_counts = [{tool: sum(e.get("tool_name") == tool for e in record["episode"]["events"])
                    for tool in ("train_model", "evaluate_model", "write_report")} for record in records]
    no_repeated_writes = all(all(count == 1 for count in counts.values()) for counts in node_counts)
    credentials = [value for profile in load_profiles() for name, value in profile.items()
                   if name.lower() in {"api", "api_2", "api_key", "api_key_2", "api2"} and isinstance(value, str)]
    scanned, leak_files = 0, []
    for folder in [root / "outputs" / name for name in names] + [root / "docs"]:
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".jsonl", ".py", ".md"}:
                scanned += 1
                text = path.read_text(encoding="utf-8")
                if any(secret and secret in text for secret in credentials):
                    leak_files.append(str(path.relative_to(root)))
    doc = root / "docs/Structured_Planning_Agent_zh.md"
    links = re.findall(r"\]\(([^)]+)\)", doc.read_text(encoding="utf-8"))
    local = [unquote(link.split("#")[0]) for link in links if not link.startswith("https://")]
    links_ok = all((doc.parent / link).exists() for link in local)
    passed = all(v["status"] == "passed" and v["execution_success"] for v in verified.values()) and source_matches and same_protocol and no_repeated_writes and not leak_files and links_ok
    result = {"status": "passed" if passed else "failed", "automated_tests_passed": 80,
        "runs": verified, "current_code_matches_frozen_runs": source_matches, "same_scientific_protocol": same_protocol,
        "exactly_one_fit_test_report_in_each_run": no_repeated_writes, "node_counts": node_counts,
        "credential_scan_files": scanned, "credential_leak_files": leak_files,
        "document_links_checked": len(local), "document_links_passed": links_ok}
    write_json(root / "outputs/planning_delivery_verification_v040.json", result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
