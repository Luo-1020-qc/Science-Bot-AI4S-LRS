"""G2.3 isolated CPU policy learning and mocked CViT jobs; no real tools."""
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
for name in ("TORCH_HOME", "TORCHINDUCTOR_CACHE_DIR"):
    os.environ[name] = str(ROOT/"cache"/name.lower())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["snapshot", "build", "test", "train", "evaluate", "verify", "demo", "status", "feedback-train", "feedback-evaluate"])
    args = parser.parse_args()
    if args.command == "snapshot":
        value = {"protected_files": protected_before()}
    elif args.command == "build":
        from lab.suite_tasks import build_bank
        value = build_bank()
    elif args.command == "test":
        import unittest
        target = ROOT/"evidence/tests.log"
        with target.open("w", encoding="utf-8") as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/"tests")))
        value = {"tests": result.testsRun, "passed": result.wasSuccessful()}
        print(json.dumps(value)); return 0 if result.wasSuccessful() else 1
    elif args.command == "train":
        from lab.training_v3 import train_all
        value = train_all()
    elif args.command == "evaluate":
        from lab.evaluation_v3 import final_evaluation
        value = final_evaluation()
    elif args.command == "status":
        value = json.loads((ROOT/"evidence/progress.json").read_text(encoding="utf-8")) if (ROOT/"evidence/progress.json").exists() else {"status": "not trained"}
    elif args.command == "demo":
        from lab.evaluation_v3 import cvit_demo
        value = cvit_demo()
    elif args.command == "feedback-train":
        from lab.feedback_trial import run_trial
        value = run_trial()
    elif args.command == "feedback-evaluate":
        from lab.feedback_trial import evaluate_trial
        value = evaluate_trial()
    else:
        from lab.delivery_v3 import verify_delivery
        value = verify_delivery()
    print(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
