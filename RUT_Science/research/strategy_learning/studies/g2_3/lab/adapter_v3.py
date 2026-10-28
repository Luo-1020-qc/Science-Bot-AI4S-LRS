"""Shared feature/action interface for tabular interviews and CViT job mocks."""
from copy import deepcopy
from .contracts import ACTIONS as TAB_ACTIONS, FEATURE_NAMES as TAB_FEATURES
from .environment import DesignEnvironment
from .policies import RuleV2, encode as encode_tabular
from .cvit_mock import CV_ACTIONS, CV_FIELDS, CViTMockEnvironment, CViTRule, CONFIGS

ACTIONS_V3 = tuple(TAB_ACTIONS)+tuple(action for action in CV_ACTIONS if action not in TAB_ACTIONS)
CV_FEATURES = tuple("cv_known:"+name for name in CV_FIELDS)+tuple("cv_unknown:"+name for name in CV_FIELDS)+(
    "cv_intent_chat", "cv_intent_design", "cv_intent_run", "cv_dataset_supported", "cv_target_supported", "cv_metric_supported",
    "cv_requested_pilot", "cv_requested_full", "cv_budget", "cv_profile", "cv_memory", "cv_cost_exceeds_budget", "cv_memory_insufficient",
    "cv_chosen_pilot", "cv_chosen_full", "cv_draft_current", "cv_confirmed_current", "cv_reconciled",
    "cv_job_none", "cv_job_running", "cv_job_completed", "cv_job_mismatch", "cv_job_failed", "cv_read_allowed", "cv_execute_allowed",
    "cv_refused", "cv_last_failure", "cv_turn_fraction", "cv_launches", "cv_redundant_questions")
FEATURES_V3 = ("domain_tabular", "domain_cvit")+tuple(TAB_FEATURES)+CV_FEATURES
VERSION_V3 = "g2_3_shared_decision_v1"


def encode(obs):
    if obs["domain"] == "tabular":
        return [1., 0.]+encode_tabular(obs["observation"])+[0.]*len(CV_FEATURES)
    raw = obs["observation"]
    f, p = raw["facts"], raw["profile"] or {}
    request = f.get("configuration")
    cv = [float(name in f) for name in CV_FIELDS]+[float(name in raw["unknown"]) for name in CV_FIELDS]
    cv += [float(f.get("intent") == intent) for intent in ("chat", "design", "run")]
    cv += [float(f.get("dataset") == "mock_darcy_fixture"), float(f.get("target") == "pressure_field"), float(f.get("metric") == "relative_l2")]
    cv += [float(request == "pilot"), float(request == "full"), float(f.get("budget", 0))/12, float(bool(p)), p.get("available_memory_gb", 0)/16,
           float(request in CONFIGS and CONFIGS[request]["cost"] > f.get("budget", 0)),
           float(bool(p) and request in CONFIGS and CONFIGS[request]["memory_gb"] > p["available_memory_gb"])]
    cv += [float(raw["chosen"] == name) for name in ("pilot", "full")]
    cv += [float(raw["draft_current"]), float(raw["confirmed_current"]), float(raw["reconciled"])]
    cv += [float(raw["job"] == name) for name in ("none", "running", "completed", "mismatch", "failed")]
    cv += [float(raw["read_allowed"]), float(raw["execute_allowed"]), float(raw["refused"]), float(bool(raw["last_failure"])),
           raw["turn"]/28, raw["launches"], sum(max(0, value-1) for value in raw["asked"].values())/12]
    if len(cv) != len(CV_FEATURES):
        raise ValueError("CViT feature version mismatch")
    return [0., 1.]+[0.]*len(TAB_FEATURES)+cv


class SuiteEnvironment:
    def __init__(self, task, *, record=False):
        self.domain = task["domain"]
        self.inner = DesignEnvironment(task) if self.domain == "tabular" else CViTMockEnvironment(task)
        self.record = record
        self.trace = []

    def wrap(self, raw):
        local_actions = TAB_ACTIONS if self.domain == "tabular" else CV_ACTIONS
        permitted = {action for action, allowed in zip(local_actions, raw["mask"]) if allowed}
        return {"domain": self.domain, "observation": raw, "mask": [action in permitted for action in ACTIONS_V3], "version": VERSION_V3}

    def reset(self):
        self.trace = []
        return self.wrap(self.inner.reset())

    def step(self, action):
        if type(action) is int:
            action = ACTIONS_V3[action]
        before = self.wrap(self.inner.observe())
        raw, reward, done, info = self.inner.step(action)
        after = self.wrap(raw)
        if self.record:
            self.trace.append({"observation": before, "action": action, "reward": reward, "terminal": done, "info": info})
        # The original per-domain trace is redundant in policy training. No
        # external job exists, and this clears only this environment's memory.
        self.inner.state["history"] = []
        return after, reward, done, info


class SuiteRule:
    name = "context_rule"
    def choose(self, obs):
        return (RuleV2() if obs["domain"] == "tabular" else CViTRule()).choose(obs["observation"])


def rollout(policy, task, *, record=False):
    env = SuiteEnvironment(task, record=record)
    obs = env.reset()
    total = 0.
    while not env.inner.done:
        action = policy.choose(obs)
        obs, reward, done, info = env.step(action)
        total += reward
    state = env.inner.state
    return {"task_id": task["id"], "root_group": task["root_group"], "domain": task["domain"], "scenario": task["scenario"],
            "success": info["success"], "return": total, "decisions": state["turn"], "questions": sum(state["asked"].values()),
            "blocked_attempts": state.get("blocked_execution_attempts", state.get("blocked_launches", 0)),
            "mock_launches": state.get("launches", state.get("simulated_executions", 0)),
            "duplicate_launches": max(0, state.get("launches", 0)-1), "real_executions": 0, "real_gpu_jobs": 0,
            "trace": env.trace}


def evaluate(policy, tasks):
    rows = [rollout(policy, task) for task in tasks]
    def metrics(values):
        return {"tasks": len(values), "successes": sum(v["success"] for v in values),
                "success_rate": sum(v["success"] for v in values)/len(values),
                "mean_decisions": sum(v["decisions"] for v in values)/len(values),
                "mean_questions": sum(v["questions"] for v in values)/len(values),
                "blocked_attempts": sum(v["blocked_attempts"] for v in values),
                "duplicate_mock_launches": sum(v["duplicate_launches"] for v in values),
                "real_gpu_jobs": 0, "real_executions": 0}
    result = metrics(rows)
    result["by_domain"] = {domain: metrics([v for v in rows if v["domain"] == domain]) for domain in {v["domain"] for v in rows}}
    result["by_scenario"] = {scenario: metrics([v for v in rows if v["scenario"] == scenario]) for scenario in {v["scenario"] for v in rows}}
    return result, rows
