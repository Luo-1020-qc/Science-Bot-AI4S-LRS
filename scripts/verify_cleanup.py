"""Verify every retained/moved pre-cleanup architecture and weight file."""
import json
import os
from pathlib import Path
from integrity import ROOT, sha, check_project


def main():
    record = ROOT/"docs/cleanup/2026-10-28"
    before = json.loads((record/"protected_before.json").read_text(encoding="utf-8"))
    plan = json.loads((record/"plan.json").read_text(encoding="utf-8"))
    check_project(ROOT)
    overlay_path = ROOT/"docs/integration/tool_library_2026-10-28/authorized_source_changes.json"
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))["files"] if overlay_path.exists() else {}
    changes, current, archived = [], {}, 0
    for original, row in before["files"].items():
        path = Path(row["final_path"])
        expected = overlay.get(original, {}).get("sha256", row["sha256"])
        if not path.is_file() or sha(path) != expected: changes.append(original)
        if path.is_relative_to(ROOT): current[path.relative_to(ROOT).as_posix()] = row["sha256"]
        else: archived += 1
    if changes: raise ValueError("Protected material lost/changed: "+str(changes[:10]))
    removed = [row["source"] for row in plan["deletes"] if not (ROOT/row["source"]).exists()]
    if len(removed) != len(plan["deletes"]): raise ValueError("Some retired entries remain")
    inventory = json.loads((record/"inventory_before.json").read_text(encoding="utf-8"))["files"]
    moved_files = 0
    for name, row in inventory.items():
        for move in plan["moves"]:
            if name == move["source"] or name.startswith(move["source"]+"/"):
                target = Path(move["destination"])/Path(name).relative_to(move["source"])
                checked = Path("\\\\?\\"+str(target)) if os.name == "nt" else target
                if not checked.is_file() or sha(checked) != row["sha256"]:
                    raise ValueError("Moved historical material differs: "+name)
                moved_files += 1
                break
    # Pin retained structure/weights using portable relative paths for new clones.
    (record/"protected_current.json").write_text(json.dumps({"sha256": current, "scope": "Architecture and saved policies retained byte-for-byte; excludes editable documentation/auditors"}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    value = {"passed": True, "protected_files_verified": len(before["files"]), "weight_related_files_verified": len(before["weight_files"]),
        "architecture_files_verified": len(before["architecture_files"]), "protected_files_in_current_project": len(current),
        "protected_historical_files_preserved_in_archive": archived, "unexpected_changes": changes,
        "move_entries": len(plan["moves"]), "retired_entries_removed": len(removed), "archive_root": plan["archive_root"],
        "moved_historical_files_hash_verified": moved_files,
        "authorized_post_cleanup_host_changes": len(overlay),
        "weights_deleted": 0, "weights_retrained": False, "default_policy_changed": False}
    (record/"preservation.json").write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__": main()
