from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from machina.paths import services_config_path
from machina.util import run_cmd

# Units this machine actually uses for compute / GPU / local models.
# KDE session units are excluded on purpose.
DEFAULT_UNITS = [
    {"unit": "ollama.service", "scope": "system", "why": "Local LLM server (system unit runs as ollama, not your Vault models)."},
    {"unit": "docker.service", "scope": "system", "why": "Container engine for occasional workloads."},
    {"unit": "nvidia-powerd.service", "scope": "system", "why": "NVIDIA Dynamic Boost helper."},
]


@dataclass
class Service:
    unit: str
    scope: str  # system | user
    load: str
    active: str
    sub: str
    description: str
    enabled: str | None
    why: str
    running: bool
    allowed: tuple[str, ...]


ALLOWED_VERBS = ("start", "stop", "restart", "enable", "disable")


def allowed_units() -> list[dict[str, str]]:
    units = list(DEFAULT_UNITS)
    path = services_config_path()
    if path.exists():
        try:
            extra = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(extra, dict):
                for item in extra.get("units") or []:
                    if isinstance(item, dict) and item.get("unit"):
                        units.append(
                            {
                                "unit": str(item["unit"]),
                                "scope": str(item.get("scope") or "system"),
                                "why": str(item.get("why") or "Listed in services.json"),
                            }
                        )
            elif isinstance(extra, list):
                for name in extra:
                    units.append({"unit": str(name), "scope": "system", "why": "Listed in services.json"})
        except (OSError, json.JSONDecodeError):
            pass
    seen: set[tuple[str, str]] = set()
    out = []
    for item in units:
        key = (item["unit"], item["scope"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def collect_services() -> list[Service]:
    specs = allowed_units()
    by_scope: dict[str, list[dict[str, str]]] = {}
    for spec in specs:
        by_scope.setdefault(spec["scope"], []).append(spec)
    rows: list[Service] = []
    for scope, items in by_scope.items():
        shown = _show_units([item["unit"] for item in items], scope)
        for spec in items:
            props = shown.get(spec["unit"], {})
            rows.append(_from_props(spec["unit"], spec["scope"], spec.get("why") or "", props))
    return rows


def _show_units(units: list[str], scope: str) -> dict[str, dict[str, str]]:
    if not units:
        return {}
    argv = ["systemctl"]
    if scope == "user":
        argv.append("--user")
    argv += [
        "show",
        "--no-page",
        "-p",
        "Id",
        "-p",
        "LoadState",
        "-p",
        "ActiveState",
        "-p",
        "SubState",
        "-p",
        "Description",
        "-p",
        "UnitFileState",
        *units,
    ]
    code, out, _err = run_cmd(argv, timeout=1.5)
    result: dict[str, dict[str, str]] = {}
    if code != 0:
        return result
    current: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip():
            if current:
                result[current.get("Id") or ""] = current
                current = {}
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            current[key] = value
    if current:
        result[current.get("Id") or ""] = current
    return result


def _from_props(unit: str, scope: str, why: str, props: dict[str, str]) -> Service:
    active = props.get("ActiveState", "unknown")
    return Service(
        unit=unit,
        scope=scope,
        load=props.get("LoadState", "unknown"),
        active=active,
        sub=props.get("SubState", ""),
        description=props.get("Description") or unit,
        enabled=props.get("UnitFileState") or None,
        why=why,
        running=active == "active",
        allowed=ALLOWED_VERBS,
    )


def _one(unit: str, scope: str, why: str) -> Service:
    shown = _show_units([unit], scope)
    return _from_props(unit, scope, why, shown.get(unit, {}))


def is_allowed_unit(unit: str, scope: str) -> bool:
    return any(item["unit"] == unit and item["scope"] == scope for item in allowed_units())
