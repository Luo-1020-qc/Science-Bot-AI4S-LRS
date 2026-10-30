"""Scenario requirements seed annotation work, never impersonate reviewed dialogues."""
from collections import Counter
from datetime import datetime
import hashlib
import re

from common import VERSION, fresh, identity, jsonl, lines, manifest, read, sha, write


def partition(group):
    bucket = int(identity("scientific-dialogue-split-v1", group)[:8], 16) % 100
    return "train" if bucket < 80 else "dev" if bucket < 90 else "test"


def template():
    return {"schema_version": VERSION, "dialogue_id": None, "source_group": None,
        "provenance": {"kind": "human_collected", "author_id": None,
                       "paper_ids": [], "source_hashes": []},
        "consent": {"training_allowed": False, "deidentified": False},
        "language": "zh", "messages": [], "decisions": [], "evidence": [],
        "plan_declarations": [],
        "understanding": {"status": "not_assessed", "before": None, "after": None},
        "review": {"decision": "pending", "reviewer_id": None, "reviewed_at": None,
                   "question_quality": None, "plan_testability": None, "notes": None}}


def audit_shells(source, output):
    files = sorted((source/"shells_json").glob("s*.json"))
    if not files:
        raise ValueError("No teammate scenario JSON files")
    index = read(source/"shells_json/index.json")
    indexed = {r["file"]: r for group in index["by_skeleton"].values() for r in group["scenarios"]}
    if set(indexed) != {p.name for p in files}:
        raise ValueError("Scenario index/files differ")
    for path in files:
        if sha(path) != indexed[path.name]["sha256"]:
            raise ValueError("Scenario differs from teammate's index: "+path.name)
    rows = [(p, read(p)) for p in files]
    yaml_checks = {"available": False, "checked": 0, "mismatches": []}
    try:
        import yaml
    except ImportError:
        pass
    else:
        yaml_checks["available"] = True
        for path, row in rows:
            original = source/"shells"/(path.stem+".yaml")
            with original.open(encoding="utf-8") as stream:
                if yaml.safe_load(stream) != row:
                    yaml_checks["mismatches"].append(path.name)
            yaml_checks["checked"] += 1
    if yaml_checks["mismatches"]:
        raise ValueError("Teammate YAML and JSON disagree")
    snapshot = {p.relative_to(source).as_posix(): sha(p) for p in source.rglob("*") if p.is_file()}
    queue = []
    for path, row in rows:
        item = template()
        item["dialogue_id"] = "pending:"+path.stem
        # One shared delivery group: don't randomly split related template variants.
        item["source_group"] = "teammate:coverage_tool_delivery_2026-10-29"
        item["provenance"] = {"kind": "scenario_template_pending", "author_id": None,
            "paper_ids": [], "source_hashes": [sha(path)]}
        item["seed"] = {"scenario_id": path.stem, "scenario_name": row["scenario_name"],
            "domain": row["domain"], "skeleton": row["skeleton"],
            "summary": row.get("summary", ""), "candidate_questions": row.get("survey_questions", []),
            "candidate_rubric": row.get("rubric", []), "source": row.get("source", ""),
            "executable_claim_unverified": row.get("executable", False)}
        queue.append(item)
    result = {"version": VERSION, "scenarios": len(rows),
        "skeleton_counts": dict(Counter(row["skeleton"] for _, row in rows)),
        "candidate_questions": sum(len(row.get("survey_questions", [])) for _, row in rows),
        "candidate_rubric_items": sum(len(row.get("rubric", [])) for _, row in rows),
        "index_hashes_match": True, "yaml_json_comparison": yaml_checks,
        "records_with_dialogue_turns": sum(any(k in row for k in ("messages", "turns", "dialogue")) for _, row in rows),
        "records_with_review_metadata": sum(any(k in row for k in ("review", "reviewer_id", "reviewed_at")) for _, row in rows),
        "records_with_evidence": sum("evidence" in row for _, row in rows),
        "declared_executable": sum(row.get("executable") is True for _, row in rows),
        "training_eligible_reviewed_dialogues": 0,
        "verdict": "Useful scenario/question/rubric seeds; not reviewed multi-turn dialogue training data",
        "execution_claims": "53/65 is an upstream declaration, not execution or external-validity evidence",
        "gaps": ["Observed or explicitly authored multi-turn messages and user replies",
                 "Context-specific choices, unknown/custom paths and correction behavior",
                 "Human review identity, timezone timestamp, rationale and quality labels",
                 "Exact paper/paragraph evidence, answerability and source provenance",
                 "Source-group partitions and independent human-understanding observations"],
        "source_sha256": snapshot, "source_modified": False}
    output = fresh(output)
    write(output/"audit.json", result)
    write(output/"template.json", template())
    jsonl(output/"pending.jsonl", queue)
    write(output/"manifest.json", {"version": VERSION, "files": manifest(output,
        ["audit.json", "template.json", "pending.jsonl"]), "eligible": 0})
    return {k: v for k, v in result.items() if k != "source_sha256"}


