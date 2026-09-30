"""User-owned data, cancellation and process helpers; no device access."""
from pathlib import Path
import json
import os
import subprocess
import threading
import time

class GuestLock:
    """One writer across workbench windows, builders and QEMU sessions."""
    def __init__(self, device):
        import msvcrt
        self.file = (Path(device) / 'session.lock').open('a+b')
        if self.file.tell() == 0:
            self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.file.close()
            raise RuntimeError('Another session owns this guest. Stop it before starting or building.') from None
    def close(self): self.file.close()
    def __enter__(self): return self
    def __exit__(self, *_): self.close()

ASSETS = Path(__file__).resolve().parent

def data_home():
    return Path(os.environ.get("X2DII_DEVKIT_HOME", str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "X2DII-DevKit"))).resolve()

def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {} if default is None else default

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)

class Cancelled(Exception):
    pass

class Task:
    def __init__(self, report=print):
        self.report = report
        self.cancelled = threading.Event()

    def check(self):
        if self.cancelled.is_set():
            raise Cancelled("Cancelled / 已取消；可以重试")

    def run(self, args, timeout=180, cwd=None):
        self.check()
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with subprocess.Popen([str(a) for a in args], cwd=cwd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, creationflags=creationflags) as process:
            start = time.monotonic()
            try:
                while True:
                    self.check()
                    try:
                        output, _ = process.communicate(timeout=.25)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() - start > timeout:
                            raise TimeoutError(f"Process timed out: {Path(args[0]).name}")
                if process.returncode:
                    raise RuntimeError(output.decode(errors="replace")[-4000:])
                return output.decode(errors="replace")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

def checked_child(root, name):
    """Reject archive path traversal, device names, ADS and Windows collisions."""
    name = name.replace("\\", "/")
    parts = name.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
    if not name or any(not p or p in (".", "..") or p[-1] in " ." or
                       any(ord(c) < 32 or c in '<>:"|?*' for c in p) or
                       p.split(".")[0].upper() in reserved for p in parts):
        raise ValueError(f"Unsafe archive path: {name!r}")
    target = (Path(root) / name).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise ValueError("Archive path escapes destination")
    return target
