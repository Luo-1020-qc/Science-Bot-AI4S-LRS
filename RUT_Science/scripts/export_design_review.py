"""Export G2.1 observed decisions for expert annotation; never auto-train."""
import argparse
from pathlib import Path
from rut_science.science_bot.general.interview.learning import export_review_queue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not (args.session/"session.json").is_file():
        parser.error("session must be a saved science Bot session folder")
    if args.output.exists():
        parser.error("output exists; preserve existing annotations and choose a new file")
    print(f"Exported {export_review_queue(args.session, args.output)} decisions; expert_action remains null.")


if __name__ == "__main__":
    main()
