#!/usr/bin/env python3
"""Privileged (and unprivileged) apply path. Stdlib only — safe to pkexec."""
from __future__ import annotations

import json
import os
import signal as posix_signal
import subprocess
import sys
from pathlib import Path
from typing import Any

ALLOWED_PROFILES = {"cool", "quiet", "balanced", "performance"}
ALLOWED_EPP = {"default", "performance", "balance_performance", "balance_power", "power"}
ALLOWED_GOV = {"performance", "powersave"}
NVIDIA_SMI = "/usr/bin/nvidia-smi"

# Hardware floors/ceilings duplicated here so pkexec cannot be talked into
# writing values the GUI never would.
PL1_RANGE = (15, 45)
PL2_RANGE = (30, 90)
GPU_RANGE = (30, 75)
PSTATE_FLOOR = 10


def _write(path: Path, value: str) -> None:
    path.write_text(value if value.endswith("\n") else value + "\n", encoding="utf-8")


def find_hwmon(name: str) -> Path | None:
    root = Path("/sys/class/hwmon")
    if not root.exists():
        return None
    for entry in root.iterdir():
        try:
            if (entry / "name").read_text(encoding="utf-8").strip() == name:
                return entry
        except OSError:
            continue
    return None


def _all_cpu_glob(rel: str) -> list[Path]:
    return sorted(Path("/sys/devices/system/cpu").glob(f"cpu[0-9]*/cpufreq/{rel}"))


