from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

_O_RDONLY = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
_WHICH: dict[str, tuple[float, str | None]] = {}
_USERS: dict[int, str] = {}


def _read_bytes(path: Path | str, cap: int = 4096) -> bytes | None:
    try:
        fd = os.open(os.fspath(path), _O_RDONLY)
    except OSError:
        return None
    try:
        data = os.read(fd, cap)
    except OSError:
        return None
    finally:
        os.close(fd)
    return data


def read_text(path: Path | str) -> str | None:
    data = _read_bytes(path)
    if data is None:
        return None
    try:
        return data.decode("utf-8", "replace").strip()
    except UnicodeError:
        return None


def read_int(path: Path | str) -> int | None:
    data = _read_bytes(path, 64)
    if not data:
        return None
    try:
        return int(data.strip().split()[0])
    except (ValueError, IndexError):
        return None


def read_float(path: Path | str) -> float | None:
    data = _read_bytes(path, 64)
    if not data:
        return None
    try:
        return float(data.strip().split()[0])
    except (ValueError, IndexError):
        return None


def which(name: str, ttl: float = 30.0) -> str | None:
    now = time.time()
    hit = _WHICH.get(name)
    if hit is not None and now - hit[0] < ttl:
        return hit[1]
    from shutil import which as _which

    found = _which(name)
    _WHICH[name] = (now, found)
    return found


def run_cmd(
    argv: list[str],
    timeout: float = 2.0,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            env=env,
            input=input_text,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", f"{argv[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:.1f}s"
    except OSError as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def http_json(
    url: str,
    timeout: float = 1.2,
    data: dict[str, Any] | None = None,
    method: str | None = None,
) -> tuple[bool, Any, str]:
    import urllib.error
    import urllib.request

    payload = None
    headers = {"Accept": "application/json"}
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = method or "POST"
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, None, f"HTTP {exc.code}: {body[:240] or exc.reason}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, None, str(exc)
    if not raw.strip():
        return True, None, ""
    try:
        return True, json.loads(raw), ""
    except json.JSONDecodeError:
        return True, raw, ""


def fmt_bytes(n: int | float | None) -> str:
    if n is None:
        return "—"
    n = float(n)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024.0
        i += 1
    if i == 0:
        return f"{int(n)} {units[i]}"
    return f"{n:.1f} {units[i]}"


def fmt_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def current_uid() -> int:
    return os.getuid()


def username_for(uid: int) -> str:
    cached = _USERS.get(uid)
    if cached is not None:
        return cached
    try:
        import pwd

        name = pwd.getpwuid(uid).pw_name
    except (KeyError, OSError):
        name = str(uid)
    _USERS[uid] = name
    return name
