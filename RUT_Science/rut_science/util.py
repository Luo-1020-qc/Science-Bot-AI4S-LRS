import hashlib
import json
import math
from pathlib import Path
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def state_diff(before: Any, after: Any, path: tuple = ()) -> list[dict]:
    """Concrete JSON changes, including updates and deletions, without eval()."""
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(before.keys() | after.keys()):
            child = path + (key,)
            if key not in before:
                changes.append({"op": "add", "path": list(child), "after": after[key]})
            elif key not in after:
                changes.append({"op": "remove", "path": list(child), "before": before[key]})
            else:
                changes.extend(state_diff(before[key], after[key], child))
        return changes
    if before != after:
        return [{"op": "replace", "path": list(path), "before": before, "after": after}]
    return []


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Pivoted elimination for the small, ridge-regularized synthetic regression."""
    n = len(vector)
    aug = [list(row) + [float(y)] for row, y in zip(matrix, vector)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        if abs(scale) < 1e-12:
            raise ValueError("singular design matrix")
        aug[col] = [v / scale for v in aug[col]]
        for row in range(n):
            if row != col:
                factor = aug[row][col]
                aug[row] = [x - factor * y for x, y in zip(aug[row], aug[col])]
    result = [row[-1] for row in aug]
    if not all(math.isfinite(v) for v in result):
        raise ValueError("non-finite model")
    return result