def apply_one(action: dict[str, Any]) -> str:
    op = action.get("op")
    if op == "set_platform_profile":
        value = str(action.get("value", ""))
        if value not in ALLOWED_PROFILES:
            raise ValueError(f"profile {value!r} not allowed")
        _write(Path("/sys/firmware/acpi/platform_profile"), value)
        return f"platform_profile={value}"
    if op == "set_fan_mode":
        value = str(action.get("value", ""))
        hw = find_hwmon("hp")
        if hw is None:
            raise FileNotFoundError("hp hwmon not found")
        target = hw / "pwm1_enable"
        if value == "auto":
            _write(target, "2")
            return "pwm1_enable=2"
        if value == "max":
            _write(target, "0")
            return "pwm1_enable=0"
        raise ValueError("fan mode must be auto or max")
    if op == "set_turbo":
        enabled = bool(action.get("enabled", True))
        _write(Path("/sys/devices/system/cpu/intel_pstate/no_turbo"), "0" if enabled else "1")
        return f"no_turbo={0 if enabled else 1}"
    if op == "set_epp":
        value = str(action.get("value", ""))
        if value not in ALLOWED_EPP:
            raise ValueError(f"epp {value!r} not allowed")
        paths = _all_cpu_glob("energy_performance_preference")
        if not paths:
            raise FileNotFoundError("no EPP sysfs nodes")
        for path in paths:
            _write(path, value)
        return f"epp={value} cpus={len(paths)}"
    if op == "set_governor":
        value = str(action.get("value", ""))
        if value not in ALLOWED_GOV:
            raise ValueError(f"governor {value!r} not allowed")
        paths = _all_cpu_glob("scaling_governor")
        if not paths:
            raise FileNotFoundError("no governor sysfs nodes")
        for path in paths:
            _write(path, value)
        return f"governor={value} cpus={len(paths)}"
    if op == "set_pstate":
        mn = int(action["min_pct"])
        mx = int(action["max_pct"])
        if not (PSTATE_FLOOR <= mn <= 100 and PSTATE_FLOOR <= mx <= 100 and mn <= mx):
            raise ValueError("pstate limits out of range")
        base = Path("/sys/devices/system/cpu/intel_pstate")
        _write(base / "max_perf_pct", str(mx))
        _write(base / "min_perf_pct", str(mn))
        return f"min_perf_pct={mn} max_perf_pct={mx}"
    if op == "set_rapl":
        pl1 = float(action["pl1_w"])
        pl2 = float(action["pl2_w"])
        if not (PL1_RANGE[0] <= pl1 <= PL1_RANGE[1] and PL2_RANGE[0] <= pl2 <= PL2_RANGE[1] and pl2 >= pl1):
            raise ValueError("RAPL limits rejected")
        rapl = Path("/sys/class/powercap/intel-rapl:0")
        _write(rapl / "constraint_0_power_limit_uw", str(int(pl1 * 1_000_000)))
        _write(rapl / "constraint_1_power_limit_uw", str(int(pl2 * 1_000_000)))
        return f"rapl pl1={pl1:.0f}W pl2={pl2:.0f}W"
    if op == "set_gpu_power_limit":
        watts = int(round(float(action["watts"])))
        if not (GPU_RANGE[0] <= watts <= GPU_RANGE[1]):
            raise ValueError("GPU power limit rejected")
        smi = NVIDIA_SMI if Path(NVIDIA_SMI).exists() else "nvidia-smi"
        proc = subprocess.run(
            [smi, "--power-limit", str(watts)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "nvidia-smi failed").strip()[:400])
        return f"nvidia-smi --power-limit {watts}"
    if op == "set_backlight":
        pct = float(action["percent"])
        if not (1 <= pct <= 100):
            raise ValueError("backlight percent out of range")
        root = Path("/sys/class/backlight")
        chosen = None
        for entry in sorted(root.iterdir()) if root.exists() else []:
            if "intel" in entry.name or "amd" in entry.name:
                chosen = entry
                break
        if chosen is None and root.exists():
            entries = sorted(root.iterdir())
            chosen = entries[0] if entries else None
        if chosen is None:
            raise FileNotFoundError("no backlight device")
        mx = int((chosen / "max_brightness").read_text().strip())
        value = max(1, min(mx, int(round(mx * pct / 100.0))))
        _write(chosen / "brightness", str(value))
        return f"backlight={value}/{mx}"
    if op == "signal_process":
        pid = int(action["pid"])
        if pid <= 1:
            raise ValueError("refusing pid <= 1")
        sig_name = str(action.get("signal", "term")).lower()
        allowed = {
            "term": posix_signal.SIGTERM,
            "kill": posix_signal.SIGKILL,
            "stop": posix_signal.SIGSTOP,
            "cont": posix_signal.SIGCONT,
        }
        if sig_name not in allowed:
            raise ValueError("signal not allowed")
        if pid == os.getpid():
            raise ValueError("refusing to signal the helper itself")
        os.kill(pid, allowed[sig_name])
        return f"signal {sig_name} -> {pid}"
    if op == "systemctl":
        unit = str(action.get("unit", ""))
        verb = str(action.get("verb", ""))
        scope = str(action.get("scope", "system"))
        allowed_units = {"ollama.service", "docker.service", "nvidia-powerd.service"}
        if unit not in allowed_units:
            raise ValueError(f"unit {unit!r} is not allowlisted")
        if verb not in {"start", "stop", "restart", "enable", "disable"}:
            raise ValueError("systemctl verb not allowed")
        if scope != "system":
            raise ValueError("privileged helper only runs system units")
        proc = subprocess.run(
            ["systemctl", verb, unit],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "systemctl failed").strip()[:400])
        return f"systemctl {verb} {unit}"
    if op == "read_nvme_smart":
        nvme = "/usr/bin/nvme" if Path("/usr/bin/nvme").exists() else "nvme"
        proc = subprocess.run(
            [nvme, "smart-log", "/dev/nvme0n1"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "nvme smart-log failed").strip()[:400])
        return (proc.stdout or "")[:4000]
    if op == "restore_safe":
        results = []
        for nested in (
            {"op": "set_platform_profile", "value": "balanced"},
            {"op": "set_governor", "value": "performance"},
            {"op": "set_epp", "value": "balance_performance"},
            {"op": "set_fan_mode", "value": "auto"},
            {"op": "set_turbo", "enabled": True},
            {"op": "set_pstate", "min_pct": 20, "max_pct": 100},
            {"op": "set_rapl", "pl1_w": 45, "pl2_w": 90},
            {"op": "set_gpu_power_limit", "watts": 60},
        ):
            try:
                results.append(apply_one(nested))
            except Exception as exc:  # noqa: BLE001 — report each restore step
                results.append(f"FAIL {nested['op']}: {exc}")
        return "; ".join(results)
    raise ValueError(f"unknown op {op!r}")


def apply_all(actions: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    errors = []
    for action in actions:
        try:
            results.append({"action": action, "ok": True, "detail": apply_one(action)})
        except Exception as exc:  # noqa: BLE001
            errors.append({"action": action, "ok": False, "detail": str(exc)})
            results.append({"action": action, "ok": False, "detail": str(exc)})
    return {"ok": not errors, "results": results, "errors": errors, "uid": os.geteuid()}


def try_unprivileged(actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Attempt writes as the current user. Returns leftover actions that need root."""
    leftover: list[dict[str, Any]] = []
    done: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for action in actions:
        try:
            detail = apply_one(action)
            done.append({"action": action, "ok": True, "detail": detail})
        except PermissionError:
            leftover.append(action)
        except Exception as exc:  # noqa: BLE001
            errors.append({"action": action, "ok": False, "detail": str(exc)})
    return {"done": done, "leftover": leftover, "errors": errors}


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"ok": False, "errors": [{"detail": "empty stdin"}]}))
        return 2
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [{"detail": f"invalid json: {exc}"}]}))
        return 2
    actions = payload.get("actions")
    if not isinstance(actions, list):
        print(json.dumps({"ok": False, "errors": [{"detail": "payload.actions must be a list"}]}))
        return 2
    result = apply_all(actions)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
