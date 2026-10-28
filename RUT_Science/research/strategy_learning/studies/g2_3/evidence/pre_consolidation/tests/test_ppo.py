from copy import deepcopy
import json
import unittest
import numpy as np
import torch

from lab.ppo import ActorCritic, NeuralPolicy, setup_seed, gae, clipped_loss, ppo_update, load_policy, policy_value
from lab.adapter_v3 import SuiteEnvironment, SuiteRule, ACTIONS_V3, FEATURES_V3, encode, evaluate
from lab.suite_tasks import tabular_task, cvit_task, load_split
from lab.training_v3 import collect, metric_key
from lab.guard import LAB


class PPOMathTests(unittest.TestCase):
    def test_gae_uses_terminal_boundaries(self):
        adv, returns = gae([1., 2.], [0., 0.], [0., 0.], [0., 1.], gamma=1, lam=1)
        np.testing.assert_allclose(adv, [3., 2.])
        np.testing.assert_allclose(returns, adv)
        adv, _ = gae([1., 100.], [0., 0.], [999., 999.], [1., 1.], gamma=1, lam=1)
        np.testing.assert_allclose(adv, [1., 100.])

    def test_truncated_rollout_bootstraps_next_value(self):
        adv, returns = gae([.5], [.1], [.2], [0.], gamma=.9, lam=.95)
        np.testing.assert_allclose(adv, [.58], atol=1e-6)
        np.testing.assert_allclose(returns, [.68], atol=1e-6)

    def test_clipping_matches_both_advantage_signs(self):
        new, old = torch.log(torch.tensor([2., 2.])), torch.zeros(2)
        self.assertAlmostEqual(float(clipped_loss(new[:1], old[:1], torch.tensor([1.]))), -1.2, places=6)
        self.assertAlmostEqual(float(clipped_loss(new[1:], old[1:], torch.tensor([-1.]))), 2., places=6)

    def test_invalid_action_probability_is_zero(self):
        setup_seed(1)
        network = ActorCritic()
        features = torch.zeros((1, len(FEATURES_V3)))
        mask = torch.zeros((1, len(ACTIONS_V3)), dtype=torch.bool); mask[0, 0] = True
        dist, _ = network(features, mask)
        self.assertEqual(float(dist.probs[0, 0].detach()), 1.)
        self.assertEqual(float(dist.probs[0, 1:].sum().detach()), 0.)

    def test_update_changes_parameters_and_keeps_losses_finite(self):
        setup_seed(2)
        network = ActorCritic()
        tasks = [tabular_task("ordinary_comparison", "train", 1, 101), cvit_task("pilot_run", "train", 1, 102)]
        batch = collect(network, tasks, 2, 1, 32)
        before = policy_value(network)
        result = ppo_update(network, torch.optim.Adam(network.parameters(), lr=.001), batch, epochs=2, minibatch=16)
        self.assertNotEqual(before["parameters"], policy_value(network)["parameters"])
        self.assertTrue(all(np.isfinite(value) for value in result.values()))
        for obs in batch["observations"]:
            self.assertNotIn("hidden", obs)

    def test_checkpoint_optimizer_rng_resume_matches_uninterrupted_update(self):
        setup_seed(4)
        model = ActorCritic()
        optimizer = torch.optim.Adam(model.parameters(), lr=.001)
        tasks = [cvit_task("pilot_run", "train", 1, 102)]
        batch = collect(model, tasks, 4, 1, 16)
        ppo_update(model, optimizer, batch, epochs=1, minibatch=8)
        state = deepcopy(model.state_dict()); opt = deepcopy(optimizer.state_dict()); rng = torch.get_rng_state()
        ppo_update(model, optimizer, batch, epochs=1, minibatch=8)
        expected = deepcopy(model.state_dict())
        restored = ActorCritic(); restored.load_state_dict(state)
        resumed_optimizer = torch.optim.Adam(restored.parameters(), lr=.001); resumed_optimizer.load_state_dict(opt)
        torch.set_rng_state(rng)
        ppo_update(restored, resumed_optimizer, batch, epochs=1, minibatch=8)
        self.assertTrue(all(torch.equal(expected[key], restored.state_dict()[key]) for key in expected))

    def test_policy_json_roundtrip_and_protocol_validation(self):
        setup_seed(6)
        model = ActorCritic()
        value = json.loads(json.dumps(policy_value(model)))
        other = load_policy(value)
        self.assertTrue(all(torch.equal(model.state_dict()[key], other.state_dict()[key]) for key in model.state_dict()))
        value["version"] = "wrong"
        with self.assertRaises(ValueError):
            load_policy(value)

    def test_shared_features_have_fixed_dimensions_and_no_raw_ids(self):
        for task in (tabular_task("paired_design", "train", 1, 101), cvit_task("pilot_run", "train", 1, 102)):
            env = SuiteEnvironment(task)
            obs = env.reset()
            vector = encode(obs)
            self.assertEqual(len(vector), len(FEATURES_V3))
            self.assertTrue(all(type(x) in {int, float} for x in vector))
            self.assertNotIn(task["id"], json.dumps(obs))

    def test_training_cannot_load_fresh_final_bank(self):
        with self.assertRaises(PermissionError):
            load_split("heldout", "training")

    def test_selection_key_uses_success_before_cost(self):
        better = {"success_rate": .9, "blocked_attempts": 0, "mean_decisions": 20}
        cheap = {"success_rate": .8, "blocked_attempts": 0, "mean_decisions": 2}
        self.assertGreater(metric_key(better), metric_key(cheap))

    def test_saved_checkpoint_weights_only_roundtrip(self):
        from lab.training_v3 import _save_checkpoint
        setup_seed(9)
        model = ActorCritic()
        optimizer = torch.optim.Adam(model.parameters(), lr=.001)
        target = LAB/"test_outputs/checkpoint_roundtrip.pt"
        rng = torch.get_rng_state()
        _save_checkpoint(target, {"network": model.state_dict(), "optimizer": optimizer.state_dict(), "torch_rng": rng,
                                  "update": 2, "config_hash": "unit-test-only"})
        saved = torch.load(target, map_location="cpu", weights_only=True)
        self.assertEqual(saved["update"], 2)
        self.assertTrue(torch.equal(saved["torch_rng"], rng))
        self.assertTrue(all(torch.equal(model.state_dict()[key], saved["network"][key]) for key in model.state_dict()))

