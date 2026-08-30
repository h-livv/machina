"""FreeToken Desktop on this machine.

Daemon `:1900`, engine `:1919`, weights on Vault, AppImage under `~/opt/`.
Does not read or log secrets from `~/.config/freetoken/desktop.json`.
"""
from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any

from machina.paths import logs_dir
from machina.util import http_json

_SAFE_DESKTOP_KEYS = (
    "enginePort",
    "daemon_port",
    "serverHost",
    "models_dir",
    "lastActiveId",
    "autostart",
    "version",
    "cpuThreads",
    "moeMode",
    "memoryRatio",
    "concurrency",
)

_USER = os.environ.get("USER") or os.environ.get("LOGNAME") or "h-livv"
_DEFAULT_MODELS = Path(f"/run/media/{_USER}/Vault/freetoken")
_DEFAULT_APPIMAGE = Path.home() / "opt" / "freetoken-desktop-x86_64.appimage"

_DESKTOP_CACHE: tuple[int, dict[str, Any]] | None = None


def desktop_config() -> dict[str, Any]:
    """Allowlisted keys from FreeToken Desktop settings. Never includes tokens."""
    global _DESKTOP_CACHE
    path = Path.home() / ".config" / "freetoken" / "desktop.json"
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        _DESKTOP_CACHE = None
        return {}
    if _DESKTOP_CACHE and _DESKTOP_CACHE[0] == mtime_ns:
        return _DESKTOP_CACHE[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _DESKTOP_CACHE = (mtime_ns, {})
        return {}
    if not isinstance(data, dict):
        _DESKTOP_CACHE = (mtime_ns, {})
        return {}
    out = {key: data[key] for key in _SAFE_DESKTOP_KEYS if key in data}
    _DESKTOP_CACHE = (mtime_ns, out)
    return out


def daemon_base() -> str:
    env = os.environ.get("FREETOKEN_DAEMON") or os.environ.get("CITEHOP_FREETOKEN_DAEMON")
    if env:
        return env.rstrip("/")
    desktop = desktop_config()
    host = str(desktop.get("serverHost") or "127.0.0.1")
    port = int(desktop.get("daemon_port") or 1900)
    return f"http://{host}:{port}"


def engine_base() -> str:
    env = os.environ.get("FREETOKEN_ENGINE") or os.environ.get("FREETOKEN_HOST") or os.environ.get(
        "CITEHOP_FREETOKEN_HOST"
    )
    if env:
        return env.rstrip("/")
    desktop = desktop_config()
    host = str(desktop.get("serverHost") or "127.0.0.1")
    port = int(desktop.get("enginePort") or 1919)
    return f"http://{host}:{port}"


def models_dir() -> Path:
    env = os.environ.get("FREETOKEN_DIR") or os.environ.get("CITEHOP_FREETOKEN_DIR")
    if env:
        return Path(env).expanduser()
    desktop = desktop_config()
    raw = desktop.get("models_dir")
    if isinstance(raw, str) and raw.strip():
        return Path(raw)
    return _DEFAULT_MODELS


def appimage_path() -> Path | None:
    env = os.environ.get("FREETOKEN_APPIMAGE")
    if env:
        path = Path(env).expanduser()
        return path if path.is_file() else None
    preferred = _DEFAULT_APPIMAGE
    if preferred.is_file():
        return preferred
    opt = Path.home() / "opt"
    try:
        matches = sorted(opt.glob("freetoken-desktop*.appimage")) + sorted(opt.glob("freetoken-desktop*.AppImage"))
    except OSError:
        return None
    for path in matches:
        if path.is_file():
            return path
    return None


def log_path() -> Path:
    return logs_dir() / "freetoken-desktop.log"


def daemon_health() -> dict[str, Any]:
    ok, data, err = http_json(f"{daemon_base()}/health", timeout=0.6)
    if not ok or not isinstance(data, dict):
        return {"ok": False, "error": err or "FreeToken daemon is not reachable"}
    return {
        "ok": True,
        "version": str(data.get("version") or "") or None,
        "uptime_s": _as_number(data.get("uptimeS")),
        "engine_running": bool(data.get("engineRunning")),
    }


def engine_status() -> dict[str, Any]:
    ok, data, err = http_json(f"{daemon_base()}/engine/status", timeout=0.8)
    if not ok or not isinstance(data, dict):
        return {"error": err or "engine/status failed"}
    model = data.get("model")
    model_s = str(model) if isinstance(model, str) and model.strip() else None
    return {
        "running": bool(data.get("running")),
        "starting": bool(data.get("starting")),
        "stopping": bool(data.get("stopping")),
        "pid": _as_int(data.get("pid")),
        "model": model_s,
        "port": _as_int(data.get("port")),
        "uptime_s": _as_number(data.get("uptimeS")),
        "last_exit_code": data.get("lastExitCode"),
        "last_exit_reason": str(data.get("lastExitReason") or "") or None,
    }


def list_weights(root: Path | None = None) -> list[dict[str, Any]]:
    root = root or models_dir()
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    try:
        children = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []
    for child in children:
        if not (child / "config.json").is_file():
            continue
        rows.append({"name": child.name, "path": str(child)})
    return rows


def ui_running() -> bool:
    needle = None
    image = appimage_path()
    if image is not None:
        needle = image.name.lower()
    for _pid, cmd in _iter_cmdlines():
        low = cmd.lower()
        if "ft daemon" in low or "freetoken daemon" in low:
            continue
        if "freetoken-desktop" in low or "freetoken_desktop" in low:
            return True
        if needle and needle in low:
            return True
    return False


def model_basename(path: str | None) -> str | None:
    if not path:
        return None
    name = Path(path).name
    return name or None


def stop_engine(timeout_s: float = 20.0) -> dict[str, Any]:
    """POST /engine/stop (force) and wait until the serve is gone."""
    health = daemon_health()
    if not health.get("ok"):
        return {"skipped": True, "already": True, "stopped": False}
    status = engine_status()
    current = model_basename(status.get("model") if isinstance(status.get("model"), str) else None)
    status_ok = "running" in status
    busy = bool(status.get("running") or status.get("starting") or status.get("stopping"))
    if status_ok and not busy:
        _wait_gpu_workers(timeout_s=min(6.0, timeout_s))
        return {"stopped": True, "already": True, "model": current}
    ok, payload, err = http_json(
        f"{daemon_base()}/engine/stop",
        timeout=max(12.0, min(timeout_s, 40.0)),
        data={"force": True},
    )
    if not ok:
        return {"ok": False, "error": err or "FreeToken engine/stop failed", "model": current}
    if isinstance(payload, dict) and payload.get("already"):
        _wait_gpu_workers(timeout_s=min(8.0, timeout_s))
        return {"stopped": True, "already": True, "model": current, "status": payload}
    deadline = time.monotonic() + timeout_s
    last = payload if isinstance(payload, dict) else {}
    while time.monotonic() < deadline:
        last = engine_status()
        if not last.get("running") and not last.get("starting"):
            _wait_gpu_workers(timeout_s=min(12.0, timeout_s))
            return {"stopped": True, "already": False, "model": current, "status": last}
        time.sleep(0.4)
    return {
        "ok": False,
        "error": "FreeToken engine did not exit after /engine/stop. Stop it in the FreeToken UI if it is still loaded.",
        "model": current,
        "status": last,
    }


def _wait_gpu_workers(timeout_s: float = 8.0) -> None:
    """CUDA workers can outlive the serve PID by a few seconds."""
    deadline = time.monotonic() + max(0.4, timeout_s)
    leftover: list[int] = []
    while time.monotonic() < deadline:
        leftover = _gpu_worker_pids()
        if not leftover:
            return
        time.sleep(0.4)
    for pid in leftover:
        _kill(pid, signal.SIGTERM)
    time.sleep(0.5)
    for pid in _gpu_worker_pids():
        _kill(pid, signal.SIGKILL)


def _gpu_worker_pids() -> list[int]:
    from machina.processes import collect_gpu_procs

    apps, _err = collect_gpu_procs()
    pids: list[int] = []
    for app in apps:
        cmd = _cmdline(app.pid)
        if _is_engine_worker(cmd):
            pids.append(app.pid)
    return pids


def _is_engine_worker(cmd: str) -> bool:
    low = cmd.lower()
    if "ft daemon" in low or "freetoken daemon" in low:
        return False
    if "freetoken-desktop" in low:
        return False
    return ".freetoken" in cmd or "freetoken.cli" in cmd


def _iter_cmdlines() -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    proc = Path("/proc")
    try:
        entries = proc.iterdir()
    except OSError:
        return rows
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if raw:
            rows.append((int(entry.name), raw))
    return rows


def _cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _kill(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except OSError:
        return


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _as_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
