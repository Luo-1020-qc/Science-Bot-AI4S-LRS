"""Explicit public-data download, with byte limits and immutable acquisition receipts."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from urllib.request import Request, urlopen

from common import HERE, VERSION, fresh, read, sha, write

MAX_BYTES = 80*1024*1024


def fetch(output):
    catalog = read(HERE/"sources.json")
    output = fresh(output)
    receipt = {"version": VERSION, "catalog_sha256": sha(HERE/"sources.json"),
               "acquired_utc": datetime.now(timezone.utc).isoformat(), "files": {},
               "scope": "Public dataset files only; no model requests or user files"}
    # Network access happens only through this explicit command, never on import/train.
    for source, definition in catalog["sources"].items():
        for name, url in definition["files"].items():
            request = Request(url, headers={"User-Agent": "ScienceBot-public-curriculum/1.0"})
            with urlopen(request, timeout=45) as response:
                body = response.read(MAX_BYTES+1)
                if len(body) > MAX_BYTES:
                    raise ValueError("Public artifact exceeds 80 MiB: "+name)
                final_url = response.geturl()
            with (output/name).open("xb") as stream:
                stream.write(body)
            receipt["files"][name] = {"source": source, "url": url, "resolved_url": final_url,
                "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                "revision": definition["revision"], "license": definition["license"]}
            print("Downloaded", name, len(body), flush=True)
    write(output/"acquisition.json", receipt)
    return receipt


def check_raw(folder):
    folder = Path(folder)
    receipt = read(folder/"acquisition.json")
    if receipt["version"] != VERSION or receipt["catalog_sha256"] != sha(HERE/"sources.json"):
        raise ValueError("Raw receipt/catalog mismatch")
    expected = {name for item in read(HERE/"sources.json")["sources"].values()
                for name in item["files"]}
    if set(receipt["files"]) != expected:
        raise ValueError("Incomplete public download receipt")
    for name, row in receipt["files"].items():
        if sha(folder/name) != row["sha256"]:
            raise ValueError("Raw artifact changed: "+name)
    return receipt
