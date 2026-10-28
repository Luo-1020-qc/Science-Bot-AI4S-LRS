import json
from pathlib import Path
import socket
import sys
import unittest
from lab.guard import LAB, PROJECT, ensure_local, file_hash
from lab.suite_tasks import verify_bank


class IsolationTests(unittest.TestCase):
    def test_no_live_import_network_or_external_write(self):
        with self.assertRaises(PermissionError):
            __import__("rut_science")
        with self.assertRaises(PermissionError):
            socket.socket()
        path = PROJECT/"forbidden_g2_3_test_write.txt"
        self.assertFalse(path.exists())
        with self.assertRaises(PermissionError):
            path.write_text("never", encoding="utf-8")
        self.assertFalse(path.exists())

    def test_previous_g2_2_is_outside_allowed_write_scope(self):
        with self.assertRaises(PermissionError):
            ensure_local(PROJECT/"RUT_Science/research/strategy_learning/studies/g2_2/evidence/benchmark.json")

    def test_cvit_fixtures_are_copied_and_original_code_is_not_imported(self):
        value = json.loads((LAB/"evidence/cvit_fixture_copy.json").read_text(encoding="utf-8"))
        self.assertEqual(file_hash(LAB/value["source"]), value["sha256"])
        self.assertEqual(file_hash(LAB/value["copy"]), value["sha256"])
        self.assertFalse(any(name == "rut_science" or name.startswith("rut_science.") for name in sys.modules))
        self.assertFalse(any("dynamic_cvit" in name for name in sys.modules))

    def test_bank_is_sealed_before_training(self):
        self.assertEqual(verify_bank()["counts"], {"train": 240, "development": 90, "heldout": 96})
