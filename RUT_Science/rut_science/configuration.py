"""Read local credentials without copying them into experiment artifacts."""
import json
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_API_CONFIG = Path(__file__).resolve().parents[2] / "API_key_Agent.json"


def load_profiles(path: Path | None = None) -> list[dict]:
    """Accept JSON, a JSON array, or adjacent objects with trailing commas.

    This compatibility reader does not modify the user's credential file.
    Commas inside quoted strings are never changed.
    """
    path = DEFAULT_API_CONFIG if path is None else Path(path)
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        raise ValueError(f"Cannot read local API configuration: {path.name}; credential contents omitted") from None
    normalized, quoted, escaped = [], False, False
    for index, char in enumerate(raw):
        if char == '"' and not escaped:
            quoted = not quoted
        if char == "," and not quoted and raw[index+1:].lstrip().startswith(("}", "]")):
            continue
        normalized.append(char)
        escaped = char == "\\" and not escaped if quoted else False
    raw = "".join(normalized)
    decoder, cursor, objects = json.JSONDecoder(), 0, []
    while cursor < len(raw):
        while cursor < len(raw) and raw[cursor].isspace():
            cursor += 1
        if cursor == len(raw):
            break
        try:
            obj, cursor = decoder.raw_decode(raw, cursor)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid local API configuration at line {exc.lineno}; contents omitted") from None
        objects.extend(obj if isinstance(obj, list) else [obj])
    if not objects or not all(isinstance(obj, dict) for obj in objects):
        raise ValueError("API configuration must contain object profiles")
    return objects


def load_api_config(path: Path | None = None, profile: int = 0, credential_field: str = "API") -> dict:
    profiles = load_profiles(path)
    if not 0 <= profile < len(profiles):
        raise ValueError("API profile index is out of range")
    item = profiles[profile]
    key = item.get(credential_field) or item.get("api_key") or item.get("API_KEY")
    base = item.get("endpoint") or item.get("base_url") or item.get("api_base")
    if not isinstance(key, str) or not key.strip() or not isinstance(base, str):
        raise ValueError("Selected API profile needs a credential and endpoint/base_url")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query:
        raise ValueError("Credential configuration requires an HTTPS endpoint without embedded credentials or query")
    endpoint = base.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    return {"endpoint": endpoint, "api_key": key.strip(),
            "model": item.get("model") or item.get("model_id"), "profile": profile}
