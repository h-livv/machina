from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from machina.paths import guardrails_path


DEFAULTS: dict[str, Any] = {
    "watchdog_enabled": True,
    "warn_temp_c": 90,
    "trip_temp_c": 97,
    "critical_temp_c": 100,
    "watchdog_cooldown_s": 45,
    "confirm_medium": True,
    "confirm_high": True,
    "nvidia_oem_default_w": 60,
    "nvidia_min_w": 30,
    "nvidia_max_w": 75,
    "nvidia_warn_above_w": 60,
    "nvidia_danger_above_w": 70,
    "rapl_pl1_min_w": 15,
    "rapl_pl1_max_w": 45,
    "rapl_pl2_min_w": 30,
    "rapl_pl2_max_w": 90,
    "min_perf_pct_floor": 10,
    "max_fan_warning": True,
}


def thresholds_ordered(warn: float, trip: float, critical: float) -> bool:
    return warn < trip < critical


PROFILE_BUNDLES: dict[str, dict[str, Any]] = {
    "cool": {
        "title": "Cool",
        "blurb": "Lowest heat and fan noise. Fine for writing, browsing, light work.",
        "actions": [
            {"op": "set_platform_profile", "value": "cool"},
            {"op": "set_governor", "value": "powersave"},
            {"op": "set_epp", "value": "power"},
            {"op": "set_fan_mode", "value": "auto"},
        ],
        "risk": "low",
    },
    "quiet": {
        "title": "Quiet",
        "blurb": "HP quiet policy with a power-biased CPU. Best all-day profile.",
        "actions": [
            {"op": "set_platform_profile", "value": "quiet"},
            {"op": "set_governor", "value": "powersave"},
            {"op": "set_epp", "value": "balance_power"},
            {"op": "set_fan_mode", "value": "auto"},
        ],
        "risk": "low",
    },
    "balanced": {
        "title": "Balanced",
        "blurb": "Default-like mix of boost and thermals. Safe restore target.",
        "actions": [
            {"op": "set_platform_profile", "value": "balanced"},
            {"op": "set_governor", "value": "performance"},
            {"op": "set_epp", "value": "balance_performance"},
            {"op": "set_fan_mode", "value": "auto"},
        ],
        "risk": "low",
    },
    "performance": {
        "title": "Performance",
        "blurb": "HP performance policy plus aggressive CPU energy preference. Runs hotter.",
        "actions": [
            {"op": "set_platform_profile", "value": "performance"},
            {"op": "set_governor", "value": "performance"},
            {"op": "set_epp", "value": "performance"},
            {"op": "set_fan_mode", "value": "auto"},
        ],
        "risk": "medium",
    },
}

SAFE_RESTORE = [
    {"op": "set_platform_profile", "value": "balanced"},
    {"op": "set_governor", "value": "performance"},
    {"op": "set_epp", "value": "balance_performance"},
    {"op": "set_fan_mode", "value": "auto"},
    {"op": "set_turbo", "enabled": True},
    {"op": "set_pstate", "min_pct": 20, "max_pct": 100},
    {"op": "set_rapl", "pl1_w": 45, "pl2_w": 90},
    {"op": "set_gpu_power_limit", "watts": 60},
]


_GUARDRAILS: dict[str, Any] | None = None
_GUARDRAILS_MTIME: int | None = None


def load_guardrails() -> dict[str, Any]:
    global _GUARDRAILS, _GUARDRAILS_MTIME
    path = guardrails_path()
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = None
    if _GUARDRAILS is not None and mtime == _GUARDRAILS_MTIME:
        return deepcopy(_GUARDRAILS)
    data = deepcopy(DEFAULTS)
    if mtime is not None:
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                data.update(stored)
        except (OSError, json.JSONDecodeError):
            pass
    _GUARDRAILS = data
    _GUARDRAILS_MTIME = mtime
    return data


def save_guardrails(data: dict[str, Any]) -> None:
    global _GUARDRAILS, _GUARDRAILS_MTIME
    merged = deepcopy(DEFAULTS)
    merged.update(data)
    guardrails_path().write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    _GUARDRAILS = merged
    try:
        _GUARDRAILS_MTIME = guardrails_path().stat().st_mtime_ns
    except OSError:
        _GUARDRAILS_MTIME = None


@dataclass
class Assessment:
    risk: str  # low | medium | high | blocked
    title: str
    summary: str
    bullets: list[str]
    blocked_reason: str | None = None


