"""Standalone G2.2 entry. All writes stay here; no live tool/API imports."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from lab.guard import install, protected_before, protected_after
install()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["snapshot", "copy-fixtures", "build", "test", "benchmark", "audit", "review-export", "review-import", "train-reviewed", "demo", "verify"])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "snapshot":
        print(json.dumps({"protected_files": protected_before()}))
    elif args.command == "audit":
        value = protected_after(); print(json.dumps(value)); return 0 if value["unchanged"] else 1
    elif args.command == "copy-fixtures":
        from lab.fixtures import copy_fixtures
        print(json.dumps(copy_fixtures(), ensure_ascii=False))
    elif args.command == "build":
        from lab.tasks import build_bank
        print(json.dumps(build_bank(), ensure_ascii=False))
    elif args.command == "test":
        import unittest
        suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"))
        path = ROOT/"evidence/tests.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        print(json.dumps({"tests": result.testsRun, "passed": result.wasSuccessful()})); return 0 if result.wasSuccessful() else 1
    elif args.command == "benchmark":
        from lab.benchmark import benchmark
        print(json.dumps(benchmark(), ensure_ascii=False))
    elif args.command in {"review-export", "review-import"}:
        from lab.review import export_queue, import_reviews
        function = export_queue if args.command == "review-export" else import_reviews
        print(json.dumps(function(args.input, args.output), ensure_ascii=False))
    elif args.command == "demo":
        from lab.benchmark import demo
        print(json.dumps(demo(), ensure_ascii=False))
    elif args.command == "train-reviewed":
        from lab.benchmark import train_reviewed
        print(json.dumps(train_reviewed(args.input, args.output), ensure_ascii=False))
    elif args.command == "verify":
        from lab.delivery import verify_delivery
        print(json.dumps(verify_delivery(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
