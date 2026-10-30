"""Native-format adapters. Official groups/splits and annotator alternatives survive."""
import csv
import json
from pathlib import Path
import re
import tarfile
from collections import Counter

from acquire import check_raw
from common import SPLITS, VERSION, fresh, identity, jsonl, manifest, sha, write


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def tsv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def clariq(folder):
    bank = {}
    for row in tsv(Path(folder)/"clariq_questions.tsv"):
        question = normalize(row["question"])
        if question:
            bank[row["question_id"]] = question
    records, issues = [], Counter()
    for split in SPLITS:
        for n, row in enumerate(tsv(Path(folder)/("clariq_"+split+".tsv"))):
            request = normalize(row.get("initial_request", ""))
            qid = row.get("question_id", "")
            question = normalize(row.get("question", "")) or bank.get(qid, "")
            need = row.get("clarification_need", "")
            # Empty/no-question rows still supervise clarification need, not generation.
            if not request or need not in {"1", "2", "3", "4"}:
                issues["invalid_request_or_need"] += 1
                continue
            if question and qid in bank and bank[qid] != question:
                raise ValueError("ClariQ question bank disagrees with row")
            records.append({"id": identity("clariq", split, n), "source": "clariq",
                "source_group": "clariq:topic:"+row["topic_id"], "split": split,
                "request": request, "question": question, "question_id": qid,
                "clarification_need": int(need), "user_reply": row.get("answer", ""),
                "annotation_kind": "upstream_single_turn_not_scientific_or_option_preferences",
                # Facet description is intentionally not an agent input.
                "private_facet_id": row.get("facet_id", ""),
                "private_facet_description": row.get("facet_desc", "")})
    return records, bank, dict(issues)


def archive_json(path, filename):
    # Never extract or execute anything in an upstream archive (including evaluator).
    with tarfile.open(path, "r:gz") as archive:
        found = [m for m in archive.getmembers() if m.name in {filename, "./"+filename}]
        if len(found) != 1 or not found[0].isfile() or found[0].size > 160*1024*1024:
            raise ValueError("Expected one bounded dataset JSON member: "+filename)
        with archive.extractfile(found[0]) as stream:
            return json.load(stream)


def paragraphs(paper):
    rows = []
    if paper.get("abstract"):
        rows.append({"id": "abstract", "section": "Abstract", "text": paper["abstract"]})
    for section_index, section in enumerate(paper["full_text"]):
        for paragraph_index, text in enumerate(section["paragraphs"]):
            if normalize(text):
                rows.append({"id": f"s{section_index}:p{paragraph_index}",
                    "section": section.get("section_name", ""), "text": text})
    for index, figure in enumerate(paper.get("figures_and_tables", [])):
        if figure.get("caption"):
            rows.append({"id": f"figure:{index}", "section": "Figure or table caption",
                         "text": figure["caption"]})
    return rows


def qasper(folder):
    records, papers = [], {}
    for split in SPLITS:
        archive = "qasper_test.tgz" if split == "test" else "qasper_train_dev.tgz"
        data = archive_json(Path(folder)/archive, "qasper-"+split+"-v0.3.json")
        for paper_id, paper in data.items():
            if paper_id in papers:
                raise ValueError("QASPER paper crosses official splits")
            candidates = paragraphs(paper)
            papers[paper_id] = {"id": paper_id, "split": split, "title": paper["title"],
                                "paragraphs": candidates}
            lookup = {}
            for p in candidates:
                lookup.setdefault(normalize(p["text"]), []).append(p["id"])
                lookup.setdefault(normalize("FLOAT SELECTED: "+p["text"]), []).append(p["id"])
            for qa in paper["qas"]:
                answers = []
                for entry in qa["answers"]:
                    answer = entry["answer"]
                    matched, unmatched = set(), []
                    for evidence in answer.get("evidence", []):
                        ids = lookup.get(normalize(evidence), [])
                        if ids:
                            matched.update(ids)
                        else:
                            unmatched.append(evidence)
                    yes_no = answer.get("yes_no")
                    unanswerable = answer["unanswerable"]
                    text = ("" if unanswerable else "yes" if yes_no is True else
                            "no" if yes_no is False else answer.get("free_form_answer") or
                            " | ".join(answer.get("extractive_spans", [])))
                    answers.append({"unanswerable": unanswerable, "yes_no": yes_no,
                        "text": text, "extractive_spans": answer.get("extractive_spans", []),
                        "evidence_ids": sorted(matched), "unmatched_evidence": unmatched,
                        "annotation_id": entry.get("annotation_id", "")})
                records.append({"id": "qasper:"+qa["question_id"], "source": "qasper",
                    "source_group": "qasper:paper:"+paper_id, "paper_id": paper_id,
                    "split": split, "question": qa["question"], "answers": answers})
    return records, list(papers.values())


