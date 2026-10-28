"""Check illustrative data only; no training or real scientific tools."""
import argparse
import json
from pathlib import Path
import sys
import unittest
from dataset_lib import ROOT, save, validate_dataset

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", action="store_true")
    args = parser.parse_args()
    report = validate_dataset()
    if args.tests:
        suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"))
        with (ROOT/"validation_tests.log").open("w", encoding="utf-8") as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        report.update(tests=result.testsRun, test_failures=len(result.failures), test_errors=len(result.errors), passed=result.wasSuccessful())
    save("validation.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
