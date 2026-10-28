"""Train the G2.1 BC reference baseline, no API/GPU/LLM weight updates."""
import argparse
import json
from pathlib import Path
from rut_science.science_bot.general.interview.learning import train_baseline

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"models/design_interview_bc")
    parser.add_argument("--seed", type=int, default=21)
    parser.add_argument("--epochs", type=int, default=240)
    args = parser.parse_args()
    if not 1 <= args.epochs <= 1000:
        parser.error("epochs must be 1..1000")
    if (args.output/"manifest.json").exists():
        parser.error("output already contains a versioned policy; choose a new output folder")
    result = train_baseline(args.output, seed=args.seed, epochs=args.epochs)
    print(json.dumps({"algorithm": result["manifest"]["algorithm"], "label_source": result["manifest"]["label_source"],
                      "heldout": result["evaluation"]["heldout"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