def check_splits(records):
    groups, ids, contexts = {}, set(), {}
    for row in records:
        if row["id"] in ids or row["split"] not in SPLITS:
            raise ValueError("Duplicate ID or invalid split")
        ids.add(row["id"])
        group, split = row["source_group"], row["split"]
        if group in groups and groups[group] != split:
            raise ValueError("Source group crosses splits: "+group)
        groups[group] = split
        if row["source"] == "clariq":
            key = normalize(row["request"]).casefold()
            if key in contexts and contexts[key] != split:
                raise ValueError("Identical request crosses splits")
            contexts[key] = split
    return Counter(groups.values())


def prepare(raw, output):
    receipt = check_raw(raw)
    questions, bank, issues = clariq(raw)
    evidence, papers = qasper(raw)
    records = questions+evidence
    groups = check_splits(records)
    output = fresh(output)
    jsonl(output/"clarification.jsonl", questions)
    write(output/"question_bank.json", bank)
    jsonl(output/"evidence.jsonl", evidence)
    jsonl(output/"papers.jsonl", papers)
    info = {"version": VERSION, "raw_receipt_sha256": sha(Path(raw)/"acquisition.json"),
        "source_receipt": receipt, "files": manifest(output, ["clarification.jsonl",
            "question_bank.json", "evidence.jsonl", "papers.jsonl"]),
        "counts": {"clarification": dict(Counter(r["split"] for r in questions)),
                   "evidence": dict(Counter(r["split"] for r in evidence)),
                   "papers": dict(Counter(r["split"] for r in papers))},
        "source_groups": dict(groups), "clariq_issues": issues,
        "clarq": "Importer available; bulk corpus not acquired or used in this run",
        "human_scientific_dialogues": 0, "model_requests": 0}
    write(output/"manifest.json", info)
    return info


def import_clarq(train_path, test_path, output):
    """Optional author-format JSONL; never pretend original-post answer is user feedback."""
    records, seen = [], {}
    for source_split, path in (("train", train_path), ("test", test_path)):
        with Path(path).open(encoding="utf-8") as stream:
            for line in stream:
                item = json.loads(line)
                text, question = normalize(item["context"]), normalize(item["cquestion"])
                if not text or not question:
                    continue
                # Full context identifies a group even when upstream IDs are missing.
                group = identity(text.casefold())
                split = ("dev" if int(group[:8], 16) % 10 == 0 else "train") if source_split == "train" else "test"
                if group in seen:
                    if seen[group] != split:
                        raise ValueError("ClarQ context overlaps train/test")
                seen[group] = split
                records.append({"id": identity("clarq", group, question), "source": "clarq",
                    "source_group": "clarq:post:"+group, "split": split, "request": text,
                    "question": question, "annotation_kind": "upstream_bootstrapped_pair",
                    "user_reply": None, "original_id": str(item.get("id", ""))})
    # Drop exact duplicate pairs, without allowing duplicate groups across partitions.
    records = list({row["id"]: row for row in records}.values())
    check_splits(records)
    output = fresh(output)
    jsonl(output/"clarq.jsonl", records)
    write(output/"manifest.json", {"version": VERSION, "source": "clarq",
        "source_files": {"train": sha(train_path), "test": sha(test_path)},
        "files": manifest(output, ["clarq.jsonl"]), "counts": dict(Counter(r["split"] for r in records)),
        "original_answer_used_as_clarification_reply": False})
