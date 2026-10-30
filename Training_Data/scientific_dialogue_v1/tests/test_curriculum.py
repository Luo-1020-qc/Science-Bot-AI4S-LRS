"""Offline boundary tests: source alignment, leakage, review gates, and training isolation."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import archive_json, check_splits, import_clarq, qasper
from annotation import audit_shells, import_reviewed, partition, template, validate_dialogue
from common import VERSION, identity, jsonl, lines, manifest, read, sha, verify_files, write
from exports import export_sft
from models import feature_matrix, fit_need, fit_pairs, topic_cases


def paper(question_id="q1", answer=None):
    if answer is None:
        answer = {"unanswerable": False, "yes_no": False, "free_form_answer": "",
                  "extractive_spans": [], "evidence": ["Evidence paragraph."]}
    return {"title": "Synthetic test paper", "abstract": "Synthetic abstract.",
        "full_text": [{"section_name": "Methods", "paragraphs": ["Evidence paragraph.", "Other paragraph."]}],
        "figures_and_tables": [], "qas": [{"question_id": question_id, "question": "Was it tested?",
            "answers": [{"annotation_id": "a1", "answer": answer}]}]}


def archive(path, name, value):
    body = json.dumps(value).encode()
    with tarfile.open(path, "w:gz") as output:
        member = tarfile.TarInfo(name)
        member.size = len(body)
        output.addfile(member, io.BytesIO(body))


def reviewed(group="independent-study-1"):
    row = template()
    row.update(dialogue_id="test-reviewed-1", source_group=group)
    row["provenance"].update(kind="human_authored", author_id="unit-test-fictional", paper_ids=[])
    row["consent"] = {"training_allowed": True, "deidentified": True}
    row["messages"] = [
        {"role": "user", "content": "Compare models on the same synthetic distribution."},
        {"role": "assistant", "content": "Which scope? Same distribution; New distribution; Unsure; Other"},
        {"role": "user", "content": "Same distribution"},
        {"role": "assistant", "content": "The scope is the same distribution; sample size remains unknown."}]
    row["decisions"] = [{"assistant_turn": 1, "action": "ask", "target_field": "scope",
        "based_on_user_turns": [0], "question": "Which scope?", "evidence_ids": [],
        "options": [{"id": "a", "type": "proposal", "label": "Same distribution"},
                    {"id": "b", "type": "proposal", "label": "New distribution"},
                    {"id": "u", "type": "unknown", "label": "Unsure"},
                    {"id": "c", "type": "custom", "label": "Other"}]},
        {"assistant_turn": 3, "action": "draft", "target_field": "scope", "based_on_user_turns": [0, 2], "evidence_ids": []}]
    row["plan_declarations"] = [{"field": "scope", "status": "declared", "value": "Same distribution", "user_turn": 2},
                                {"field": "sampling", "status": "unknown", "value": None}]
    row["review"].update(decision="approved", reviewer_id="unit-test-fictional",
        reviewed_at="2026-10-30T10:00:00+08:00", question_quality=4, plan_testability=3,
        notes="Synthetic unit-test fixture; never training evidence.")
    return row


class NativeAdapterTests(unittest.TestCase):
    def test_source_group_leakage_rejected(self):
        rows = [{"id": "a", "source": "qasper", "source_group": "paper:1", "split": "train"},
                {"id": "b", "source": "qasper", "source_group": "paper:1", "split": "test"}]
        with self.assertRaises(ValueError):
            check_splits(rows)

    def test_relabeling_id_does_not_hide_duplicate_request(self):
        rows = [{"id": "a", "source": "clariq", "request": "Same request", "source_group": "a", "split": "train"},
                {"id": "b", "source": "clariq", "request": "same request", "source_group": "b", "split": "dev"}]
        with self.assertRaises(ValueError):
            check_splits(rows)

    def test_topic_request_variants_preserve_common_group(self):
        base = {"source_group": "topic:1", "split": "test", "clarification_need": 2, "question": "Which version?"}
        rows = [dict(base, request="Tell me about X"), dict(base, request="More on X")]
        cases = topic_cases(rows)
        self.assertEqual(len(cases), 2)
        self.assertEqual(len({c["source_group"] for c in cases}), 1)

    def test_archive_never_extracts_traversal_member(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"unsafe.tgz"
            archive(path, "../dataset.json", {})
            with self.assertRaises(ValueError):
                archive_json(path, "dataset.json")
            self.assertFalse((Path(temp)/"dataset.json").exists())

    def test_false_yes_no_and_unmatched_evidence_survive(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with tarfile.open(folder/"qasper_train_dev.tgz", "w:gz") as output:
                for split in ("train", "dev"):
                    p = paper(split, {"unanswerable": False, "yes_no": False,
                        "evidence": ["Evidence paragraph.", "Absent evidence."]})
                    body = json.dumps({split: p}).encode()
                    member = tarfile.TarInfo("qasper-"+split+"-v0.3.json")
                    member.size = len(body)
                    output.addfile(member, io.BytesIO(body))
            archive(folder/"qasper_test.tgz", "qasper-test-v0.3.json", {"test": paper("test")})
            rows, _ = qasper(folder)
            self.assertEqual(rows[0]["answers"][0]["text"], "no")
            self.assertEqual(rows[0]["answers"][0]["evidence_ids"], ["s0:p0"])
            self.assertEqual(rows[0]["answers"][0]["unmatched_evidence"], ["Absent evidence."])

    def test_clarq_original_answer_is_never_clarification_reply(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for split in ("train", "test"):
                jsonl(folder/(split+".json"), [{"id": split, "context": split+" context", "cquestion": "Which system?", "answer": "Original post's final answer"}])
            import_clarq(folder/"train.json", folder/"test.json", folder/"out")
            self.assertTrue(all(r["user_reply"] is None for r in lines(folder/"out/clarq.jsonl")))

    def test_clarq_train_test_overlap_rejects_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for split in ("train", "test"):
                jsonl(folder/(split+".json"), [{"context": "same post", "cquestion": "Which system?"}])
            with self.assertRaises(ValueError):
                import_clarq(folder/"train.json", folder/"test.json", folder/"out")
            self.assertFalse((folder/"out").exists())


class TrainingIsolationTests(unittest.TestCase):
    def test_missing_native_section_name_is_not_a_failure(self):
        x = feature_matrix("model", [{"text": "model result", "section": None}], evidence=True)
        self.assertEqual(x.shape, (1, 16))

    def test_artifact_manifest_cannot_escape_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"outside.json"
            write(path, {"outside": True})
            with self.assertRaises(ValueError):
                verify_files(Path(temp)/"data", {"../outside.json": sha(path)})

    def test_dev_test_labels_do_not_change_need_training(self):
        rows = [{"split": "train", "request": "model comparison", "need": 2},
                {"split": "train", "request": "data source", "need": 3},
                {"split": "test", "request": "held out", "need": 1}]
        before = fit_need(rows)
        rows[-1].update(need=4, request="modified held out")
        self.assertEqual(before, fit_need(rows))

    def test_ranking_learns_actual_parameter_updates(self):
        candidates = [{"text": "Which model comparison?"}, {"text": "What food?"}]
        x = feature_matrix("model comparison", candidates)
        weights, fit = fit_pairs([x[0]-x[1]])
        self.assertGreater(float((x[0]-x[1]) @ weights), 0)
        self.assertGreater(fit["parameter_l2_change"], 0)

    def test_existing_artifacts_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"result.json"
            write(path, {"original": True})
            before = sha(path)
            with self.assertRaises(FileExistsError):
                write(path, {"original": False})
            self.assertEqual(sha(path), before)


class HumanReviewTests(unittest.TestCase):
    def test_valid_fixture_is_accepted(self):
        self.assertTrue(validate_dialogue(reviewed()))

    def test_pending_template_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_dialogue(template())

    def test_review_gate_required(self):
        row = reviewed()
        row["review"]["decision"] = "pending"
        with self.assertRaises(ValueError):
            validate_dialogue(row)

    def test_timezone_required(self):
        row = reviewed()
        row["review"]["reviewed_at"] = "2026-10-30T10:00:00"
        with self.assertRaises(ValueError):
            validate_dialogue(row)

    def test_consent_required(self):
        row = reviewed()
        row["consent"]["training_allowed"] = False
        with self.assertRaises(ValueError):
            validate_dialogue(row)

    def test_future_user_answer_not_available_to_prior_question(self):
        row = reviewed()
        row["decisions"][0]["based_on_user_turns"] = [2]
        with self.assertRaises(ValueError):
            validate_dialogue(row)

    def test_missing_unknown_choice_rejected(self):
        row = reviewed()
        row["decisions"][0]["options"][2]["type"] = "proposal"
        with self.assertRaises(ValueError):
            validate_dialogue(row)

    def test_unknown_cannot_be_filled_as_fact(self):
        row = reviewed()
        row["plan_declarations"][1]["value"] = "n=100"
        with self.assertRaises(ValueError):
            validate_dialogue(row)

    def test_declared_fact_needs_user_grounding(self):
        row = reviewed()
        row["plan_declarations"][0]["value"] = "Invented data"
        with self.assertRaises(ValueError):
            validate_dialogue(row)

    def test_nonexistent_citation_rejected(self):
        row = reviewed()
        row["decisions"][0]["evidence_ids"] = ["imaginary"]
        with self.assertRaises(ValueError):
            validate_dialogue(row)

    def test_unmeasured_understanding_not_scored(self):
        row = reviewed()
        row["understanding"]["status"] = "assessed"
        with self.assertRaises(ValueError):
            validate_dialogue(row)

    def test_credential_pattern_rejected(self):
        row = reviewed()
        row["messages"][0]["content"] += " api_key=REDACT_BEFORE_IMPORT"
        with self.assertRaises(ValueError):
            validate_dialogue(row)

    def test_duplicate_paper_cannot_cross_partitions(self):
        groups = {}
        for index in range(100):
            name = "group-"+str(index)
            groups.setdefault(partition(name), name)
        a, b = reviewed(groups["train"]), reviewed(groups["test"])
        b["dialogue_id"] = "second"
        b["messages"][0]["content"] = "Different initial request."
        for row in (a, b):
            row["provenance"]["paper_ids"] = ["shared-paper"]
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            jsonl(folder/"input.jsonl", [a, b])
            with self.assertRaises(ValueError):
                import_reviewed(folder/"input.jsonl", folder/"out")
            self.assertFalse((folder/"out").exists())

    def test_import_retains_provenance_without_review_labels_in_model_input(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            row = reviewed()
            jsonl(folder/"input.jsonl", [row])
            result = import_reviewed(folder/"input.jsonl", folder/"out")
            split = partition(row["source_group"])
            exported = lines(folder/"out"/(split+".sft.jsonl"))[0]
            self.assertEqual(result["reviewed_dialogues"], 1)
            self.assertNotIn("reviewer_id", json.dumps(exported))
            self.assertEqual(exported["messages"], row["messages"])

    def test_shells_seed_pending_queue_without_invented_dialogue(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/"source"
            row = {"scenario_name": "Synthetic fixture", "domain": "test", "skeleton": "S1",
                   "executable": True, "survey_questions": ["What unit?"], "rubric": ["Unit known"]}
            write(source/"shells_json/s1_fixture.json", row)
            write(source/"shells/s1_fixture.yaml", row)
            write(source/"shells_json/index.json", {"by_skeleton": {"S1": {"scenarios": [
                {"file": "s1_fixture.json", "sha256": sha(source/"shells_json/s1_fixture.json")} ]}}})
            before = sha(source/"shells_json/s1_fixture.json")
            result = audit_shells(source, Path(temp)/"out")
            self.assertEqual(result["training_eligible_reviewed_dialogues"], 0)
            pending = lines(Path(temp)/"out/pending.jsonl")[0]
            self.assertEqual(pending["messages"], [])
            self.assertFalse(pending["consent"]["training_allowed"])
            self.assertEqual(sha(source/"shells_json/s1_fixture.json"), before)


class ExportTests(unittest.TestCase):
    def test_sft_export_excludes_private_facet_and_preserves_unanswerable(self):
        with tempfile.TemporaryDirectory() as temp:
            data, output = Path(temp)/"data", Path(temp)/"out"
            q = {"id": "c1", "source": "clariq", "source_group": "topic:1", "split": "train",
                 "request": "Compare models", "question": "What scope?", "clarification_need": 2,
                 "private_facet_description": "PRIVATE_FACET", "user_reply": "PRIVATE_REPLY"}
            e = {"id": "q1", "source": "qasper", "paper_id": "p1", "source_group": "paper:1",
                 "split": "train", "question": "Was this measured?", "answers": [{"unanswerable": True,
                 "text": "", "evidence_ids": [], "unmatched_evidence": []}]}
            jsonl(data/"clarification.jsonl", [q])
            jsonl(data/"evidence.jsonl", [e])
            jsonl(data/"papers.jsonl", [{"id": "p1", "title": "Fixture", "paragraphs": []}])
            write(data/"question_bank.json", {"q": "What scope?"})
            write(data/"manifest.json", {"version": VERSION, "files": manifest(data,
                ["clarification.jsonl", "evidence.jsonl", "papers.jsonl", "question_bank.json"])})
            export_sft(data, output)
            text = (output/"stage1_train.jsonl").read_text()
            self.assertNotIn("PRIVATE_FACET", text)
            self.assertNotIn("PRIVATE_REPLY", text)
            answer = json.loads(lines(output/"stage2_train.jsonl")[0]["messages"][-1]["content"])
            self.assertEqual(answer["status"], "unanswerable")
            self.assertEqual(answer["answer"], "")


if __name__ == "__main__":
    unittest.main()
