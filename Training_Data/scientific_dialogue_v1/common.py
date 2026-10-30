"""Local, versioned curriculum artifacts. No provider, executor or online policy writes."""
import hashlib
import json
from pathlib import Path

VERSION = "scientific_dialogue_curriculum_v1"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPLITS = ("train", "dev", "test")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def identity(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")


def lines(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def fresh(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    return path


def manifest(folder, names):
    return {str(name): sha(Path(folder)/name) for name in sorted(names)}


def verify_files(folder, hashes):
    for name, checksum in hashes.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or ":" in name or "\\" in name:
            raise ValueError("Artifact must stay inside its versioned directory")
        path = Path(folder)/name
        if not path.resolve().is_relative_to(Path(folder).resolve()):
            raise ValueError("Artifact link leaves its versioned directory")
        if not path.is_file() or sha(path) != checksum:
            raise ValueError("Artifact changed or missing: "+name)


def source_code_hashes():
    return manifest(HERE, [p.name for p in HERE.glob("*.py")]+["sources.json"])
