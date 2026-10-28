"""V2 interview environment: semantic choices remain unmasked and observable.

Masks enforce permissions and job identity. They do not tell the policy which
question or method is scientifically suitable; the frozen verifier grades that.
"""
from copy import deepcopy
from .contracts import ACTIONS, FIELDS, VERSION
from .verifier import contract_id, validate_design, execution_gate, grade_terminal
from .mock_tools import MockTools


class DesignEnvironment:
    def __init__(self, task):
        if task.get("schema_version") != "g2_2_task_v2":
            raise ValueError("Unsupported task")
        self._task = deepcopy(task)
        self.done = False

    def reset(self):
        task = self._task
        self.tools = MockTools(task["hidden"]["profile"], task["hidden"]["inspection_mode"])
        self.state = {"facts": deepcopy(task["initial"]), "sources": {key: "initial_user_declaration" for key in task["initial"]},
                      "unknown": [], "conflicts": {}, "profile": None, "method": None, "draft": None, "confirmation": None,
                      "revision": 0, "permissions": deepcopy(task["initial_permissions"]), "turn": 0,
                      "remaining_questions": task["question_budget"], "remaining_resource": task["resource_budget"],
                      "question_limit": task["question_budget"], "resource_limit": task["resource_budget"],
                      "asked": {}, "last_failure": None, "confirmation_refused": False,
                      "blocked_execution_attempts": 0, "simulated_executions": 0, "mock_calls": 0,
                      "redundant_questions": 0, "unanswerable_questions": 0, "rejected_designs": 0,
                      "events_applied": [], "history": [], "errors": []}
        self.done = False
        return self.observe()

    def _revise(self):
        self.state["revision"] += 1
        self.state["draft"] = self.state["confirmation"] = None

    def mask(self):
        state = self.state
        if self.done:
            return [False]*len(ACTIONS)
        allowed = set(ACTIONS)
        if state["remaining_questions"] <= 0:
            allowed -= {action for action in ACTIONS if action.startswith("ask:")}
        if state["permissions"]["read"] is not True or state["remaining_resource"] < 1:
            allowed -= {"inspect", "retry_inspect"}
        if state["last_failure"] != "transient_timeout" or self.tools.inspections >= 2:
            allowed.discard("retry_inspect")
        if self.tools.inspections or state["profile"]:
            allowed.discard("inspect")
        if not state["conflicts"]:
            allowed.discard("resolve")
        if not state["method"]:
            allowed.discard("draft")
        if not state["draft"] or state["facts"].get("intent") != "run" or state["permissions"]["execute"] is not True or state["confirmation_refused"]:
            allowed.discard("request_confirmation")
        if not execution_gate(state):
            allowed.discard("execute_mock")
        return [action in allowed for action in ACTIONS]

    def observe(self):
        state = self.state
        return {"version": VERSION, "facts": deepcopy(state["facts"]), "unknown": state["unknown"][:],
                "permissions": deepcopy(state["permissions"]), "profile": deepcopy(state["profile"]),
                "conflicts": deepcopy(state["conflicts"]), "method": state["method"],
                "draft_valid": bool(state["draft"] and state["draft"]["contract_id"] == contract_id(state)),
                "confirmed_current": state["confirmation"] == contract_id(state),
                "confirmation_refused": state["confirmation_refused"], "last_failure": state["last_failure"],
                "remaining_questions": state["remaining_questions"], "remaining_resource": state["remaining_resource"],
                "turn": state["turn"], "asked": deepcopy(state["asked"]), "errors": state["errors"][:], "mask": self.mask()}

    def _events(self):
        for i, event in enumerate(self._task["hidden"]["events"]):
            if i in self.state["events_applied"]:
                continue
            if event["when"] == "after_first_question" and sum(self.state["asked"].values()) >= 1:
                self.state["events_applied"].append(i)
                for name, value in event["fields"].items():
                    old = self.state["facts"].get(name)
                    self.state["conflicts"][name] = {"previous": old, "user_proposed": deepcopy(value)}
                self._revise()

    def step(self, action):
        if self.done:
            raise ValueError("Episode is complete")
        before = self.observe()
        self.state["turn"] += 1
        reward = -.05
        if type(action) is not str or action not in ACTIONS or not before["mask"][ACTIONS.index(action)]:
            if action == "execute_mock":
                self.state["blocked_execution_attempts"] += 1
            self.state["errors"] = ["action_blocked_by_host"]
            reward -= 2
            if self.state["turn"] >= 24:
                self.done = True
            return self._finish(before, action, reward)
        self.state["errors"] = []
        if action.startswith("ask:"):
            field = action[4:]
            self.state["remaining_questions"] -= 1
            self.state["asked"][field] = self.state["asked"].get(field, 0)+1
            reward -= .1
            if field.endswith("_permission"):
                key = "read" if field == "read_permission" else "execute"
                if self.state["permissions"][key] is not None:
                    self.state["redundant_questions"] += 1; reward -= .3
                new_value = self._task["hidden"]["read_permission" if key == "read" else "execute_permission"]
                if self.state["permissions"][key] != new_value:
                    self._revise()
                self.state["permissions"][key] = new_value
            elif field in self._task["hidden"]["unknown_fields"]:
                if field not in self.state["unknown"]:
                    self.state["unknown"].append(field)
                self.state["unanswerable_questions"] += 1; reward -= .2
            else:
                truth = self._task["hidden"]["facts"]
                value = deepcopy(truth[field])
                if field in self.state["facts"]:
                    self.state["redundant_questions"] += 1; reward -= .3
                if self.state["facts"].get(field) != value:
                    self.state["facts"][field] = value
                    self.state["sources"][field] = "simulated_user_answer"
                    self._revise()
            self._events()
        elif action in {"inspect", "retry_inspect"}:
            self.state["remaining_resource"] -= 1
            self.state["mock_calls"] += 1
            result = self.tools.inspect()
            if result["status"] == "error":
                self.state["last_failure"] = result["error_type"]
            elif result["profile"].get("schema_version") != "mock_csv_profile_v1":
                self.state["last_failure"] = "invalid_schema"
                self.state["errors"] = ["mock_tool_schema_rejected"]
            else:
                self.state["last_failure"] = None
                self.state["profile"] = result["profile"]
                self._revise()
        elif action == "resolve":
            for field, values in self.state["conflicts"].items():
                self.state["facts"][field] = deepcopy(values["user_proposed"])
                self.state["sources"][field] = "explicit_simulated_user_correction"
            self.state["conflicts"] = {}
            self._revise()
        elif action.startswith("choose:"):
            new_method = action.split(":")[1]
            if self.state["method"] != new_method:
                self.state["method"] = new_method
                self._revise()
            else:
                reward -= .2
        elif action == "draft":
            validation = validate_design(self.state)
            if not validation["valid"]:
                self.state["errors"] = validation["blockers"]
                self.state["rejected_designs"] += 1
                reward -= 1
            else:
                self.state["draft"] = {"contract_id": contract_id(self.state), "method": self.state["method"], "simulated": True}
                if self.state["facts"].get("intent") == "design":
                    self.done = True
        elif action == "request_confirmation":
            answer = self._task["hidden"]["confirmation"]
            if answer == "approve":
                self.state["confirmation"] = contract_id(self.state)
            else:
                self.state["confirmation_refused"] = True
                if answer == "revoke":
                    self.state["permissions"]["execute"] = False
                    self._revise()
        elif action == "execute_mock":
            cost = self.state["profile"]["estimated_execution_cost"]
            self.state["remaining_resource"] -= cost
            self.tools.execute(self.state["draft"])
            self.state["mock_calls"] += 1
            self.state["simulated_executions"] += 1
            self.done = True
        elif action in {"respond", "stop"}:
            self.done = True
        if self.state["turn"] >= 24:
            self.done = True
        return self._finish(before, action, reward)

    def _finish(self, before, action, reward):
        info = {"simulated": True, "real_tools_connected": False, "real_model_calls": 0}
        if self.done:
            info.update(grade_terminal(self._task, self.state, action))
            reward += 3 if info["success"] else -2
        self.state["history"].append({"observation": before, "action": action, "reward": reward,
                                      "next_observation": self.observe(), "terminal": self.done, "info": info})
        return self.observe(), reward, self.done, info
