"""Small supervised candidates, not LLM fine tuning or online planner deployment."""
from collections import Counter, defaultdict
from functools import lru_cache
import math
import re

import numpy as np

from adapters import check_splits
from common import (VERSION, SPLITS, fresh, identity, lines, manifest, read,
                    sha, source_code_hashes, verify_files, write)

SEED = 20261030
FEATURES = ["bias", "bm25", "cosine", "jaccard", "query_coverage", "candidate_coverage",
            "bigram_coverage", "exact_query", "length_ratio", "candidate_length",
            "query_length", "digit_overlap", "section_overlap", "position",
            "is_abstract", "is_caption"]
STOP = set("a an the is are was were be of in on to and or for with by as at it this that "
           "i me my we you your do does can could would should please tell find know about "
           "information interested looking like what which how when where why".split())


@lru_cache(maxsize=32768)
def tokens(text):
    if text is None:
        return ()  # QASPER legitimately has null section names.
    return tuple(t for t in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text.casefold()) if t not in STOP)


def feature_matrix(query, candidates, evidence=False):
    q = tokens(query)
    qc, qs = Counter(q), set(q)
    counts = [Counter(tokens(c["text"])) for c in candidates]
    df = Counter(t for count in counts for t in count)
    n = max(len(candidates), 1)
    average = sum(sum(c.values()) for c in counts)/n or 1
    idf = {t: math.log(1+(n-df[t]+0.5)/(df[t]+0.5)) for t in qs}
    norm = sum(idf.values()) or 1
    qb = set(zip(q, q[1:]))
    rows = []
    for index, (candidate, count) in enumerate(zip(candidates, counts)):
        ct, cs = tokens(candidate["text"]), set(count)
        shared, size = qs & cs, sum(count.values())
        bm25 = sum(idf[t]*count[t]*2.2/(count[t]+1.2*(0.25+0.75*size/average)) for t in shared)/norm
        cosine = sum(qc[t]*count[t] for t in shared)/(math.sqrt(sum(v*v for v in qc.values())*
                        sum(v*v for v in count.values())) or 1)
        section = set(tokens(candidate.get("section", "")))
        rows.append([1, bm25, cosine, len(shared)/max(len(qs | cs), 1),
            len(shared)/max(len(qs), 1), len(shared)/max(len(cs), 1),
            len(qb & set(zip(ct, ct[1:])))/max(len(qb), 1),
            float(bool(q) and " ".join(q) in " ".join(ct)),
            min(len(q), size)/max(len(q), size, 1), min(size, 500)/500,
            min(len(q), 100)/100, len({t for t in shared if t.isdigit()})/max(len(qs), 1),
            len(qs & section)/max(len(qs), 1) if evidence else 0,
            index/n if evidence else 0, float(candidate.get("id") == "abstract") if evidence else 0,
            float(candidate.get("id", "").startswith("figure:")) if evidence else 0])
    return np.asarray(rows, dtype=np.float64).reshape((-1, len(FEATURES)))


def fit_pairs(pairs):
    x = np.asarray(pairs, dtype=np.float64)
    if len(x) == 0:
        raise ValueError("No supervised ranking pairs")
    weights = np.zeros(x.shape[1])
    for _ in range(400):
        p = 1/(1+np.exp(np.clip(x @ weights, -35, 35)))
        weights += 0.3*((x.T @ p)/len(x)-0.002*weights)
    return weights, {"algorithm": "pairwise_logistic_regression", "steps": 400,
        "learning_rate": 0.3, "l2": 0.002, "training_pairs": len(x),
        "parameter_l2_change": float(np.linalg.norm(weights))}


def request_vector(request, dimensions=512):
    result = np.zeros(dimensions)
    for token in tokens(request):
        result[int(identity(token)[:8], 16) % dimensions] += 1
    result /= max(float(np.linalg.norm(result)), 1)
    return np.concatenate(([1.0], result))


def fit_need(topics):
    train = [t for t in topics if t["split"] == "train"]
    x = np.asarray([request_vector(t["request"]) for t in train])
    y = np.asarray([t["need"]-1 for t in train])
    weights = np.zeros((x.shape[1], 4))
    for _ in range(500):
        logits = x @ weights
        logits -= logits.max(axis=1, keepdims=True)
        probs = np.exp(logits)
        probs /= probs.sum(axis=1, keepdims=True)
        probs[np.arange(len(y)), y] -= 1
        weights -= 0.5*((x.T @ probs)/len(y)+0.002*weights)
    majority = Counter(y.tolist()).most_common(1)[0][0]+1
    return {"weights": weights.tolist(), "train_majority_label": majority,
            "parameter_l2_change": float(np.linalg.norm(weights)), "steps": 500,
            "learning_rate": 0.5, "l2": 0.002, "dimensions": 512,
            "training_topics": len(train), "label_meaning": "Original ClariQ 1..4 labels"}


