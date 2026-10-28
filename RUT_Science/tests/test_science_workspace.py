from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from rut_science.science_bot.workspace import Workspace, MAX_TEXT_BYTES
from rut_science.science_bot.session import ScienceSession, ROOT
from rut_science.science_bot.terminal import project_command
from rut_science.science_bot.api import make_server
from rut_science.util import write_json


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base/"research project 项目"
        self.root.mkdir()

    def session(self, **kwargs):
        return ScienceSession.create(backend="offline", planner="adaptive", workspace=self.root, **kwargs)

    def test_identity_is_stable_and_config_persisted(self):
        first = Workspace.open(self.root)
        second = Workspace.open(self.root/".")
        self.assertEqual(first.binding, second.binding)
        self.assertTrue((self.root/".sciencebot/workspace.json").is_file())

    def test_invalid_workspace_does_not_create_project(self):
        missing = self.root/"typo"
        with self.assertRaises(ValueError):
            Workspace.open(missing)
        self.assertFalse(missing.exists())
        file = self.root/"module.py"; file.write_text("x=1", encoding="utf-8")
        with self.assertRaises(ValueError):
            Workspace.open(file)

    def test_session_location_and_cwd_independence(self):
        cwd = Path.cwd()
        session = self.session()
        self.assertEqual(session.folder.parent, self.root/".sciencebot/sessions")
        self.assertEqual(Path.cwd(), cwd)
        self.assertEqual(session.status()["workspace"]["root"], str(self.root))
        self.assertNotIn(str(self.root), json.dumps(session.env.observe()))

    def test_explicit_output_override_is_preserved(self):
        output = self.base/"other output"
        session = self.session(base=output)
        self.assertEqual(session.folder.parent, output)
        self.assertEqual(session.workspace.root, self.root)

    def test_confirmation_is_bound_to_workspace(self):
        a = self.session()
        other = self.base/"other"; other.mkdir()
        b = ScienceSession.create(backend="offline", planner="adaptive", workspace=other)
        self.assertEqual(a.env.observe(), b.env.observe())
        self.assertNotEqual(a.confirmation, b.confirmation)

    def test_restore_by_id_and_reject_another_workspace(self):
        session = self.session()
        restored = ScienceSession.restore(session.meta["id"], workspace=self.root)
        self.assertEqual(restored.workspace.binding, session.workspace.binding)
        other = self.base/"other"; other.mkdir()
        with self.assertRaisesRegex(ValueError, "another workspace"):
            ScienceSession.restore(session.folder, workspace=other)

    def test_missing_or_replaced_identity_rejected(self):
        session = self.session()
        config = self.root/".sciencebot/workspace.json"
        binding = json.loads(config.read_text(encoding="utf-8"))
        config.unlink()
        with self.assertRaises(ValueError):
            ScienceSession.restore(session.folder)
        binding["workspace_id"] = "0"*32
        write_json(config, binding)
        with self.assertRaisesRegex(ValueError, "identity changed"):
            ScienceSession.restore(session.folder)

    def test_legacy_session_still_restores_without_workspace(self):
        legacy = ScienceSession.create(self.base/"legacy", backend="offline", planner="adaptive")
        self.assertIsNone(ScienceSession.restore(legacy.folder).workspace)
        with self.assertRaisesRegex(ValueError, "Legacy"):
            ScienceSession.restore(legacy.folder, workspace=self.root)

    def test_unicode_and_quoted_file_paths(self):
        path = self.root/"source file 中文.py"
        path.write_bytes("print('你好')\n".encode("utf-8"))
        workspace = Workspace.open(self.root)
        result = workspace.read_text('"source file 中文.py"')
        self.assertEqual(result["text"], "print('你好')\n")
        self.assertEqual(result["path"], path.name)
        self.assertEqual(len(result["sha256"]), 64)

    def test_parent_and_absolute_escape_rejected(self):
        external = self.base/"outside.py"; external.write_text("outside", encoding="utf-8")
        workspace = Workspace.open(self.root)
        for value in ("../outside.py", external):
            with self.assertRaisesRegex(ValueError, "outside"):
                workspace.read_text(value)

    def test_credentials_state_and_binary_not_readable(self):
        workspace = Workspace.open(self.root)
        for filename in ("API_key_Agent.json", ".env", ".env.local", "private.key"):
            (self.root/filename).write_text("not a real secret", encoding="utf-8")
            with self.assertRaises(ValueError):
                workspace.read_text(filename)
        with self.assertRaises(ValueError):
            workspace.read_text(".sciencebot/workspace.json")
        (self.root/"array.bin").write_bytes(b"abc\x00def")
        with self.assertRaises(ValueError):
            workspace.read_text("array.bin")
        (self.root/"terminal.txt").write_text("\x1b[2J", encoding="utf-8")
        with self.assertRaises(ValueError):
            workspace.read_text("terminal.txt")

    def test_large_files_are_bounded(self):
        workspace = Workspace.open(self.root)
        (self.root/"large.py").write_bytes(b"x"*(MAX_TEXT_BYTES+1))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            workspace.read_text("large.py")

    def test_listing_exclusions_and_limit(self):
        workspace = Workspace.open(self.root)
        (self.root/"a.py").write_text("x=1", encoding="utf-8")
        (self.root/"b.py").write_text("x=2", encoding="utf-8")
        (self.root/".venv").mkdir()
        (self.root/".venv"/"hidden.py").write_text("hidden", encoding="utf-8")
        (self.root/"API_key_Agent.json").write_text("not a secret", encoding="utf-8")
        result = workspace.files("*.py", limit=1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["files"][0]["path"], "a.py")
        self.assertEqual([r["path"] for r in workspace.files()["files"]], ["a.py", "b.py"])

    def test_symlink_escape_and_excluded_alias_rejected(self):
        outside = self.base/"outside.txt"; outside.write_text("external", encoding="utf-8")
        secret = self.root/".env"; secret.write_text("not a secret", encoding="utf-8")
        try:
            (self.root/"external.txt").symlink_to(outside)
            (self.root/"alias.txt").symlink_to(secret)
        except OSError:
            self.skipTest("Windows account cannot create symlinks")
        workspace = Workspace.open(self.root)
        for value in ("external.txt", "alias.txt"):
            with self.assertRaises(ValueError):
                workspace.read_text(value)
        self.assertEqual(workspace.files()["files"], [])

    def junction(self, link, target):
        if sys.platform == "win32":
            result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            if result.returncode:
                self.skipTest("Windows junction creation is unavailable")
        else:
            link.symlink_to(target, target_is_directory=True)

    def test_directory_junction_escape_is_not_listed_or_read(self):
        outside = self.base/"external folder"; outside.mkdir()
        (outside/"external.py").write_text("external", encoding="utf-8")
        self.junction(self.root/"linked", outside)
        workspace = Workspace.open(self.root)
        with self.assertRaisesRegex(ValueError, "outside"):
            workspace.read_text("linked/external.py")
        self.assertEqual(workspace.files()["files"], [])

    def test_workspace_state_cannot_be_redirected(self):
        outside = self.base/"external state"; outside.mkdir()
        self.junction(self.root/".sciencebot", outside)
        with self.assertRaisesRegex(ValueError, "redirected"):
            Workspace.open(self.root)
        self.assertFalse((outside/"workspace.json").exists())

    def test_default_session_directory_cannot_be_redirected(self):
        workspace = Workspace.open(self.root)
        outside = self.base/"external sessions"; outside.mkdir()
        self.junction(workspace.sessions_dir, outside)
        with self.assertRaisesRegex(ValueError, "redirected"):
            self.session()
        self.assertEqual(list(outside.iterdir()), [])

    def test_local_project_commands_do_not_call_llm_or_spend_budget(self):
        session = self.session()
        (self.root/"module.py").write_text("value=42", encoding="utf-8")
        before = session.env.observe()
        with patch.object(session.llm, "call", side_effect=AssertionError("must stay local")):
            self.assertEqual(project_command(session, "/read", "module.py")["text"], "value=42")
            self.assertTrue(project_command(session, "/files")["files"])
        self.assertEqual(before, session.env.observe())

    def test_cli_demo_works_from_another_cwd(self):
        process = subprocess.run([sys.executable, "-m", "rut_science", "science", "--workspace", str(self.root),
                                  "--backend", "offline", "--planner", "adaptive", "--demo"],
                                 cwd=self.base, capture_output=True, timeout=60)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors="replace"))
        manifests = list((self.root/".sciencebot/sessions").glob("*/session.json"))
        self.assertEqual(len(manifests), 1)
        session = ScienceSession.restore(manifests[0].parent)
        self.assertTrue(session.env.done)
        self.assertEqual(session.workspace.root, self.root)

    def test_workspace_http_is_server_bound(self):
        server = make_server(port=0, workspace=self.root)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/v1/sessions"
        def post(body, key):
            request = Request(url, data=json.dumps(body).encode(), headers={
                "Content-Type": "application/json", "Authorization": "Bearer "+server.service.token,
                "Idempotency-Key": key})
            with urlopen(request, timeout=5) as response:
                return json.load(response)
        status = post({"backend": "offline", "planner": "adaptive"}, "create")
        self.assertEqual(status["workspace"]["root"], str(self.root))
        self.assertTrue((self.root/".sciencebot/sessions"/status["id"] / "session.json").exists())
        with self.assertRaises(HTTPError):
            post({"workspace": str(self.base), "backend": "offline", "planner": "adaptive"}, "other")


if __name__ == "__main__":
    unittest.main()
