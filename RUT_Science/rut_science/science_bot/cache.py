"""Tool-owned real-result cache; it is never passed to a policy."""
from pathlib import Path
import json
import time
from .numerics import TOOL_VERSION, execute
from ..util import digest, write_json


class OutcomeCache:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder else None
        self.memory = {}

    def get(self, data, candidate, cold=False):
        key = digest({"data": data.identity, "candidate": candidate, "tool": TOOL_VERSION,
                      "preprocessing": "fit_subset_standardize_v1"})
        started = time.perf_counter()
        path = self.folder / (key+".json") if self.folder else None
        if not cold and key in self.memory:
            result, hit = self.memory[key], True
        elif not cold and path and path.exists():
            envelope = json.loads(path.read_text(encoding="utf-8"))
            if envelope["key"] != key or digest(envelope["result"]) != envelope["result_hash"]:
                raise ValueError("Corrupt outcome cache")
            result, hit = envelope["result"], True
        else:
            result, hit = execute(data, candidate), False
            if path:
                write_json(path, {"key": key, "result": result, "result_hash": digest(result)})
        self.memory[key] = result
        return result, {"cache_hit": hit, "elapsed_seconds": time.perf_counter()-started, "cache_key": key}
