"""Stable validation entry for the current version; preserves original v1 CLI."""
import json
from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    current = json.loads((root/"current_dataset.json").read_text(encoding="utf-8"))
    target = (root/current["current_directory"]).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Current dataset must remain inside its dedicated directory")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(target))
    runpy.run_path(str(target/"validate.py"), run_name="__main__")
