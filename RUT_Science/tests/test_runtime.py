import unittest
from unittest.mock import patch

from rut_science.agents import RuleAgent, message, tool
from rut_science.benchmark import build_tasks, build_dialogues, response_dialogues
from rut_science.contracts import DialogueSpec
from rut_science.environment import ScientificMLEnvironment
from rut_science.evaluator import evaluate
from rut_science.runtime import run_episode
from rut_science.validation import validate_benchmark
from rut_science.research_spec import ResearchSpec
from rut_science.environment import make_initial_state


class ScriptAgent:
    def __init__(self, actions):
        self.actions = actions
        self.seen = []

    def reset(self, system_prompt, tools, seed):
        self.index = 0
        self.seen = []

    def step(self, messages):
        self.seen.append(messages)
        decision = self.actions[self.index]
        self.index += 1
        return decision


class RuntimeTests(unittest.TestCase):
    def test_future_user_turn_and_gold_not_exposed(self):
        agent = ScriptAgent([message("ready"), message("done")])
        dialogue = DialogueSpec("private_gold_id", "ideal", ("FIRST", "FUTURE_SECRET"))
        run_episode(agent, ScientificMLEnvironment(), dialogue)
        self.assertNotIn("FUTURE_SECRET", str(agent.seen[0]))
        self.assertNotIn("private_gold_id", str(agent.seen))
        self.assertNotIn("datasets", str(agent.seen))
        self.assertIn("FUTURE_SECRET", str(agent.seen[1]))

    def test_no_write_before_confirmation_and_attempt_preserved(self):
        agent = ScriptAgent([tool("split_dataset", dataset_id="ds_1", target="conductivity", train_fraction=0.6, seed=11), message("wait")])
        env = ScientificMLEnvironment()
        initial = env.snapshot()
        episode = run_episode(agent, env, DialogueSpec("x", "ideal", ("do not train",)))
        self.assertEqual(episode["final_state"], initial)
        self.assertEqual(episode["events"][1]["tool_result"]["error_code"], "permission_denied")

    def test_malformed_actions_cannot_escape_step_budget(self):
        agent = ScriptAgent([{}, {}, {}])
        episode = run_episode(agent, ScientificMLEnvironment(), DialogueSpec("x", "ideal", ("query",)), max_steps=3)
        self.assertEqual(episode["termination"], "step_limit")
        self.assertEqual(len([e for e in episode["events"] if e["event_type"] == "invalid_action"]), 3)

    def test_all_five_tasks_and_seven_context_control_variants(self):
        tasks = build_tasks()
        validate_benchmark(tasks)
        for task in tasks:
            for dialogue in build_dialogues(task):
                with self.subTest(task=task.task_id, behavior=dialogue.behavior):
                    episode = run_episode(RuleAgent("context"), ScientificMLEnvironment(), dialogue,
                                          research_spec=ResearchSpec.from_task(task, make_initial_state()))
                    self.assertTrue(evaluate(task, dialogue, episode)["execution_success"])

    def test_response_cases_have_separate_success_not_execution_sr(self):
        task = build_tasks()[0]
        for dialogue in response_dialogues(task):
            episode = run_episode(RuleAgent(), ScientificMLEnvironment(), dialogue)
            score = evaluate(task, dialogue, episode)
            self.assertTrue(score["interaction_success"])
            self.assertIsNone(score["execution_success"])

    def test_claimed_clarification_with_irrelevant_text_fails(self):
        task = build_tasks()[0]
        dialogue = response_dialogues(task)[1]
        episode = run_episode(ScriptAgent([message("今天几点？", "clarify")]), ScientificMLEnvironment(), dialogue)
        self.assertFalse(evaluate(task, dialogue, episode)["interaction_success"])

    def test_rule_latest_failure_is_authored_context_control(self):
        task = build_tasks()[0]
        validate_benchmark([task])
        dialogue = build_dialogues(task)[1]
        episode = run_episode(RuleAgent("latest"), ScientificMLEnvironment(), dialogue,
                              research_spec=ResearchSpec.from_task(task, make_initial_state()))
        self.assertFalse(evaluate(task, dialogue, episode)["execution_success"])

    def test_isolated_runs_do_not_reuse_mutated_environment(self):
        task = build_tasks()[0]
        dialogue = build_dialogues(task)[0]
        spec = ResearchSpec.from_task(task, make_initial_state())
        left = run_episode(RuleAgent(), ScientificMLEnvironment(), dialogue, research_spec=spec)
        right = run_episode(RuleAgent(), ScientificMLEnvironment(), dialogue, research_spec=spec)
        self.assertEqual(left["initial_state"], right["initial_state"])
        self.assertEqual(left["final_state"], right["final_state"])

    def test_invalid_time_budget_rejected(self):
        for value in (float("nan"), float("inf"), 0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                run_episode(RuleAgent(), ScientificMLEnvironment(), DialogueSpec("x", "ideal", ("query",)), max_seconds=value)

    def test_late_reply_cannot_claim_completion_after_deadline(self):
        # Simulate a late reply without depending on Windows timer granularity.
        with patch("rut_science.runtime.time.monotonic", side_effect=[0, .001, .001, .010, .010, .010]):
            episode = run_episode(ScriptAgent([message("completed")]), ScientificMLEnvironment(),
                                  DialogueSpec("x", "ideal", ("query",)), max_seconds=0.005)
        self.assertEqual(episode["termination"], "time_limit")