def validate_dialogue(row):
    if row.get("schema_version") != VERSION:
        raise ValueError("Unknown dialogue schema")
    for key in ("dialogue_id", "source_group"):
        if not isinstance(row.get(key), str) or not row[key].strip() or row[key].startswith("pending:"):
            raise ValueError("Real dialogue ID and source group required")
    provenance = row["provenance"]
    if provenance["kind"] not in {"human_collected", "human_authored", "model_generated_human_reviewed"} or not provenance.get("author_id"):
        raise ValueError("Pending templates cannot become human dialogues")
    if row["consent"] != {"training_allowed": True, "deidentified": True}:
        raise ValueError("Training consent and deidentification required")
    messages = row["messages"]
    if len(messages) < 4 or len(messages) % 2:
        raise ValueError("At least two complete user/assistant turns required")
    for index, message in enumerate(messages):
        if message.get("role") != ("user" if index % 2 == 0 else "assistant") or not isinstance(message.get("content"), str) or not message["content"].strip():
            raise ValueError("Messages must alternate nonempty user/assistant content")
        if re.search(r"(?:sk-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{20,}|api[_-]?key\s*[=:])", message["content"], re.I):
            raise ValueError("Potential credential in dialogue; redact before import")
    review = row["review"]
    if review["decision"] != "approved" or not review.get("reviewer_id") or not review.get("notes"):
        raise ValueError("Explicit human approval with reviewer and notes required")
    try:
        timestamp = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Human review needs an ISO timestamp") from exc
    if timestamp.utcoffset() is None:
        raise ValueError("Human review timestamp needs timezone")
    for key in ("question_quality", "plan_testability"):
        if type(review.get(key)) is not int or not 1 <= review[key] <= 5:
            raise ValueError("Human review needs 1..5 quality labels")
    evidence = {}
    for item in row["evidence"]:
        if item["id"] in evidence or not item.get("source_id") or not item.get("locator") or not item.get("quote"):
            raise ValueError("Evidence needs unique ID, source, locator and exact quote")
        if item.get("quote_sha256") != hashlib.sha256(item["quote"].encode()).hexdigest():
            raise ValueError("Evidence quote hash mismatch")
        if not re.fullmatch(r"[0-9a-f]{64}", item.get("source_sha256", "")):
            raise ValueError("Evidence source snapshot hash required")
        evidence[item["id"]] = item
    indices = set()
    fields = {"research_question", "objective_type", "hypothesis", "scope", "exclusions",
        "experimental_unit", "factors", "design", "outcomes", "baseline", "data_source", "sampling",
        "randomization", "analysis", "acceptance", "resources", "risks", "reproducibility", "human_roles", "deliverable"}
    for decision in row["decisions"]:
        index = decision["assistant_turn"]
        if type(index) is not int or index % 2 != 1 or not 0 <= index < len(messages) or index in indices:
            raise ValueError("Decision must identify one unique assistant message")
        indices.add(index)
        if decision["action"] not in {"ask", "request_evidence", "draft", "stop"}:
            raise ValueError("Unknown dialogue action")
        if any(type(i) is not int or i < 0 or i >= index or messages[i]["role"] != "user" for i in decision["based_on_user_turns"]):
            raise ValueError("Decision references future/non-user turns")
        if not decision["based_on_user_turns"]:
            raise ValueError("Decision requires preceding user context")
        if decision["target_field"] not in fields:
            raise ValueError("Unregistered planning field")
        if set(decision.get("evidence_ids", []))-set(evidence):
            raise ValueError("Decision cites nonexistent evidence")
        if decision["action"] in {"ask", "request_evidence"}:
            question = decision["question"]
            options = decision["options"]
            if not question or question not in messages[index]["content"]:
                raise ValueError("Question must occur in reviewed assistant response")
            if len(options) < 4 or len(options) > 6 or len({o["id"] for o in options}) != len(options) or len({o["label"] for o in options}) != len(options):
                raise ValueError("Distinct contextual choices plus unknown/custom required")
            types = [o["type"] for o in options]
            if types.count("unknown") != 1 or types.count("custom") != 1 or not 2 <= types.count("proposal") <= 4 or any(t not in {"unknown", "custom", "proposal"} for t in types):
                raise ValueError("Options need 2..4 proposals, one unknown and one custom")
            if any(not o["label"] or o["label"] not in messages[index]["content"] for o in options):
                raise ValueError("Option labels must occur in reviewed response")
    if indices != {i for i, m in enumerate(messages) if m["role"] == "assistant"}:
        raise ValueError("Review decisions must cover every assistant turn")
    for declaration in row["plan_declarations"]:
        if declaration["field"] not in fields or declaration["status"] not in {"declared", "proposed", "unknown"}:
            raise ValueError("Invalid plan declaration")
        if declaration["status"] == "unknown":
            if declaration["value"] is not None:
                raise ValueError("Unknown cannot become a filled fact")
        elif not isinstance(declaration["value"], str) or not declaration["value"].strip():
            raise ValueError("Plan declaration needs content")
        if declaration["status"] == "declared":
            turn = declaration["user_turn"]
            if type(turn) is not int or not 0 <= turn < len(messages) or messages[turn]["role"] != "user" or declaration["value"] not in messages[turn]["content"]:
                raise ValueError("Declared fact needs exact user grounding")
    understanding = row["understanding"]
    if understanding["status"] == "assessed":
        if not all(isinstance(understanding.get(k), str) and understanding[k].strip() for k in ("before", "after")):
            raise ValueError("Understanding assessment needs actual before/after responses")
    elif understanding["status"] != "not_assessed" or understanding.get("before") is not None or understanding.get("after") is not None:
        raise ValueError("Unmeasured understanding must stay unmeasured")
    return True


