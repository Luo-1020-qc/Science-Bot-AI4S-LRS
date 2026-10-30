"""Three-stage, local research curriculum. Downloads require the explicit fetch command."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--output", required=True, type=Path)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--raw", required=True, type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    train = sub.add_parser("train")
    train.add_argument("--data", required=True, type=Path)
    train.add_argument("--output", required=True, type=Path)
    export = sub.add_parser("export-sft")
    export.add_argument("--data", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    clarq = sub.add_parser("import-clarq")
    clarq.add_argument("--train", required=True, type=Path)
    clarq.add_argument("--test", required=True, type=Path)
    clarq.add_argument("--output", required=True, type=Path)
    audit = sub.add_parser("audit-teammate")
    audit.add_argument("--source", required=True, type=Path)
    audit.add_argument("--output", required=True, type=Path)
    review = sub.add_parser("import-reviewed")
    review.add_argument("--input", required=True, type=Path)
    review.add_argument("--output", required=True, type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("--data", required=True, type=Path)
    verify.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "fetch":
        from acquire import fetch
        result = fetch(args.output)
        result = {"downloaded_files": len(result["files"])}
    elif args.command == "prepare":
        from adapters import prepare
        result = prepare(args.raw, args.output)["counts"]
    elif args.command == "train":
        from models import train
        result = train(args.data, args.output)
    elif args.command == "export-sft":
        from exports import export_sft
        result = export_sft(args.data, args.output)
    elif args.command == "import-clarq":
        from adapters import import_clarq
        result = import_clarq(args.train, args.test, args.output)
    elif args.command == "audit-teammate":
        from annotation import audit_shells
        result = audit_shells(args.source, args.output)
    elif args.command == "import-reviewed":
        from annotation import import_reviewed
        result = import_reviewed(args.input, args.output)
    else:
        from models import verify_run
        result = verify_run(args.data, args.run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
