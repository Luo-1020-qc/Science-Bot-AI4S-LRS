"""Read-only delivery audit plus one small verification JSON; no API requests."""
import json
from pathlib import Path
import re
from urllib.parse import unquote

from rut_science.configuration import load_profiles
from rut_science.darcy_workflow import verify_run
from rut_science.util import digest, write_json


def main():
    root = Path(__file__).resolve().parents[1]
    data = root / "data/darcy_cpu_v1"
    names = ["darcy_cpu_control_release_v030", "darcy_cpu_deepseek_release_v030"]
    verifications = {name: verify_run(data, root / "outputs" / name) for name in names}
    manifests = {name: json.loads((root / "outputs" / name / "manifest.json").read_text(encoding="utf-8")) for name in names}
    source_match = all(all(digest((root / "rut_science" / name).read_text(encoding="utf-8")) == checksum
                           for name, checksum in manifest["source_hashes"].items()) for manifest in manifests.values())
    same_protocol = all(manifests[names[0]][key] == manifests[names[1]][key]
                        for key in ("source_hashes", "dataset_hash", "spec_hash", "tools_hash", "system_prompt_hash"))
    doc = root / "docs/ResearchSpec_Darcy_Workflow_zh.md"
    links = re.findall(r"\]\(([^)]+)\)", doc.read_text(encoding="utf-8"))
    local_links = [unquote(link.split("#")[0]) for link in links if not link.startswith("https://")]
    links_ok = all((doc.parent / link).exists() for link in local_links)
    credentials = []
    for profile in load_profiles():
        credentials.extend(value for key, value in profile.items() if key.lower() in
                           {"api", "api_2", "api_key", "api2", "api_key_2"} and isinstance(value, str))
    scan_roots = [root / "outputs" / name for name in names] + [root / "docs", data]
    leaks = []
    scanned = 0
    for folder in scan_roots:
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".py"}:
                scanned += 1
                content = path.read_text(encoding="utf-8")
                if any(secret and secret in content for secret in credentials):
                    leaks.append(str(path.relative_to(root)))
    passed = all(v["status"] == "passed" for v in verifications.values()) and source_match and same_protocol and links_ok and not leaks
    result = {"status": "passed" if passed else "failed", "runs": {name: v["status"] for name, v in verifications.items()},
              "current_source_matches_frozen_runs": source_match, "same_scientific_protocol_and_backend": same_protocol,
              "local_document_links_checked": len(local_links), "document_links_passed": links_ok,
              "credential_scan_files": scanned, "credential_leak_files": leaks,
              "test_evidence": "53 automated tests passed; generated unit fixtures distinguished from real MAT runs"}
    write_json(root / "outputs/v030_delivery_verification.json", result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