def _num(action: dict[str, Any], key: str) -> float | None:
    val = action.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def assess(actions: list[dict[str, Any]], cfg: dict[str, Any] | None = None, on_battery: bool = False) -> Assessment:
    cfg = cfg or load_guardrails()
    if not actions:
        return Assessment("blocked", "Nothing to apply", "No actions were requested.", [], "empty")

    bullets: list[str] = []
    risk_rank = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
    risk = "low"
    title = "Apply hardware changes"
    blocked = None

    def bump(level: str) -> None:
        nonlocal risk
        if risk_rank[level] > risk_rank[risk]:
            risk = level

    for action in actions:
        op = action.get("op")
        if op == "set_platform_profile":
            value = str(action.get("value", ""))
            if value not in {"cool", "quiet", "balanced", "performance"}:
                blocked = f"Unknown platform profile {value!r}"
                bump("blocked")
            else:
                bullets.append(f"HP platform profile → {value}")
                if value == "performance":
                    bump("medium")
                    if on_battery:
                        bullets.append("Performance mode on battery: expect faster drain and more heat.")
                        bump("high")
        elif op == "set_fan_mode":
            value = str(action.get("value", ""))
            if value not in {"auto", "max"}:
                blocked = f"Fan mode {value!r} is not allowed"
                bump("blocked")
            elif value == "max":
                bullets.append("Fans → maximum override (loud, extra power).")
                bump("medium")
            else:
                bullets.append("Fans → BIOS automatic control.")
        elif op == "set_turbo":
            enabled = bool(action.get("enabled", True))
            bullets.append("Intel Turbo → " + ("on" if enabled else "off"))
            if not enabled:
                bump("medium")
                bullets.append("Disabling turbo cuts peak CPU clocks significantly.")
        elif op == "set_epp":
            value = str(action.get("value", ""))
            allowed = {
                "default",
                "performance",
                "balance_performance",
                "balance_power",
                "power",
            }
            if value not in allowed:
                blocked = f"EPP {value!r} is not in the allowlist"
                bump("blocked")
            else:
                bullets.append(f"CPU energy preference → {value}")
                if value == "performance":
                    bump("medium")
        elif op == "set_governor":
            value = str(action.get("value", ""))
            if value not in {"performance", "powersave"}:
                blocked = f"Governor {value!r} is not allowed"
                bump("blocked")
            else:
                bullets.append(f"CPU governor → {value}")
        elif op == "set_pstate":
            mn = int(_num(action, "min_pct") or 0)
            mx = int(_num(action, "max_pct") or 0)
            floor = int(cfg["min_perf_pct_floor"])
            if not (floor <= mn <= 100 and floor <= mx <= 100 and mn <= mx):
                blocked = f"P-state limits {mn}/{mx} are outside {floor}–100"
                bump("blocked")
            else:
                bullets.append(f"Intel P-state min/max performance → {mn}% / {mx}%")
                if mx < 60:
                    bump("medium")
                    bullets.append("Capping max performance this low will feel slow.")
        elif op == "set_rapl":
            pl1 = _num(action, "pl1_w")
            pl2 = _num(action, "pl2_w")
            if pl1 is None or pl2 is None:
                blocked = "RAPL request is missing PL1 or PL2"
                bump("blocked")
            elif not (cfg["rapl_pl1_min_w"] <= pl1 <= cfg["rapl_pl1_max_w"]):
                blocked = f"PL1 {pl1} W is outside {cfg['rapl_pl1_min_w']}–{cfg['rapl_pl1_max_w']} W"
                bump("blocked")
            elif not (cfg["rapl_pl2_min_w"] <= pl2 <= cfg["rapl_pl2_max_w"]):
                blocked = f"PL2 {pl2} W is outside {cfg['rapl_pl2_min_w']}–{cfg['rapl_pl2_max_w']} W"
                bump("blocked")
            elif pl2 < pl1:
                blocked = "PL2 must be greater than or equal to PL1"
                bump("blocked")
            else:
                bullets.append(f"CPU RAPL PL1/PL2 → {pl1:.0f} / {pl2:.0f} W")
                if pl1 >= cfg["rapl_pl1_max_w"] and pl2 >= cfg["rapl_pl2_max_w"] - 1:
                    bump("medium")
        elif op == "set_gpu_power_limit":
            watts = _num(action, "watts")
            if watts is None:
                blocked = "GPU power limit missing"
                bump("blocked")
            elif watts < cfg["nvidia_min_w"] or watts > cfg["nvidia_max_w"]:
                blocked = (
                    f"GPU power {watts} W is outside Machina’s {cfg['nvidia_min_w']}–{cfg['nvidia_max_w']} W guardrail "
                    f"(hardware may allow a wider range)."
                )
                bump("blocked")
            else:
                bullets.append(f"NVIDIA power limit → {watts:.0f} W")
                if watts < 40:
                    bump("medium")
                    bullets.append("A low GPU cap will throttle games and CUDA hard.")
                if watts > cfg["nvidia_warn_above_w"]:
                    bump("medium")
                    bullets.append(f"Above HP’s {cfg['nvidia_oem_default_w']} W default: extra heat in the chassis.")
                if watts > cfg["nvidia_danger_above_w"]:
                    bump("high")
                    bullets.append("Near the board’s maximum. Sustained load can hit thermal limits quickly.")
        elif op == "set_backlight":
            pct = _num(action, "percent")
            if pct is None or not (1 <= pct <= 100):
                blocked = "Backlight percent must be 1–100"
                bump("blocked")
            else:
                bullets.append(f"Panel brightness → {pct:.0f}%")
        elif op == "signal_process":
            pid = int(_num(action, "pid") or 0)
            sig = str(action.get("signal", "term")).lower()
            if pid <= 1:
                blocked = "Refusing to signal pid ≤ 1"
                bump("blocked")
            elif sig not in {"term", "kill", "stop", "cont"}:
                blocked = f"Signal {sig!r} is not allowed"
                bump("blocked")
            else:
                bullets.append(f"Send SIG{sig.upper()} to pid {pid}")
                bump("high" if sig == "kill" else "medium")
        elif op == "systemctl":
            unit = str(action.get("unit", ""))
            verb = str(action.get("verb", ""))
            allowed_units = {"ollama.service", "docker.service", "nvidia-powerd.service"}
            if unit not in allowed_units:
                blocked = f"{unit} is not on the service allowlist"
                bump("blocked")
            elif verb not in {"start", "stop", "restart", "enable", "disable"}:
                blocked = f"systemctl {verb} is not allowed"
                bump("blocked")
            else:
                bullets.append(f"systemctl {verb} {unit}")
                if verb in {"enable", "disable"}:
                    bump("high")
                    bullets.append("This changes whether the unit starts at boot.")
                elif verb in {"stop", "restart"} and unit == "docker.service":
                    bump("medium")
                else:
                    bump("medium")
        elif op == "read_nvme_smart":
            bullets.append("Read NVMe SMART log (one-shot, privileged).")
        elif op == "restore_safe":
            bullets.append("Restore Machina’s conservative defaults (balanced, auto fans, turbo on, 45/90 W RAPL, 60 W GPU).")
            bump("medium")
        else:
            blocked = f"Operation {op!r} is not allowed"
            bump("blocked")

    if blocked:
        return Assessment("blocked", "Blocked by guardrails", blocked, bullets, blocked)

    summary = "These writes go to sysfs / nvidia-smi. They persist until something else changes them, or until reboot for some knobs."
    if risk == "high":
        title = "High-risk change"
    elif risk == "medium":
        title = "Confirm this change"
    else:
        title = "Apply settings"
    return Assessment(risk, title, summary, bullets)