def topic_cases(records):
    groups = {}
    for row in records:
        group = row["source_group"]
        key = (group, row["request"])
        value = groups.setdefault(key, {"id": group+":"+identity(row["request"])[:12],
            "source_group": group, "request": row["request"],
            "split": row["split"], "need": row["clarification_need"], "positives": set()})
        if value["request"] != row["request"] or value["need"] != row["clarification_need"]:
            raise ValueError("Inconsistent ClariQ topic request/need")
        if row["question"] and row["question"].casefold() not in {"no question", "no clarification needed"}:
            value["positives"].add(row["question"])
    return list(groups.values())


def question_candidates(bank):
    texts = sorted({v for v in bank.values() if v.casefold() not in {"no question", "no clarification needed"}})
    return [{"id": identity(t), "text": t} for t in texts]


def ranked(scores):
    return np.argsort(-scores, kind="stable")


def ranking_metrics(order, positives):
    return {"hit_at_1": float(int(order[0]) in positives),
            "recall_at_3": len(set(map(int, order[:3])) & positives)/len(positives),
            "recall_at_5": len(set(map(int, order[:5])) & positives)/len(positives),
            "mrr": 1/next(i+1 for i, p in enumerate(order) if int(p) in positives)}


def mean_metrics(rows):
    if not rows:
        return {"evaluated": 0}
    return {"evaluated": len(rows), **{key: round(sum(r[key] for r in rows)/len(rows), 8) for key in rows[0]}}


def evaluate_questions(topics, candidates, ranker, need):
    results = {}
    w = np.asarray(ranker["weights"])
    need_w = np.asarray(need["weights"])
    for split in SPLITS:
        baseline, trained, need_hits, majority_hits = [], [], [], []
        for topic in [t for t in topics if t["split"] == split]:
            predicted = int(np.argmax(request_vector(topic["request"]) @ need_w))+1
            need_hits.append(int(predicted == topic["need"]))
            majority_hits.append(int(need["train_majority_label"] == topic["need"]))
            if topic["need"] == 1:
                continue
            positives = {i for i, c in enumerate(candidates) if c["text"] in topic["positives"]}
            if not positives:
                continue
            x = feature_matrix(topic["request"], candidates)
            baseline.append(ranking_metrics(ranked(x[:, 1]), positives))
            trained.append(ranking_metrics(ranked(x @ w), positives))
        results[split] = {"question_bm25": mean_metrics(baseline), "question_trained": mean_metrics(trained),
            "need_topics": len(need_hits), "need_accuracy": round(sum(need_hits)/max(len(need_hits), 1), 8),
            "need_majority_accuracy": round(sum(majority_hits)/max(len(majority_hits), 1), 8)}
    return results


def evidence_cases(records, papers):
    for record in records:
        candidates = papers[record["paper_id"]]["paragraphs"]
        lookup = {p["id"]: i for i, p in enumerate(candidates)}
        annotations = [a for a in record["answers"] if not a["unanswerable"] and
                       a["evidence_ids"] and not a["unmatched_evidence"]]
        if not annotations:
            continue
        gold_sets = [{lookup[p] for p in a["evidence_ids"]} for a in annotations]
        yield record, candidates, gold_sets


def evaluate_evidence(records, papers, ranker):
    output = {}
    for split in SPLITS:
        baseline, trained = [], []
        subset = [r for r in records if r["split"] == split]
        for record, candidates, gold_sets in evidence_cases(subset, papers):
            x = feature_matrix(record["question"], candidates, evidence=True)
            for target, order in ((baseline, ranked(x[:, 1])),
                                  (trained, ranked(x @ np.asarray(ranker["weights"])))):
                # Keep annotator alternatives separate; best overlap per question.
                scores = [ranking_metrics(order, gold) for gold in gold_sets]
                target.append({key: max(s[key] for s in scores) for key in scores[0]})
        output[split] = {"bm25": mean_metrics(baseline), "trained": mean_metrics(trained),
            "all_questions": len(subset),
            "all_annotators_unanswerable": sum(bool(r["answers"]) and all(a["unanswerable"] for a in r["answers"]) for r in subset),
            "questions_with_unmatched_evidence": sum(any(a["unmatched_evidence"] for a in r["answers"]) for r in subset)}
    return output


def load_data(folder):
    info = read(folder/"manifest.json")
    if info["version"] != VERSION:
        raise ValueError("Unknown prepared dataset version")
    verify_files(folder, info["files"])
    questions, evidence, papers = lines(folder/"clarification.jsonl"), lines(folder/"evidence.jsonl"), lines(folder/"papers.jsonl")
    check_splits(questions+evidence)
    return info, questions, read(folder/"question_bank.json"), evidence, {p["id"]: p for p in papers}


