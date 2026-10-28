"""Standalone detailed tool library. No mutation of the live Agent registry."""
import argparse
import json
from pathlib import Path
import sys
from catalog import CATALOG
from core import Library, ROOT, strict

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["list", "describe", "call", "demo", "test"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--store", type=Path, default=ROOT/"sandbox")
    parser.add_argument("--domain", choices=["darcy", "cvit", "all"], default="all")
    args = parser.parse_args()
    if args.command == "list":
        result = [{"name": row["name"], "group": row["group"], "implementation": row["implementation"], "purpose": row["purpose"]} for row in CATALOG]
    elif args.command == "describe":
        result = next(row for row in CATALOG if row["name"] == args.name)
    elif args.command == "call":
        path = (args.input if args.input.is_absolute() else ROOT/args.input).absolute() if args.input else None
        if path is None or path.resolve() != path or not path.is_relative_to(ROOT) or path.stat().st_size > 300000:
            raise ValueError("Select an explicit input JSON inside Research_Tool_Library")
        folder = args.store if args.store.is_absolute() else ROOT/args.store
        result = Library(folder).call(args.name, strict(path.read_text(encoding="utf-8")))
    elif args.command == "demo":
        from demo import run_demo
        results = [run_demo(domain, ROOT/"runs"/domain) for domain in (("darcy", "cvit") if args.domain == "all" else (args.domain,))]
        result = [{"domain": row["domain"], "passed": row["passed"], "tool_calls": len(row["tool_calls"]),
            "initial_findings": row["initial_findings"], "final_status": row["final_assessment"]["status"], "report_ref": row["report_ref"],
            "real_scientific_claim_verified": False} for row in results]
    else:
        import unittest
        with (ROOT/"tests.log").open("w", encoding="utf-8") as stream:
            suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"))
            report = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        result = {"tests": report.testsRun, "passed": report.wasSuccessful(), "failures": len(report.failures), "errors": len(report.errors)}
        (ROOT/"test_result.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(result)); return 0 if report.wasSuccessful() else 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