def hottest_cpu(snapshot: Any) -> float | None:
    temps = []
    pkg = getattr(getattr(snapshot, "cpu", None), "package_temp_c", None)
    if pkg is not None:
        temps.append(pkg)
    gpu = getattr(getattr(snapshot, "gpu", None), "temp_c", None)
    if gpu is not None:
        temps.append(gpu)
    for point in getattr(snapshot, "thermals", []) or []:
        if point.source in {"coretemp", "acpitz"}:
            temps.append(point.temp_c)
    return max(temps) if temps else None


def watchdog_plan(snapshot: Any, cfg: dict[str, Any] | None = None) -> dict[str, Any] | None:
    cfg = cfg or load_guardrails()
    if not cfg.get("watchdog_enabled", True):
        return None
    cpu_t = getattr(getattr(snapshot, "cpu", None), "package_temp_c", None)
    gpu = getattr(snapshot, "gpu", None)
    gpu_t = getattr(gpu, "temp_c", None) if gpu is not None else None
    candidates = [t for t in (cpu_t, gpu_t) if t is not None]
    if not candidates:
        return None
    hot = max(candidates)
    critical = float(cfg["critical_temp_c"])
    trip = float(cfg["trip_temp_c"])
    warn = float(cfg["warn_temp_c"])
    if hot >= critical:
        return {
            "level": "critical",
            "temp": hot,
            "message": f"Thermal critical at {hot:.0f} °C. Machina will force cool profile, max fans, and a 45 W GPU cap.",
            "actions": [
                {"op": "set_platform_profile", "value": "cool"},
                {"op": "set_fan_mode", "value": "max"},
                {"op": "set_gpu_power_limit", "watts": 45},
                {"op": "set_epp", "value": "power"},
            ],
        }
    if hot >= trip:
        return {
            "level": "trip",
            "temp": hot,
            "message": f"Thermal trip at {hot:.0f} °C. Machina will force maximum fans until temperatures fall.",
            "actions": [{"op": "set_fan_mode", "value": "max"}],
        }
    if hot >= warn:
        return {
            "level": "warn",
            "temp": hot,
            "message": f"Package/GPU is {hot:.0f} °C. Consider Quiet/Cool or raising fans.",
            "actions": [],
        }
    return None
