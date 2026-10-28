"""G2.4 offline DOE protocol, common verifier and expert-pending calibration."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from doe.guard import install
install()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "test", "evaluate", "demo", "verify", "status", "validate", "review-export", "review-import"])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from doe.guard import local
    from doe.io import read, write
    def selected(path):
        if path is None:
            raise ValueError("Select an explicit study-local input")
        return local(path if path.is_absolute() else ROOT/path)
    if args.command == "test":
        import unittest
        with (ROOT/"evidence/current_tests.log").open("w", encoding="utf-8") as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/"tests")))
        value = {"tests": result.testsRun, "passed": result.wasSuccessful()}
        print(json.dumps(value)); return 0 if result.wasSuccessful() else 1
    elif args.command == "validate":
        from doe.validation import validate
        value = validate(read(selected(args.input)), read(selected(args.request)))
        if args.output:
            write(selected(args.output), value, fresh=True)
    elif args.command in {"review-export", "review-import"}:
        from doe.review import export_queue, import_reviews
        value = export_queue(selected(args.output) if args.output else None) if args.command == "review-export" else import_reviews(selected(args.input), selected(args.output) if args.output else None)
    elif args.command == "status":
        value = read(ROOT/"evidence/current_verification.json") if (ROOT/"evidence/current_verification.json").exists() else {"passed": False, "note": "Run build/test/evaluate/verify"}
    else:
        from doe.evaluation import freeze_protocol, diagnose_development, demo, verify
        value = {"build": freeze_protocol, "evaluate": diagnose_development, "demo": demo, "verify": verify}[args.command]()
    print(json.dumps(value, ensure_ascii=False))
    return 1 if args.command == "validate" and not value["ready_for_review"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