def train(folder, output):
    code_before = source_code_hashes()
    data_before = sha(folder/"manifest.json")
    info, questions, bank, evidence, papers = load_data(folder)
    output = fresh(output)
    topics, candidates = topic_cases(questions), question_candidates(bank)
    rng = np.random.default_rng(SEED)
    pairs = []
    for topic in [t for t in topics if t["split"] == "train" and t["need"] > 1]:
        x = feature_matrix(topic["request"], candidates)
        pos = [i for i, c in enumerate(candidates) if c["text"] in topic["positives"]]
        valid_neg = [i for i in ranked(x[:, 1]) if i not in pos]
        neg = valid_neg[:20]+list(rng.choice(valid_neg, min(8, len(valid_neg)), replace=False))
        for p in pos:
            pairs.extend(x[p]-x[n] for n in neg)
    weights, fit = fit_pairs(pairs)
    stage1 = {"feature_names": FEATURES, "weights": weights.tolist(), "fit": fit,
              "scope": "ClariQ question-bank relevance; not generated-option quality"}
    need = fit_need(topics)
    write(output/"question_ranker.json", stage1)
    write(output/"clarification_need.json", need)
    print("Stage 1 trained on ClariQ train topics", flush=True)

    pairs = []
    for record, candidates, gold_sets in evidence_cases([r for r in evidence if r["split"] == "train"], papers):
        x = feature_matrix(record["question"], candidates, evidence=True)
        pos = set.union(*gold_sets)
        annotated_ids = {p for a in record["answers"] if not a["unanswerable"] for p in a["evidence_ids"]}
        known_positive = {i for i, p in enumerate(candidates) if p["id"] in annotated_ids}
        neg = [int(i) for i in ranked(x[:, 1]) if int(i) not in known_positive]
        chosen = neg[:12]+list(rng.choice(neg, min(6, len(neg)), replace=False)) if neg else []
        for p in sorted(pos):
            pairs.extend(x[p]-x[n] for n in chosen)
    weights, fit = fit_pairs(pairs)
    stage2 = {"feature_names": FEATURES, "weights": weights.tolist(), "fit": fit,
              "scope": "Evidence paragraph ranking only; not answer generation or causal verification"}
    write(output/"evidence_ranker.json", stage2)
    print("Stage 2 trained on QASPER train papers", flush=True)
    results = {"version": VERSION, "seed": SEED,
        "clarification": evaluate_questions(topics, question_candidates(bank), stage1, need),
        "evidence": evaluate_evidence(evidence, papers, stage2),
        "training_ids_sha256": {"clariq": identity(sorted(t["id"] for t in topics if t["split"] == "train")),
                               "qasper": identity(sorted(r["id"] for r in evidence if r["split"] == "train"))},
        "limits": ["English public-data diagnostics, not Chinese scientific dialogue evaluation",
            "ClariQ official question bank is known during training and evaluation; no claim of unseen-question generation",
            "Independent task heads; not sequential updates to a shared LLM",
            "No LLM weights, existing planner weights, online policies or PPO rewards changed",
            "QASPER ranking reports only questions with at least one fully aligned answerable annotation",
            "No measured researcher understanding or question-option preference improvement"],
        "human_reviewed_scientific_dialogues": 0, "online_deployment": False,
        "llm_parameter_updates": 0, "model_api_calls": 0, "real_scientific_executions": 0}
    if code_before != source_code_hashes() or data_before != sha(folder/"manifest.json"):
        raise ValueError("Code or data changed during training; no completed run receipt saved")
    write(output/"results.json", results)
    write(output/"manifest.json", {"version": VERSION, "data_manifest_sha256": data_before,
        "source_code_sha256": code_before, "files": manifest(output,
            ["question_ranker.json", "clarification_need.json", "evidence_ranker.json", "results.json"]),
        "numpy_version": np.__version__, "deployment": "research_candidate_only"})
    return results


def verify_run(folder, run):
    info, questions, bank, evidence, papers = load_data(folder)
    receipt = read(run/"manifest.json")
    if receipt["data_manifest_sha256"] != sha(folder/"manifest.json") or receipt["source_code_sha256"] != source_code_hashes():
        raise ValueError("Training dataset or code differs from receipt")
    verify_files(run, receipt["files"])
    for filename in ("question_ranker.json", "evidence_ranker.json"):
        model = read(run/filename)
        if model["feature_names"] != FEATURES or len(model["weights"]) != len(FEATURES) or not np.isfinite(model["weights"]).all():
            raise ValueError("Invalid trained ranking candidate")
    result = read(run/"results.json")
    actual1 = evaluate_questions(topic_cases(questions), question_candidates(bank),
                                read(run/"question_ranker.json"), read(run/"clarification_need.json"))
    actual2 = evaluate_evidence(evidence, papers, read(run/"evidence_ranker.json"))
    if actual1 != result["clarification"] or actual2 != result["evidence"]:
        raise ValueError("Recomputed held-out metrics disagree")
    return {"passed": True, "recomputed_metrics": True, "model_api_calls": 0}
