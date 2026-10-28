"""Cooperative process guards and protected-project inventory.

This audit hook is defense against accidental writes, not an OS sandbox for
arbitrary hostile Python code. The lab contains no subprocess/network tools.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

LAB = Path(__file__).resolve().parents[1]
PROJECT = next(parent for parent in LAB.parents if (parent/"science-bot.cmd").is_file() and (parent/"RUT_Science").is_dir())


def ensure_local(value):
    path = Path(value).resolve()
    if not path.is_relative_to(LAB) or path == LAB:
        raise PermissionError("G2.2 writes must remain inside its dedicated test folder")
    return path


def install():
    sys.dont_write_bytecode = True
    def audit(event, args):
        if event in {"socket.__new__", "socket.connect", "socket.bind", "subprocess.Popen", "os.system", "os.startfile", "os.posix_spawn", "os.exec", "os.spawn"}:
            raise PermissionError("No network, GUI, process execution or real tools in G2.2")
        if event == "import" and str(args[0]).split(".")[0] == "rut_science":
            raise PermissionError("Do not import the live science Bot or real tool registry")
        if event == "open":
            path, mode, flags = args
            writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)))
            if writes and not isinstance(path, int):
                ensure_local(os.fsdecode(path))
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "os.truncate"}:
            ensure_local(os.fsdecode(args[0]))
        if event in {"os.rename", "os.replace", "os.link", "os.symlink"}:
            ensure_local(os.fsdecode(args[0])); ensure_local(os.fsdecode(args[1]))
    sys.addaudithook(audit)


def file_hash(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def inventory():
    result, directories = {}, []
    for folder, dirs, names in os.walk(PROJECT, followlinks=False):
        folder = Path(folder)
        dirs[:] = [name for name in dirs if folder/name != LAB and not (folder/name).is_symlink()]
        for name in names:
            path = folder/name
            if path.is_symlink():
                continue
            relative = path.relative_to(PROJECT).as_posix()
            stat = path.stat()
            # The installed interpreter is read-only. Record its entire file
            # inventory cheaply; hash every other existing project file.
            item = {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            if ".venv" not in path.relative_to(PROJECT).parts:
                item["sha256"] = file_hash(path)
            result[relative] = item
    return result


def write_json(path, value):
    path = ensure_local(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
    temporary = path.with_name(path.name+".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def protected_before():
    if (LAB/"relocation.json").exists():
        raise ValueError("Historical protected baseline is immutable; use the consolidated verify entry")
    path = LAB/"evidence/protected_before.json"
    if path.exists():
        raise ValueError("Protected baseline already exists; never replace it")
    value = inventory()
    write_json(path, {"date": "2026-10-26", "project": str(PROJECT), "excluded": str(LAB),
                      "hash_policy": "SHA256+size+mtime for all project files except .venv; full size+mtime inventory for .venv", "files": value})
    return len(value)


def protected_after():
    if (LAB/"relocation.json").exists():
        raise ValueError("Original isolation inventory is historical; use current relocation verification")
    old = json.loads((LAB/"evidence/protected_before.json").read_text(encoding="utf-8"))["files"]
    new = inventory()
    added, removed = sorted(set(new)-set(old)), sorted(set(old)-set(new))
    changed = [path for path in old.keys()&new.keys() if old[path] != new[path]]
    result = {"unchanged": not (added or removed or changed), "files_checked": len(old), "added": added, "removed": removed, "changed": sorted(changed)}
    write_json(LAB/"evidence/protected_after.json", result)
    return result
