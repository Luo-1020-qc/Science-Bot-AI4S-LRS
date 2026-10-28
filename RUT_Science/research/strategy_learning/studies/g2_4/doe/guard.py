"""Accidental-side-effect guard; not an OS sandbox for hostile Python code."""
import os
from pathlib import Path
import sys

LAB = Path(__file__).resolve().parents[1]
PROJECT = LAB.parents[4]


def local(value):
    path = Path(value).absolute()
    if not path.is_relative_to(LAB) or path == LAB or path.resolve() != path:
        raise PermissionError("G2.4 file operations require a non-redirected path inside the study")
    return path


def install():
    sys.dont_write_bytecode = True
    def audit(event, args):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.startfile", "os.posix_spawn", "os.exec", "os.spawn"}:
            raise PermissionError("G2.4 has no network, real tools or external processes")
        if event == "import" and str(args[0]).split(".")[0] in {"rut_science", "dynamic_cvit"}:
            raise PermissionError("Live Agent and CViT imports are prohibited")
        if event == "open":
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not isinstance(path, int):
                local(os.fsdecode(path))
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "os.truncate"}:
            local(os.fsdecode(args[0]))
        if event in {"os.rename", "os.replace", "os.link", "os.symlink"}:
            local(os.fsdecode(args[0])); local(os.fsdecode(args[1]))
    sys.addaudithook(audit)