def import_reviewed(path, output):
    records = lines(path)
    if not records:
        raise ValueError("No reviewed dialogues supplied")
    seen_ids, content_groups, paper_groups = set(), {}, {}
    for row in records:
        validate_dialogue(row)
        if row["dialogue_id"] in seen_ids:
            raise ValueError("Duplicate dialogue ID")
        seen_ids.add(row["dialogue_id"])
        split = partition(row["source_group"])
        initial = identity(row["messages"][0]["content"].strip().casefold())
        for key, mapping in [(initial, content_groups), *[(p, paper_groups) for p in row["provenance"]["paper_ids"]]]:
            if key in mapping and mapping[key] != split:
                raise ValueError("Same initial request or paper crosses partitions")
            mapping[key] = split
        row["split"] = split
    output = fresh(output)
    for split in ("train", "dev", "test"):
        subset = [r for r in records if r["split"] == split]
        jsonl(output/(split+".jsonl"), subset)
        jsonl(output/(split+".sft.jsonl"), [{"id": r["dialogue_id"], "source_group": r["source_group"],
            "split": split, "messages": r["messages"], "review_metadata_in_model_input": False} for r in subset])
    result = {"version": VERSION, "input_sha256": sha(path),
        "reviewed_dialogues": len(records), "counts": dict(Counter(r["split"] for r in records)),
        "source_kinds": dict(Counter(r["provenance"]["kind"] for r in records)),
        "source_groups": len({r["source_group"] for r in records}),
        "understanding_assessed": sum(r["understanding"]["status"] == "assessed" for r in records),
        "identity_authentication": "Metadata validation only; does not authenticate reviewer identity or verify quoted source bytes",
        "files": manifest(output, [s+suffix for s in ("train", "dev", "test") for suffix in (".jsonl", ".sft.jsonl")])}
    write(output/"manifest.json", result)
    return result
