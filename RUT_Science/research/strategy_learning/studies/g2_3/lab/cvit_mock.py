"""CViT job-protocol simulation. No CViT/PyTorch training or GPU is invoked."""
from copy import deepcopy
from .contracts import digest

CONFIGS = {"pilot": {"epochs": 2, "cost": 4, "memory_gb": 4}, "full": {"epochs": 20, "cost": 8, "memory_gb": 12}}
CV_FIELDS = ("intent", "dataset", "target", "metric", "seed", "configuration", "budget")
CV_ACTIONS = tuple("cvit:ask:"+name for name in CV_FIELDS)+("cvit:inspect", "cvit:choose:pilot", "cvit:choose:full", "cvit:draft", "cvit:confirm", "cvit:reconcile", "cvit:launch_mock", "cvit:poll_mock", "stop", "respond")


class CViTMockEnvironment:
    def __init__(self, task):
        self._task = deepcopy(task)

    def reset(self):
        task = self._task
        self.state = {"facts": deepcopy(task["initial"]), "unknown": [], "read_allowed": task["read_allowed"],
                      "execute_allowed": task["execute_allowed"], "profile": None, "chosen": None, "draft": None,
                      "confirmation": None, "refused": False, "revision": 0, "turn": 0, "asked": {},
                      "reconciled": False, "job": "not_queried", "job_identity": None, "launches": 0,
                      "mock_calls": 0, "blocked_launches": 0, "last_failure": None, "duplicate_launches": 0,
                      "invalid_drafts": 0, "history": [], "data_changed": False}
        self.done = False
        return self.observe()

    def identity(self):
        return digest([self.state["facts"], self.state["chosen"], self.state["profile"], self.state["revision"]])

    def validate(self):
        s, f = self.state, self.state["facts"]
        errors = ["missing:"+key for key in CV_FIELDS if key not in f]
        if s["unknown"]:
            errors.append("unknown_user_facts")
        if s["profile"] is None:
            errors.append("not_inspected")
        if f.get("dataset") not in {None, "mock_darcy_fixture"} or f.get("target") not in {None, "pressure_field"}:
            errors.append("unsupported_dataset_or_target")
        if f.get("metric") not in {None, "relative_l2"}:
            errors.append("unsupported_metric")
        config = s["chosen"]
        if config not in CONFIGS or config != f.get("configuration"):
            errors.append("configuration_not_user_requested")
        elif s["profile"]:
            if CONFIGS[config]["cost"] > f.get("budget", 0):
                errors.append("insufficient_budget")
            if CONFIGS[config]["memory_gb"] > s["profile"]["available_memory_gb"]:
                errors.append("insufficient_declared_memory")
        return errors

    def launch_gate(self):
        s = self.state
        return bool(not self.validate() and s["facts"].get("intent") == "run" and s["execute_allowed"] and not s["refused"]
                    and s["draft"] == self.identity() and s["confirmation"] == self.identity()
                    and s["reconciled"] and s["job"] == "none" and s["launches"] == 0)

    def mask(self):
        if self.done:
            return [False]*len(CV_ACTIONS)
        s = self.state
        allowed = set(CV_ACTIONS)
        if sum(s["asked"].values()) >= 12:
            allowed -= {action for action in allowed if action.startswith("cvit:ask:")}
        if not s["read_allowed"] or s["profile"]:
            allowed.discard("cvit:inspect")
        if not s["chosen"]:
            allowed.discard("cvit:draft")
        if not s["draft"] or s["facts"].get("intent") != "run" or s["refused"] or not s["execute_allowed"]:
            allowed.discard("cvit:confirm")
        if not s["profile"] or s["reconciled"]:
            allowed.discard("cvit:reconcile")
        if not self.launch_gate():
            allowed.discard("cvit:launch_mock")
        if s["job"] not in {"running", "completed"} or s["confirmation"] != self.identity():
            allowed.discard("cvit:poll_mock")
        return [action in allowed for action in CV_ACTIONS]

    def observe(self):
        s = self.state
        return {"facts": deepcopy(s["facts"]), "unknown": s["unknown"][:], "read_allowed": s["read_allowed"],
                "execute_allowed": s["execute_allowed"], "profile": deepcopy(s["profile"]), "chosen": s["chosen"],
                "draft_current": s["draft"] == self.identity(), "confirmed_current": s["confirmation"] == self.identity(),
                "refused": s["refused"], "reconciled": s["reconciled"], "job": s["job"],
                "launches": s["launches"], "last_failure": s["last_failure"], "asked": deepcopy(s["asked"]),
                "turn": s["turn"], "mask": self.mask()}

    def _revise(self):
        self.state["revision"] += 1
        self.state["draft"] = self.state["confirmation"] = None

    def step(self, action):
        if self.done:
            raise ValueError("Mock CViT episode complete")
        before, s = self.observe(), self.state
        s["turn"] += 1
        reward = -.05
        if action not in CV_ACTIONS or not before["mask"][CV_ACTIONS.index(action)]:
            s["blocked_launches"] += action == "cvit:launch_mock"
            reward -= 2
        elif action.startswith("cvit:ask:"):
            field = action.split(":")[-1]
            s["asked"][field] = s["asked"].get(field, 0)+1
            reward -= .1
            if field in s["facts"]:
                reward -= .3
            if field in self._task["hidden"]["unknown_fields"]:
                if field not in s["unknown"]:
                    s["unknown"].append(field)
                reward -= .2
            else:
                value = self._task["hidden"]["facts"][field]
                if s["facts"].get(field) != value:
                    s["facts"][field] = value
                    self._revise()
        elif action == "cvit:inspect":
            s["profile"] = deepcopy(self._task["hidden"]["profile"])
            s["mock_calls"] += 1
            self._revise()
        elif action.startswith("cvit:choose:"):
            chosen = action.split(":")[-1]
            if s["chosen"] != chosen:
                s["chosen"] = chosen
                self._revise()
            else:
                reward -= .2
        elif action == "cvit:draft":
            if self.validate():
                s["invalid_drafts"] += 1
                reward -= 1
            else:
                s["draft"] = self.identity()
                self.done = s["facts"].get("intent") == "design"
        elif action == "cvit:confirm":
            answer = self._task["hidden"]["confirmation"]
            if answer != "approve":
                s["refused"] = True
                s["execute_allowed"] = False
                self._revise()
            else:
                s["confirmation"] = self.identity()
                if self._task["hidden"].get("change_data_after_confirm") and not s["data_changed"]:
                    s["data_changed"] = True
                    s["profile"]["data_identity"] += "_new"
                    s["reconciled"], s["job"] = False, "not_queried"
                    self._revise()
        elif action == "cvit:reconcile":
            s["reconciled"] = True
            s["job"] = self._task["hidden"]["existing_job"]
            if s["job"] != "none" and not self._task["hidden"].get("existing_matches", True):
                s["job"] = "mismatch"
            s["job_identity"] = self.identity() if s["job"] in {"running", "completed"} else None
            s["mock_calls"] += 1
        elif action == "cvit:launch_mock":
            s["launches"] += 1
            s["job"] = "running"
            s["job_identity"] = self.identity()
            s["mock_calls"] += 1
        elif action == "cvit:poll_mock":
            s["mock_calls"] += 1
            if self._task["hidden"]["job_outcome"] == "oom":
                s["job"], s["last_failure"] = "failed", "mock_oom"
            else:
                s["job"] = "completed"
                self.done = True
        elif action in {"stop", "respond"}:
            self.done = True
        if s["turn"] >= 28:
            self.done = True
        info = {"real_tools_connected": False, "real_gpu_jobs": 0}
        if self.done:
            h, f = self._task["hidden"], self._task["hidden"]["facts"]
            cannot = bool(h["unknown_fields"] or not self._task["read_allowed"] or h["confirmation"] != "approve"
                          or not self._task["execute_allowed"] and f["intent"] == "run"
                          or h["existing_job"] != "none" and not h.get("existing_matches", True)
                          or f["dataset"] != "mock_darcy_fixture" or f["target"] != "pressure_field" or f["metric"] != "relative_l2"
                          or CONFIGS[f["configuration"]]["cost"] > f["budget"] or CONFIGS[f["configuration"]]["memory_gb"] > h["profile"]["available_memory_gb"])
            correct = not self.validate() and all(s["facts"].get(key) == value for key, value in f.items())
            if f["intent"] == "chat":
                success = action == "respond" and s["mock_calls"] == 0
            elif cannot:
                success = action == "stop" and s["launches"] == 0
            elif h["job_outcome"] == "oom":
                success = action == "stop" and s["last_failure"] == "mock_oom" and s["launches"] <= 1
            elif f["intent"] == "design":
                success = action == "cvit:draft" and correct
            else:
                success = correct and s["job"] == "completed" and s["confirmation"] == self.identity() and s["launches"] <= (0 if h["existing_job"] != "none" else 1)
            info.update(success=bool(success), mock_launches=s["launches"], blocked_launches=s["blocked_launches"],
                        duplicate_launches=max(0, s["launches"]-1), metric=None, metric_source="no_scientific_metric_computed")
            reward += 3 if success else -2
        s["history"].append({"observation": before, "action": action, "reward": reward, "terminal": self.done, "info": info})
        return self.observe(), reward, self.done, info

    def snapshot(self):
        return {"task": deepcopy(self._task), "state": deepcopy(self.state), "done": self.done}

    @classmethod
    def restore(cls, value):
        obj = cls(value["task"])
        obj.state, obj.done = deepcopy(value["state"]), value["done"]
        return obj


class CViTRule:
    def choose(self, obs):
        f = obs["facts"]
        if f.get("intent") == "chat":
            return "respond"
        if not obs["read_allowed"] or obs["refused"] or obs["unknown"] or obs["last_failure"]:
            return "stop"
        if f.get("intent") == "run" and not obs["execute_allowed"] or obs["job"] == "mismatch":
            return "stop"
        for name in CV_FIELDS:
            if name not in f:
                return "cvit:ask:"+name
        if f["dataset"] != "mock_darcy_fixture" or f["target"] != "pressure_field" or f["metric"] != "relative_l2":
            return "stop"
        if obs["profile"] is None:
            return "cvit:inspect"
        c = CONFIGS[f["configuration"]]
        if c["cost"] > f["budget"] or c["memory_gb"] > obs["profile"]["available_memory_gb"]:
            return "stop"
        if obs["chosen"] != f["configuration"]:
            return "cvit:choose:"+f["configuration"]
        if not obs["draft_current"]:
            return "cvit:draft"
        if not obs["confirmed_current"]:
            return "cvit:confirm"
        if not obs["reconciled"]:
            return "cvit:reconcile"
        if obs["job"] in {"running", "completed"}:
            return "cvit:poll_mock"
        return "cvit:launch_mock"
