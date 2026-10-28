"""G2.1 declarations, choices, provenance, authorization and recovery."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_tabular_g2 as fixtures
import test_general_session as model_helpers
from rut_science.util import digest, write_json
from rut_science.science_bot.session import ScienceSession
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.interview.runtime import load, save, bound_draft_valid
from rut_science.science_bot.general.interview.state import new_state, apply_fields, contract_hash
from rut_science.science_bot.general.interview.policy import observe, choose, ACTIONS


class DesignInterviewTests(unittest.TestCase):
    setUp = fixtures.TabularG2Tests.setUp
    session = fixtures.TabularG2Tests.session
    spec = fixtures.TabularG2Tests.spec
    api = model_helpers.GeneralSessionTests.api

    def answer(self, session, updates, command="/answer"):
        return session.message(command+" "+json.dumps(updates, ensure_ascii=False))

    def fields(self, design="independent"):
        return {**{k: v for k, v in self.spec(design).to_dict().items() if k != "schema_version" and v is not None},
                "unit_structure": "paired_units" if design == "paired" else "independent_rows"}

    def test_multiturn_accumulates_declarations_and_does_not_execute(self):
        session = self.session()
        first = session.message("/interview groups.csv")
        self.assertEqual(first["action"], "ask:research_question")
        self.assertEqual(session.resources()["tool_attempts"], 1)
        self.answer(session, {"research_question": "A和B的平均y是否不同"})
        second = self.answer(session, {"unit_structure": "independent_rows"})
        self.assertEqual(second["action"], "options:design")
        self.assertEqual(len(second["interview"]["pending"]["options"]), 3)
        session.message("1")
        self.answer(session, {"response": "y", "unit": "id", "provenance": "synthetic"})
        self.answer(session, {"factor": "group", "levels": ["A", "B"]})
        draft = self.answer(session, {"sampling_note": "全部现有合成样本，探索性分析"})
        self.assertTrue(draft["requires_confirmation"])
        self.assertEqual(session.tabular.spec.design, "independent")
        self.assertEqual(session.tabular.meta["completed"], {})
        self.assertFalse(session.status()["confirmed"])
        state = load(session)
        self.assertEqual(state["sources"]["response"]["kind"], "user_structured")
        self.assertNotEqual(state["sources"]["response"]["turn"], state["sources"]["sampling_note"]["turn"])
        session.confirm(session.confirmation)
        report = session.run()
        self.assertTrue(report["execution_success"])
        self.assertEqual(session.resources()["tool_attempts"], 4)
        self.assertEqual(session.resources()["llm_requests"], 0)

    def test_reply_after_restore_uses_previous_fields(self):
        session = self.session()
        session.message("/interview paired.csv")
        self.answer(session, {"research_question": "比较前后", "unit_structure": "paired_units", "design": "paired"})
        restored = ScienceSession.restore(session.folder)
        result = self.answer(restored, {k: v for k, v in self.fields("paired").items() if k not in {"research_question", "unit_structure", "design", "data_path"}})
        self.assertTrue(result["requires_confirmation"])
        restored.confirm(restored.confirmation)
        restored.run(max_steps=1)
        again = ScienceSession.restore(restored.folder)
        again.run()
        self.assertEqual(again.research_report()["metrics"]["method"], "paired_t")

    def test_conflicting_fields_require_explicit_resolution(self):
        session = self.session()
        session.message("/interview groups.csv")
        self.answer(session, {"response": "y"})
        result = self.answer(session, {"response": "other"})
        self.assertEqual(result["action"], "resolve")
        self.assertEqual(load(session)["fields"]["response"], "y")
        self.assertFalse(result["validation"]["ready"])
        self.answer(session, {"response": "y"}, "/resolve")
        self.assertFalse(load(session)["conflicts"])
        self.assertEqual(load(session)["fields"]["response"], "y")

    def test_unknown_is_not_invented_or_asked_repeatedly(self):
        session = self.session()
        session.message("/interview")
        result = session.message("不知道")
        self.assertEqual(result["action"], "stop")
        self.assertFalse(load(session)["active"])
        self.assertIn("research_question", load(session)["unknown"])
        self.assertIsNone(session.tabular)
        self.answer(session, {"research_question": "比较A与B的平均y"})
        self.assertNotIn("research_question", load(session)["unknown"])

    def test_defaults_and_user_facts_are_distinct_and_extra_keys_rejected_atomically(self):
        session = self.session()
        session.message("/interview")
        result = self.answer(session, {"response": "y", "run_shell": "command"})
        self.assertIn("未接受", result["answer"])
        state = load(session)
        self.assertNotIn("response", state["fields"])
        self.assertEqual(state["sources"]["alpha"]["kind"], "protocol_default")

    def test_structure_mismatch_and_unsupported_structure_block(self):
        for structure in ("paired_units", "temporal", "clustered"):
            session = self.session()
            session.message("/interview groups.csv")
            result = self.answer(session, {**self.fields(), "unit_structure": structure})
            self.assertFalse(result["validation"]["ready"])
            self.assertIsNone(session.tabular)
            self.assertEqual(result["action"], "stop")

    def test_changed_data_requires_refresh_and_new_draft_hash(self):
        session = self.session()
        session.message("/interview groups.csv")
        self.answer(session, self.fields())
        old = session.confirmation
        path = self.project/"groups.csv"
        path.write_text(path.read_text(encoding="utf-8").replace("u0,A,1", "u0,A,1.5"), encoding="utf-8")
        with self.assertRaises(ValueError):
            session.confirm(old)
        refreshed = session.message("/interview-refresh")
        self.assertTrue(refreshed["requires_confirmation"])
        self.assertNotEqual(session.confirmation, old)

    def test_revision_and_new_questions_revoke_confirmation(self):
        session = self.session()
        session.message("/interview groups.csv")
        self.answer(session, self.fields())
        old = session.confirmation
        result = self.answer(session, {"research_question": "另一个问题"}, "/revise")
        self.assertTrue(result["requires_confirmation"])
        self.assertNotEqual(session.confirmation, old)
        with self.assertRaises(ValueError):
            session.confirm(old)
        session.message("什么是配对检验？")
        with self.assertRaises(ValueError):
            session.confirm(session.tabular.confirmation)

    def test_same_committed_turn_replay_does_not_create_second_experiment(self):
        session = self.session()
        session.message("/interview groups.csv")
        request_text = "/answer "+json.dumps(self.fields(), ensure_ascii=False)
        result = session.message(request_text)
        before = session.resources()
        request = {"raw_text": request_text, "intent": "design", "reason": "design_interview"}
        self.assertEqual(session.dispatch(request, 2), result)
        self.assertEqual(before, session.resources())
        self.assertEqual(len(session.meta["experiments"]), 1)

    def test_model_extraction_requires_current_quotes_and_no_negative_inference(self):
        for quote, value in (("这些不是合成数据", "synthetic"), ("未提到的原文", "synthetic")):
            call = model_helpers.tool_call("record_design_fields", {"updates": [{"field": "provenance", "value_json": json.dumps(value), "quote": quote}]}, "extract_1")
            with self.api(model_helpers.envelope(calls=[call])):
                session = GeneralSession.create(self.root/"api", workspace=self.project)
                session.message("/interview")
                # No pending enum is supplied; force semantic extraction rather
                # than accepting a free-text answer to the research-question slot.
                self.answer(session, {"research_question": "比较y", "data_path": "groups.csv", "unit_structure": "independent_rows", "design": "independent", "response": "y", "unit": "id"})
                result = session.message("/answer 这些不是合成数据")
                self.assertNotIn("provenance", load(session)["fields"])
                self.assertEqual(session.model_output()["status"], "rejected")
                self.assertIsNone(session.tabular)

    def test_grounded_native_extraction_is_saved_as_user_grounded_not_model_fact(self):
        call = model_helpers.tool_call("record_design_fields", {"updates": [{"field": "provenance", "value_json": '"synthetic"', "quote": "来自合成数据"}]}, "extract_source")
        with self.api(model_helpers.envelope(calls=[call])) as (network, bodies):
            session = GeneralSession.create(self.root/"api", workspace=self.project)
            session.message("/interview groups.csv")
            self.answer(session, {"research_question": "比较y", "unit_structure": "independent_rows", "design": "independent", "response": "y", "unit": "id"})
            session.message("/answer 来自合成数据")
            self.assertEqual(network.call_count, 1)
            state = load(session)
            self.assertEqual(state["fields"]["provenance"], "synthetic")
            self.assertEqual(state["sources"]["provenance"]["kind"], "user_grounded_model")
            self.assertNotIn("group", json.dumps(bodies[0]))

    def test_policy_mask_blocks_prepare_and_cannot_be_overridden(self):
        state = new_state()
        observation = observe(state)
        self.assertFalse(observation["mask"][ACTIONS.index("prepare")])
        class Bad:
            def choose(self, _obs):
                return "prepare"
        with self.assertRaises(ValueError):
            choose(state, policy=Bad())

    def test_feedback_pending_review_does_not_change_policy(self):
        session = self.session()
        session.message("/interview")
        session.message('/design-feedback {"rating":5,"note":"希望问题更简洁"}')
        state = load(session)
        self.assertEqual(state["feedback"][0]["review_status"], "pending_human_review")
        self.assertEqual(state["policy"], "rule")

    def test_cancel_and_budget_do_not_create_experiments(self):
        session = self.session()
        session.message("/interview")
        session.cancel()
        with self.assertRaises(ValueError):
            session.run()
        state = load(session)
        state["turns"] = 24
        save(session, state)
        result = session.message('/answer {"research_question":"比较y"}')
        self.assertEqual(result["action"], "stop")
        self.assertIsNone(session.tabular)

    def test_saved_interview_tampering_is_detected(self):
        session = self.session()
        session.message("/interview")
        state = load(session)
        state["fields"]["provenance"] = "synthetic"
        write_json(session.folder/session.meta["interview_ref"], state)
        with self.assertRaises(ValueError):
            ScienceSession.restore(session.folder)

    def test_context_switch_does_not_consume_followup_as_old_field(self):
        session = self.session()
        session.message("/interview groups.csv")
        session.message("什么是区组设计？")
        self.assertFalse(load(session)["active"])
        result = session.message("1")
        self.assertNotEqual(session.meta["active_task"], "design_interview")
        self.assertNotIn("research_question", load(session)["fields"])
        resumed = session.message("/interview")
        self.assertEqual(resumed["action"], "ask:research_question")

    def test_missing_policy_reject_is_not_asked_again_after_explicit_choice(self):
        session = self.session()
        path = self.project/"groups.csv"
        path.write_text(path.read_text(encoding="utf-8").replace("u0,A,1", "u0,A,NA"), encoding="utf-8")
        session.message("/interview groups.csv")
        fields = self.fields()
        fields.pop("missing_policy")
        result = self.answer(session, fields)
        self.assertEqual(result["action"], "ask:missing_policy")
        blocked = session.message("1")
        self.assertEqual(blocked["action"], "stop")
        self.assertIsNone(session.tabular)
        accepted = self.answer(session, {"missing_policy": "drop_complete_case"}, "/revise")
        self.assertTrue(accepted["requires_confirmation"])
        self.assertEqual(session.tabular.meta["validation"]["missing_units"], 1)

    def test_no_workspace_no_files_and_no_implicit_numeric_environment(self):
        session = GeneralSession.create(self.root/"none", backend="offline")
        result = session.message("设计一个实验")
        self.assertEqual(result["intent"], "design")
        self.assertIsNone(session.env)
        self.assertIsNone(session.tabular)
        self.assertEqual(session.resources()["tool_attempts"], 0)
        bad = session.message("/interview groups.csv")
        self.assertIn("Workspace", bad["answer"])

    def test_policy_checkpoint_switch_is_explicit_and_does_not_change_permissions(self):
        session = self.session()
        session.message("/interview-policy bc")
        self.assertEqual(session.meta["interview_policy"], "bc")
        result = session.message("/interview groups.csv")
        self.assertIn(result["action"], ACTIONS)
        self.assertIsNone(session.tabular)
        session.message("/interview-policy rule")
        self.assertEqual(session.meta["interview_policy"], "rule")

    def test_options_listing_does_not_clear_unknown_or_bypass_validation(self):
        session = self.session()
        session.message("/interview")
        session.message("不知道")
        session.message("/interview-options")
        self.assertIn("research_question", load(session)["unknown"])
        self.assertIsNone(session.tabular)

    def test_tight_tool_budget_and_prediction_interview(self):
        session = self.session(limits={"tool_calls": 7})
        session.message("/interview prediction.csv")
        result = self.answer(session, self.fields("prediction"))
        self.assertTrue(result["requires_confirmation"])
        session.confirm(session.confirmation)
        report = session.run()
        self.assertEqual(report["metrics"]["selected"], "ols")
        self.assertEqual(session.resources()["tool_attempts"], 7)


if __name__ == "__main__":
    unittest.main()
