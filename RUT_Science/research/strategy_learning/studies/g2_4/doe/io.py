"""Strict JSON, bounded study-local input and non-overwriting record helpers."""
import hashlib
import json
from .guard import local


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def strict_json(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value
    def invalid(value):
        raise ValueError("Non-finite JSON constant")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def read(path):
    path = local(path)
    if path.stat().st_size > 8*1024*1024:
        raise ValueError("Research input exceeds 8 MiB")
    return strict_json(path.read_text(encoding="utf-8"))


def rows(path):
    path = local(path)
    if path.stat().st_size > 8*1024*1024:
        raise ValueError("Research input exceeds 8 MiB")
    return [strict_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write(path, value, *, fresh=False):
    path = local(path)
    if fresh and path.exists():
        raise ValueError("Never overwrite an existing frozen artifact or review file")
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
    with path.open("x" if fresh else "w", encoding="utf-8") as stream:
        stream.write(data)


def write_rows(path, records, *, fresh=False):
    path = local(path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if fresh else "w", encoding="utf-8") as stream:
        stream.write("".join(canonical(row)+"\n" for row in records))
