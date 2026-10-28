"""Run copied compatibility tests and integration tests inside this delivery."""
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE/"tests"))
with (HERE/"tests.log").open("w", encoding="utf-8") as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.discover(str(HERE/"tests")))
value = {"date": "2026-10-27", "tests": result.testsRun, "skipped": len(result.skipped),
         "failures": len(result.failures), "errors": len(result.errors), "passed": result.wasSuccessful(),
         "real_model_requests": 0, "real_scientific_tool_executions": 0,
         "scope": "Copied compatibility tests, real read-only bridge processes, terminal and loopback HTTP; synthetic inputs only"}
(HERE/"tests.json").write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps(value, ensure_ascii=False))
raise SystemExit(0 if result.wasSuccessful() else 1)
