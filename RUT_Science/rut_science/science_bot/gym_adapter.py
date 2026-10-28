"""Gymnasium wrapper over exactly the deployment step_action method."""
import gymnasium as gym
from gymnasium import spaces
import numpy as np
from .contracts import K_MAX, BudgetedResearchSpec
from .environment import BudgetedEnvironment
from .numerics import load_data
from .policies import encode, GLOBAL_DIM, CANDIDATE_DIM, HISTORY_DIM


class ScienceGym(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, spec=None, cache=None):
        self.spec = spec or BudgetedResearchSpec()
        self.cache = cache
        self.action_space = spaces.Discrete(K_MAX)
        self.observation_space = spaces.Dict({
            "global": spaces.Box(-np.inf, np.inf, (GLOBAL_DIM,), dtype=np.float32),
            "history": spaces.Box(-np.inf, np.inf, (13, HISTORY_DIM), dtype=np.float32),
            "candidates": spaces.Box(-np.inf, np.inf, (K_MAX, CANDIDATE_DIM), dtype=np.float32),
            "mask": spaces.MultiBinary(K_MAX)})

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.env = BudgetedEnvironment(self.spec, load_data(self.spec), cache=self.cache)
        self.public = self.env.observe()
        return encode(self.public), {}

    def action_masks(self):
        return np.asarray(self.public["mask"], bool)

    def step(self, action):
        if not self.public["mask"][action]:
            raise ValueError("Masked action")
        result = self.env.step_action(self.public["candidates"][action]["id"], self.public["observation_ref"],
                                      f"gym_{self.env.state['version']}")
        self.public = self.env.observe()
        return encode(self.public), result["reward"], result["terminated"], result["truncated"], {}
