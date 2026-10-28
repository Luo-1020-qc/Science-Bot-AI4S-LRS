"""All entrypoint tests use fake API_key_Agent.json files and mock networking."""
import contextlib
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rut_science.agents import JSONHTTPAgent, RuleAgent
from rut_science.benchmark import build_tasks
from rut_science.cli import main
from rut_science.configuration import DEFAULT_API_CONFIG, load_api_config
from rut_science.environment import make_initial_state
from rut_science.research_spec import ResearchSpec


class APIConfigurationEntrypointTests(unittest.TestCase):
    def write_config(self, folder):
        path = Path(folder) / "API_key_Agent.json"
        path.write_text(json.dumps({"API": "fake_agent_config_key", "endpoint": "https://example.invalid/chat/completions",
                                    "model": "mock-model"}), encoding="utf-8")
        return path

    def test_default_path_is_project_anchored_and_cwd_independent(self):
        self.assertEqual(DEFAULT_API_CONFIG, Path(__file__).resolve().parents[2] / "API_key_Agent.json")
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_config(folder)
            original = Path.cwd()
            try:
                os.chdir(Path(folder).parent)
                with patch("rut_science.configuration.DEFAULT_API_CONFIG", path):
                    self.assertEqual(load_api_config()["api_key"], "fake_agent_config_key")
            finally:
                os.chdir(original)

    def test_environment_key_does_not_override_file_and_endpoint_must_match(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_config(folder)
            with patch("rut_science.configuration.DEFAULT_API_CONFIG", path), patch.dict(os.environ, {"RUT_MODEL_API_KEY": "ignored_key"}):
                agent = JSONHTTPAgent("https://example.invalid/chat/completions", "mock")
                self.assertEqual(agent.api_key, "fake_agent_config_key")
                with self.assertRaises(ValueError):
                    JSONHTTPAgent("https://other.invalid/chat/completions", "mock")

    def test_missing_file_does_not_fall_back_to_environment(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"RUT_MODEL_API_KEY": "ignored_key"}):
            path = Path(folder) / "API_key_Agent.json"
            with patch("rut_science.configuration.DEFAULT_API_CONFIG", path), self.assertRaises(ValueError) as raised:
                JSONHTTPAgent("https://example.invalid/chat/completions", "mock")
            self.assertNotIn("ignored_key", str(raised.exception))

    def test_scientific_cli_uses_file_without_api_config_argument(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            config = self.write_config(folder)
            output = Path(folder) / "run"
            with patch("rut_science.cli.DEFAULT_API_CONFIG", config), patch("rut_science.cli.JSONHTTPAgent", side_effect=lambda *a, **k: RuleAgent()) as factory:
                self.assertEqual(main(["run", "--agents", "api_direct", "--task", "science_001", "--output", str(output)]), 0)
            self.assertEqual(factory.call_count, 10)  # Preflight + 9 local mocked episodes.
            for call in factory.call_args_list:
                self.assertEqual(call.args[:2], ("https://example.invalid/chat/completions", "mock-model"))
                self.assertEqual(call.kwargs["api_key"], "fake_agent_config_key")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["api_config_file"], "API_key_Agent.json")
            self.assertNotIn("fake_agent_config_key", (output / "manifest.json").read_text(encoding="utf-8"))

    def test_darcy_cli_uses_the_same_default_file(self):
        try:
            from rut_science.darcy_workflow import main as darcy_main
        except ImportError:
            self.skipTest("Optional Darcy dependencies are not installed")
        with tempfile.TemporaryDirectory() as folder:
            config = self.write_config(folder)
            spec_path = Path(folder) / "spec.json"
            spec = ResearchSpec("Darcy-Published-CPU-v1", "0"*64, "pressure_field", "nondimensional", "ridge_field", 0.8,
                                2026, split_policy="published_train_test", metric="mean_relative_l2", model_parameters={"alpha": 1.0})
            spec_path.write_text(json.dumps(spec.to_dict()), encoding="utf-8")
            with patch("rut_science.darcy_workflow.DEFAULT_API_CONFIG", config), patch("rut_science.darcy_workflow.run_workflow", return_value={"score": {"execution_success": True}}) as runner:
                self.assertEqual(darcy_main(["run", "--agent", "api_direct", "--spec", str(spec_path),
                                             "--output", str(Path(folder) / "run")]), 0)
            self.assertEqual(runner.call_args.args[3].api_key, "fake_agent_config_key")
            self.assertEqual(runner.call_args.args[3].endpoint, "https://example.invalid/chat/completions")
            self.assertEqual(runner.call_args.kwargs["api_config_file"], "API_key_Agent.json")
