from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from machina.nvml import query_gpu as _nvml_gpu
from machina.util import read_float, read_int, read_text


SYSFS = Path("/sys")
_read_text = read_text
_read_int = read_int
_read_float = read_float

_HWMON: dict[str, Path | None] = {}
_HWMON_TS = 0.0
_CPU_MODEL: str | None = None
_THERMAL_LAYOUT: list[tuple[str, str, Path, float | None, float | None]] | None = None
_THERMAL_TS = 0.0
_FAN_HW: Path | None | bool = False
_FAN_TS = 0.0
_FAN_INPUTS: list[Path] = []
_CORETEMP_INPUTS: list[tuple[str, Path]] | None = None
_CPU_STATIC: dict[str, Any] | None = None
_INDEX_TTL = 45.0


def find_hwmon(name: str) -> Path | None:
    _index_hwmon()
    return _HWMON.get(name)


def _index_hwmon(force: bool = False) -> None:
    global _HWMON_TS
    now = time.time()
    if not force and _HWMON and (now - _HWMON_TS) < _INDEX_TTL:
        return
    _HWMON.clear()
    root = Path("/sys/class/hwmon")
    if not root.exists():
        _HWMON_TS = now
        return
    try:
        entries = list(root.iterdir())
    except OSError:
        _HWMON_TS = now
        return
    for entry in entries:
        chip = _read_text(entry / "name")
        if chip and chip not in _HWMON:
            _HWMON[chip] = entry
    _HWMON_TS = now


def millideg_c(value: int | None) -> float | None:
    if value is None:
        return None
    return value / 1000.0


@dataclass
class HostInfo:
    hostname: str
    vendor: str
    product: str
    bios: str
    kernel: str
    os_pretty: str
    chassis: str


@dataclass
class CpuCore:
    index: int
    freq_mhz: float | None
    governor: str | None
    epp: str | None
    usage: float | None = None
    temp_c: float | None = None


@dataclass
class CpuInfo:
    model: str
    logical_cpus: int
    usage: float | None
    package_temp_c: float | None
    cores: list[CpuCore]
    governor: str | None
    governors: list[str]
    epp: str | None
    epp_available: list[str]
    driver: str | None
    min_mhz: float | None
    max_mhz: float | None
    avg_mhz: float | None
    turbo_enabled: bool | None
    min_perf_pct: int | None
    max_perf_pct: int | None
    hwp_dynamic_boost: bool | None
    pstate_status: str | None
    loadavg: tuple[float, float, float]


@dataclass
class GpuInfo:
    present: bool
    name: str | None = None
    driver: str | None = None
    temp_c: float | None = None
    util: float | None = None
    mem_util: float | None = None
    power_w: float | None = None
    power_limit_w: float | None = None
    power_min_w: float | None = None
    power_max_w: float | None = None
    power_default_w: float | None = None
    clock_graphics_mhz: float | None = None
    clock_memory_mhz: float | None = None
    mem_used_mib: float | None = None
    mem_total_mib: float | None = None
    pstate: str | None = None
    thermal_slowdown: bool | None = None
    hw_thermal_slowdown: bool | None = None
    error: str | None = None


@dataclass
class IgpuInfo:
    present: bool
    cur_mhz: float | None = None
    min_mhz: float | None = None
    max_mhz: float | None = None
    boost_mhz: float | None = None


@dataclass
class FanInfo:
    present: bool
    name: str | None
    rpm: list[int]
    pwm_enable: int | None
    mode: str
    mode_label: str
    note: str


@dataclass
class ThermalPoint:
    source: str
    label: str
    temp_c: float
    high_c: float | None = None
    crit_c: float | None = None


@dataclass
class BatteryInfo:
    present: bool
    status: str | None = None
    percent: int | None = None
    power_w: float | None = None
    voltage_v: float | None = None
    energy_now_wh: float | None = None
    energy_full_wh: float | None = None
    energy_design_wh: float | None = None
    health_pct: float | None = None
    cycle_count: int | None = None
    ac_online: bool | None = None


@dataclass
class RaplLimit:
    name: str
    power_limit_w: float | None
    max_power_w: float | None
    window_s: float | None
    writable: bool


@dataclass
class PowerInfo:
    rapl_limits: list[RaplLimit]
    package_power_w: float | None
    rapl_energy_readable: bool


@dataclass
class ProfileInfo:
    current: str | None
    choices: list[str]
    writable: bool


@dataclass
class BacklightInfo:
    present: bool
    name: str | None = None
    percent: float | None = None
    brightness: int | None = None
    max_brightness: int | None = None


@dataclass
class MemoryInfo:
    total_b: int | None = None
    used_b: int | None = None
    available_b: int | None = None
    swap_total_b: int | None = None
    swap_used_b: int | None = None


@dataclass
class ThrottleInfo:
    available: bool
    core_count: int | None = None
    package_count: int | None = None
    core_total_ms: int | None = None
    package_total_ms: int | None = None
    rising: bool = False
    note: str = ""


@dataclass
class SourceStatus:
    name: str
    ok: bool
    ts: float
    detail: str | None = None
    stale: bool = False


@dataclass
class Snapshot:
    ts: float
    host: HostInfo
    cpu: CpuInfo
    gpu: GpuInfo
    igpu: IgpuInfo
    fans: FanInfo
    thermals: list[ThermalPoint]
    battery: BatteryInfo
    power: PowerInfo
    profile: ProfileInfo
    backlight: BacklightInfo
    memory: MemoryInfo
    throttle: ThrottleInfo
    notes: list[str] = field(default_factory=list)
    sources: dict[str, SourceStatus] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(self)


def _to_plain(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    return obj


def _cpu_model() -> str:
    global _CPU_MODEL
    if _CPU_MODEL is not None:
        return _CPU_MODEL
    path = Path("/proc/cpuinfo")
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name"):
                _CPU_MODEL = line.split(":", 1)[1].strip()
                return _CPU_MODEL
    except OSError:
        pass
    _CPU_MODEL = "Unknown CPU"
    return _CPU_MODEL


def _os_pretty() -> str:
    path = Path("/etc/os-release")
    text = _read_text(path) or ""
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return os.uname().sysname


def _read_cpu_times() -> tuple[int, int, list[tuple[int, int]]]:
    idle = 0
    total = 0
    cores: list[tuple[int, int]] = []
    try:
        lines = Path("/proc/stat").read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0, 0, []
    for line in lines:
        if not line.startswith("cpu"):
            continue
        parts = line.split()
        if not parts:
            continue
        nums = [int(x) for x in parts[1:]]
        iowait = nums[3] + (nums[4] if len(nums) > 4 else 0)
        tot = sum(nums)
        if parts[0] == "cpu":
            total, idle = tot, iowait
        elif re.fullmatch(r"cpu\d+", parts[0]):
            cores.append((tot, iowait))
    return total, idle, cores


def _usage_from(prev: tuple[int, int] | None, cur: tuple[int, int]) -> float | None:
    if prev is None:
        return None
    dt = cur[0] - prev[0]
    if dt <= 0:
        return None
    didle = cur[1] - prev[1]
    used = dt - didle
    return max(0.0, min(100.0, 100.0 * used / dt))


def _collect_host() -> HostInfo:
    dmi = Path("/sys/class/dmi/id")
    return HostInfo(
        hostname=os.uname().nodename,
        vendor=_read_text(dmi / "sys_vendor") or "Unknown",
        product=_read_text(dmi / "product_name") or "Unknown",
        bios=_read_text(dmi / "bios_version") or "",
        kernel=os.uname().release,
        os_pretty=_os_pretty(),
        chassis=_read_text(dmi / "chassis_type") or "",
    )


def _collect_cpu(prev_times: tuple[int, int] | None, prev_cores: list[tuple[int, int]] | None) -> tuple[CpuInfo, tuple[int, int], list[tuple[int, int]]]:
    total, idle, core_times = _read_cpu_times()
    usage = _usage_from(prev_times, (total, idle))
    cpu0 = Path("/sys/devices/system/cpu/cpu0/cpufreq")
    pstate = Path("/sys/devices/system/cpu/intel_pstate")
    logical = os.cpu_count() or 0
    cores: list[CpuCore] = []
    freqs: list[float] = []
    temps_by_core: dict[int, float] = {}
    package_temp = None
    global _CORETEMP_INPUTS
    if _CORETEMP_INPUTS is None:
        mapped: list[tuple[str, Path]] = []
        hwmon = find_hwmon("coretemp")
        if hwmon:
            for inp in sorted(hwmon.glob("temp*_input")):
                label = _read_text(Path(str(inp).replace("_input", "_label"))) or inp.name
                mapped.append((label, inp))
        _CORETEMP_INPUTS = mapped
    for label, inp in _CORETEMP_INPUTS:
        temp = millideg_c(_read_int(inp))
        if temp is None:
            continue
        if "package" in label.lower():
            package_temp = temp
        elif label.lower().startswith("core "):
            try:
                temps_by_core[int(label.split()[-1])] = temp
            except ValueError:
                pass

    global _CPU_STATIC
    if _CPU_STATIC is None:
        _CPU_STATIC = {
            "epp_avail": (_read_text(cpu0 / "energy_performance_available_preferences") or "").split(),
            "governors": (_read_text(cpu0 / "scaling_available_governors") or "").split(),
            "driver": _read_text(cpu0 / "scaling_driver"),
            "min_k": _read_int(cpu0 / "cpuinfo_min_freq") or _read_int(cpu0 / "scaling_min_freq"),
            "max_k": _read_int(cpu0 / "cpuinfo_max_freq") or _read_int(cpu0 / "scaling_max_freq"),
        }
    epp_avail = _CPU_STATIC["epp_avail"]
    governors = _CPU_STATIC["governors"]
    for idx in range(logical):
        base = Path(f"/sys/devices/system/cpu/cpu{idx}/cpufreq")
        freq_khz = _read_int(base / "scaling_cur_freq")
        freq_mhz = freq_khz / 1000.0 if freq_khz else None
        if freq_mhz:
            freqs.append(freq_mhz)
        core_usage = None
        if prev_cores and idx < len(prev_cores) and idx < len(core_times):
            core_usage = _usage_from(prev_cores[idx], core_times[idx])
        # Intel hybrid labels (0,4,8,12,20...) don't map 1:1 to logical index.
        temp = temps_by_core.get(idx)
        cores.append(
            CpuCore(
                index=idx,
                freq_mhz=freq_mhz,
                governor=_read_text(base / "scaling_governor"),
                epp=_read_text(base / "energy_performance_preference"),
                usage=core_usage,
                temp_c=temp,
            )
        )

    no_turbo = _read_int(pstate / "no_turbo")
    min_k = _CPU_STATIC["min_k"] if _CPU_STATIC else (_read_int(cpu0 / "cpuinfo_min_freq") or _read_int(cpu0 / "scaling_min_freq"))
    max_k = _CPU_STATIC["max_k"] if _CPU_STATIC else (_read_int(cpu0 / "cpuinfo_max_freq") or _read_int(cpu0 / "scaling_max_freq"))
    try:
        loadavg = os.getloadavg()
    except OSError:
        loadavg = (0.0, 0.0, 0.0)

    info = CpuInfo(
        model=_cpu_model(),
        logical_cpus=logical,
        usage=usage,
        package_temp_c=package_temp,
        cores=cores,
        governor=_read_text(cpu0 / "scaling_governor"),
        governors=governors,
        epp=_read_text(cpu0 / "energy_performance_preference"),
        epp_available=epp_avail,
        driver=_CPU_STATIC["driver"] if _CPU_STATIC else _read_text(cpu0 / "scaling_driver"),
        min_mhz=(min_k / 1000.0) if min_k else None,
        max_mhz=(max_k / 1000.0) if max_k else None,
        avg_mhz=(sum(freqs) / len(freqs)) if freqs else None,
        turbo_enabled=None if no_turbo is None else (no_turbo == 0),
        min_perf_pct=_read_int(pstate / "min_perf_pct"),
        max_perf_pct=_read_int(pstate / "max_perf_pct"),
        hwp_dynamic_boost=None
        if _read_int(pstate / "hwp_dynamic_boost") is None
        else bool(_read_int(pstate / "hwp_dynamic_boost")),
        pstate_status=_read_text(pstate / "status"),
        loadavg=loadavg,
    )
    return info, (total, idle), core_times


def _parse_nvidia_number(raw: str) -> float | None:
    raw = raw.strip()
    if not raw or raw in {"[N/A]", "N/A", "[Not Supported]", "Not Supported"}:
        return None
    raw = raw.replace("%", "").replace("W", "").replace("MHz", "").replace("MiB", "").replace("C", "")
    try:
        return float(raw.split()[0])
    except (ValueError, IndexError):
        return None


def _collect_nvidia() -> GpuInfo:
    nv = _nvml_gpu()
    if nv is not None:
        return GpuInfo(present=True, **nv)
    return _collect_nvidia_smi()


def _collect_nvidia_smi() -> GpuInfo:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return GpuInfo(present=False, error="nvidia-smi not found")
    query = (
        "name,driver_version,temperature.gpu,utilization.gpu,utilization.memory,"
        "power.draw,enforced.power.limit,power.min_limit,power.max_limit,"
        "clocks.gr,clocks.mem,memory.used,memory.total,pstate,"
        "clocks_event_reasons.sw_thermal_slowdown,clocks_event_reasons.hw_thermal_slowdown,"
        "power.default_limit"
    )
    try:
        proc = subprocess.run(
            [smi, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return GpuInfo(present=True, error=str(exc))
    if proc.returncode != 0:
        return GpuInfo(present=True, error=(proc.stderr or proc.stdout or "nvidia-smi failed").strip()[:200])
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return GpuInfo(present=True, error="nvidia-smi returned no data")
    parts = [p.strip() for p in line[0].split(",")]
    while len(parts) < 17:
        parts.append("")

    def flag(val: str) -> bool | None:
        v = val.strip().lower()
        if v in {"active", "yes", "true", "1"}:
            return True
        if v in {"not active", "no", "false", "0", "n/a", "[n/a]", ""}:
            return False if v not in {"", "n/a", "[n/a]"} else None
        if "not active" in v:
            return False
        if v == "active":
            return True
        return None

    return GpuInfo(
        present=True,
        name=parts[0] or None,
        driver=parts[1] or None,
        temp_c=_parse_nvidia_number(parts[2]),
        util=_parse_nvidia_number(parts[3]),
        mem_util=_parse_nvidia_number(parts[4]),
        power_w=_parse_nvidia_number(parts[5]),
        power_limit_w=_parse_nvidia_number(parts[6]),
        power_min_w=_parse_nvidia_number(parts[7]),
        power_max_w=_parse_nvidia_number(parts[8]),
        clock_graphics_mhz=_parse_nvidia_number(parts[9]),
        clock_memory_mhz=_parse_nvidia_number(parts[10]),
        mem_used_mib=_parse_nvidia_number(parts[11]),
        mem_total_mib=_parse_nvidia_number(parts[12]),
        pstate=parts[13] or None,
        thermal_slowdown=flag(parts[14]),
        hw_thermal_slowdown=flag(parts[15]),
        power_default_w=_parse_nvidia_number(parts[16]),
    )


def _collect_igpu() -> IgpuInfo:
    drm = Path("/sys/class/drm")
    if not drm.exists():
        return IgpuInfo(present=False)
    for card in sorted(drm.glob("card*")):
        if not card.is_dir() or "-" in card.name:
            continue
        cur = _read_int(card / "gt_cur_freq_mhz")
        if cur is None:
            continue
        return IgpuInfo(
            present=True,
            cur_mhz=float(cur),
            min_mhz=_read_float(card / "gt_min_freq_mhz"),
            max_mhz=_read_float(card / "gt_max_freq_mhz"),
            boost_mhz=_read_float(card / "gt_boost_freq_mhz"),
        )
    return IgpuInfo(present=False)


def _fan_mode(pwm_enable: int | None) -> tuple[str, str, str]:
    if pwm_enable == 2:
        return (
            "auto",
            "BIOS auto",
            "This HP firmware exposes only auto vs max — not a percent curve like Omen Hub on Windows.",
        )
    if pwm_enable == 0:
        return (
            "max",
            "Maximum / override",
            "pwm1_enable=0 asks the HP embedded controller for maximum fan override. Loud, and it will drain more power.",
        )
    if pwm_enable == 1:
        return "manual", "Manual", "Manual PWM is advertised but this machine does not export a pwm1 duty file."
    return "unknown", "Unknown", "Fan mode could not be read from hp-wmi."


def _fan_hwmon() -> Path | None:
    global _FAN_HW, _FAN_TS, _FAN_INPUTS
    now = time.time()
    if _FAN_HW is not False and (now - _FAN_TS) < _INDEX_TTL:
        return _FAN_HW if isinstance(_FAN_HW, Path) else None
    hw = find_hwmon("hp")
    if not hw:
        root = Path("/sys/class/hwmon")
        if root.exists():
            for entry in root.glob("hwmon*"):
                if any(entry.glob("fan*_input")):
                    hw = entry
                    break
    _FAN_HW = hw
    _FAN_INPUTS = sorted(hw.glob("fan*_input")) if hw else []
    _FAN_TS = now
    return hw
    now = time.time()
    if _FAN_HW is not False and (now - _FAN_TS) < _INDEX_TTL:
        return _FAN_HW if isinstance(_FAN_HW, Path) else None
    hw = find_hwmon("hp")
    if not hw:
        root = Path("/sys/class/hwmon")
        if root.exists():
            for entry in root.glob("hwmon*"):
                if any(entry.glob("fan*_input")):
                    hw = entry
                    break
    _FAN_HW = hw
    _FAN_INPUTS = sorted(hw.glob("fan*_input")) if hw else []
    _FAN_TS = now
    return hw


def _collect_fans() -> FanInfo:
    hw = _fan_hwmon()
    if not hw:
        return FanInfo(False, None, [], None, "none", "No fan sensors", "No hwmon fan inputs found.")
    rpm = []
    for p in _FAN_INPUTS:
        value = _read_int(p)
        if value is not None:
            rpm.append(value)
    enable = _read_int(hw / "pwm1_enable")
    mode, label, note = _fan_mode(enable)
    return FanInfo(True, _read_text(hw / "name") or "hp", rpm, enable, mode, label, note)


def _thermal_layout() -> list[tuple[str, str, Path, float | None, float | None]]:
    global _THERMAL_LAYOUT, _THERMAL_TS
    now = time.time()
    if _THERMAL_LAYOUT is not None and (now - _THERMAL_TS) < _INDEX_TTL:
        return _THERMAL_LAYOUT
    layout: list[tuple[str, str, Path, float | None, float | None]] = []
    hwmon_root = Path("/sys/class/hwmon")
    if hwmon_root.exists():
        for hw in sorted(hwmon_root.glob("hwmon*")):
            chip = _read_text(hw / "name") or hw.name
            if chip in {"hp", "ADP1", "ucsi_source_psy_USBC000:001"}:
                continue
            for inp in sorted(hw.glob("temp*_input")):
                stem = inp.name.replace("_input", "")
                label = _read_text(hw / f"{stem}_label") or stem
                high = millideg_c(_read_int(hw / f"{stem}_max"))
                crit = millideg_c(_read_int(hw / f"{stem}_crit"))
                layout.append((chip, label, inp, high, crit))
    _THERMAL_LAYOUT = layout
    _THERMAL_TS = now
    return layout


_SLOW_THERMAL = {"nvme", "acpitz"}
_SLOW_THERMAL_POINTS: list[ThermalPoint] = []
_SLOW_THERMAL_TS = 0.0


def _collect_thermals() -> list[ThermalPoint]:
    global _SLOW_THERMAL_POINTS, _SLOW_THERMAL_TS
    now = time.time()
    refresh_slow = (now - _SLOW_THERMAL_TS) >= 2.0
    cached = {(p.source, p.label): p for p in _SLOW_THERMAL_POINTS}
    points: list[ThermalPoint] = []
    slow: list[ThermalPoint] = []
    for chip, label, inp, high, crit in _thermal_layout():
        if chip in _SLOW_THERMAL and not refresh_slow:
            prev = cached.get((chip, label))
            if prev is not None:
                points.append(prev)
            continue
        temp = millideg_c(_read_int(inp))
        if temp is None:
            continue
        point = ThermalPoint(chip, label, temp, high, crit)
        points.append(point)
        if chip in _SLOW_THERMAL:
            slow.append(point)
    if refresh_slow:
        _SLOW_THERMAL_POINTS = slow
        _SLOW_THERMAL_TS = now
    return points


_BAT_PATH: Path | None = None
_AC_PATH: Path | None | bool = False
_BAT_STATIC: tuple[float | None, float | None, float | None, int | None] | None = None
_BAT_STATUS: str | None = None
_BAT_STATUS_TS = 0.0


def _collect_battery() -> BatteryInfo:
    global _BAT_PATH, _AC_PATH, _BAT_STATIC, _BAT_STATUS, _BAT_STATUS_TS
    if _BAT_PATH is None:
        bat = Path("/sys/class/power_supply/BAT0")
        if not bat.exists():
            supplies = list(Path("/sys/class/power_supply").glob("BAT*")) if Path("/sys/class/power_supply").exists() else []
            bat = supplies[0] if supplies else bat
        _BAT_PATH = bat
    bat = _BAT_PATH
    present = bat.exists()
    if _AC_PATH is False:
        ac_path: Path | None = None
        for name in ("ADP1", "AC", "ACAD", "AC0"):
            candidate = Path("/sys/class/power_supply") / name / "online"
            if _read_int(candidate) is not None:
                ac_path = candidate
                break
        _AC_PATH = ac_path
    ac = None
    if isinstance(_AC_PATH, Path):
        online = _read_int(_AC_PATH)
        ac = None if online is None else bool(online)
    if not present:
        return BatteryInfo(present=False, ac_online=ac)

    def uw_to_w(path: str) -> float | None:
        raw = _read_int(bat / path)
        if raw is None:
            return None
        return raw / 1_000_000.0

    if _BAT_STATIC is None:
        full = uw_to_w("energy_full")
        design = uw_to_w("energy_full_design")
        health = 100.0 * full / design if full and design and design > 0 else None
        _BAT_STATIC = (full, design, health, _read_int(bat / "cycle_count"))
    full, design, health, cycles = _BAT_STATIC
    now = time.time()
    if (now - _BAT_STATUS_TS) >= 2.0 or _BAT_STATUS is None:
        _BAT_STATUS = _read_text(bat / "status")
        _BAT_STATUS_TS = now
    volts = _read_int(bat / "voltage_now")
    return BatteryInfo(
        present=True,
        status=_BAT_STATUS,
        percent=_read_int(bat / "capacity"),
        power_w=uw_to_w("power_now"),
        voltage_v=(volts / 1_000_000.0) if volts else None,
        energy_now_wh=uw_to_w("energy_now"),
        energy_full_wh=full,
        energy_design_wh=design,
        health_pct=health,
        cycle_count=cycles,
        ac_online=ac,
    )


def _collect_power() -> PowerInfo:
    rapl = Path("/sys/class/powercap/intel-rapl:0")
    limits: list[RaplLimit] = []
    energy_ok = False
    if (rapl / "energy_uj").exists():
        energy_ok = os.access(rapl / "energy_uj", os.R_OK)
    if rapl.exists():
        for idx in range(0, 4):
            name = _read_text(rapl / f"constraint_{idx}_name")
            if not name:
                continue
            limit_uw = _read_int(rapl / f"constraint_{idx}_power_limit_uw")
            max_uw = _read_int(rapl / f"constraint_{idx}_max_power_uw")
            window = _read_int(rapl / f"constraint_{idx}_time_window_us")
            limits.append(
                RaplLimit(
                    name=name,
                    power_limit_w=(limit_uw / 1_000_000.0) if limit_uw is not None else None,
                    max_power_w=(max_uw / 1_000_000.0) if max_uw not in (None, 0) else None,
                    window_s=(window / 1_000_000.0) if window else None,
                    writable=os.access(rapl / f"constraint_{idx}_power_limit_uw", os.W_OK),
                )
            )
    return PowerInfo(rapl_limits=limits, package_power_w=None, rapl_energy_readable=energy_ok)


def _collect_profile() -> ProfileInfo:
    path = Path("/sys/firmware/acpi/platform_profile")
    choices_raw = _read_text(Path("/sys/firmware/acpi/platform_profile_choices")) or ""
    return ProfileInfo(
        current=_read_text(path),
        choices=choices_raw.split() if choices_raw else [],
        writable=path.exists() and os.access(path, os.W_OK),
    )


def _collect_backlight() -> BacklightInfo:
    root = Path("/sys/class/backlight")
    if not root.exists():
        return BacklightInfo(present=False)
    entries = sorted(root.iterdir())
    if not entries:
        return BacklightInfo(present=False)
    # Prefer the panel backlight.
    chosen = None
    for e in entries:
        if "intel" in e.name or "amd" in e.name or "nvidia" in e.name:
            chosen = e
            break
    chosen = chosen or entries[0]
    cur = _read_int(chosen / "brightness")
    mx = _read_int(chosen / "max_brightness")
    pct = (100.0 * cur / mx) if cur is not None and mx else None
    return BacklightInfo(True, chosen.name, pct, cur, mx)


def _collect_memory() -> MemoryInfo:
    info: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            try:
                info[key] = int(raw.strip().split()[0]) * 1024
            except (ValueError, IndexError):
                continue
    except OSError:
        return MemoryInfo()
    total = info.get("MemTotal")
    available = info.get("MemAvailable")
    used = (total - available) if total is not None and available is not None else None
    swap_total = info.get("SwapTotal")
    swap_free = info.get("SwapFree")
    swap_used = (swap_total - swap_free) if swap_total is not None and swap_free is not None else None
    return MemoryInfo(
        total_b=total,
        used_b=used,
        available_b=available,
        swap_total_b=swap_total,
        swap_used_b=swap_used,
    )


def _collect_throttle(prev: ThrottleInfo | None) -> ThrottleInfo:
    base = Path("/sys/devices/system/cpu/cpu0/thermal_throttle")
    if not base.exists():
        return ThrottleInfo(available=False, note="Kernel did not export cpu0 thermal_throttle.")
    core = _read_int(base / "core_throttle_count")
    pkg = _read_int(base / "package_throttle_count")
    rising = False
    if prev and prev.available:
        if core is not None and prev.core_count is not None and core > prev.core_count:
            rising = True
        if pkg is not None and prev.package_count is not None and pkg > prev.package_count:
            rising = True
    return ThrottleInfo(
        available=True,
        core_count=core,
        package_count=pkg,
        core_total_ms=_read_int(base / "core_throttle_total_time_ms"),
        package_total_ms=_read_int(base / "package_throttle_total_time_ms"),
        rising=rising,
        note="Counts are cumulative since boot on cpu0; a rising count means throttling happened in this interval.",
    )


class Sampler:
    def __init__(self) -> None:
        self._cpu_total: tuple[int, int] | None = None
        self._cpu_cores: list[tuple[int, int]] | None = None
        self._host: HostInfo | None = None
        self._gpu: GpuInfo | None = None
        self._gpu_ts: float = 0.0
        self._throttle: ThrottleInfo | None = None

    def snapshot(self, include_gpu: bool = True) -> Snapshot:
        now = time.time()
        if self._host is None:
            self._host = _collect_host()
        cpu, times, cores = _collect_cpu(self._cpu_total, self._cpu_cores)
        self._cpu_total, self._cpu_cores = times, cores
        notes = []
        fans = _collect_fans()
        sources: dict[str, SourceStatus] = {}
        if include_gpu or self._gpu is None:
            gpu = _collect_nvidia()
            self._gpu = gpu
            self._gpu_ts = now
        else:
            gpu = self._gpu
        gpu_stale = (now - self._gpu_ts) > 5.0
        if gpu.present and gpu.error:
            notes.append(f"NVIDIA: {gpu.error}")
            sources["gpu"] = SourceStatus("gpu", False, self._gpu_ts, gpu.error, stale=True)
        elif gpu.present:
            sources["gpu"] = SourceStatus("gpu", True, self._gpu_ts, gpu.name, stale=gpu_stale)
        else:
            sources["gpu"] = SourceStatus("gpu", False, now, gpu.error or "nvidia-smi not found", stale=False)

        power = _collect_power()
        if not power.rapl_energy_readable:
            notes.append(
                "CPU package power is unavailable: intel-rapl energy_uj is root-only on this kernel."
            )
            sources["cpu_power"] = SourceStatus(
                "cpu_power", False, now, "energy_uj is root-only", stale=False
            )
        else:
            sources["cpu_power"] = SourceStatus("cpu_power", True, now, None, stale=False)

        memory = _collect_memory()
        throttle = _collect_throttle(self._throttle)
        self._throttle = throttle
        sources["cpu"] = SourceStatus("cpu", True, now, None, stale=False)
        sources["fans"] = SourceStatus("fans", fans.present, now, None if fans.present else fans.note, stale=False)
        sources["battery"] = SourceStatus("battery", True, now, None, stale=False)

        return Snapshot(
            ts=now,
            host=self._host,
            cpu=cpu,
            gpu=gpu,
            igpu=_collect_igpu(),
            fans=fans,
            thermals=_collect_thermals(),
            battery=_collect_battery(),
            power=power,
            profile=_collect_profile(),
            backlight=_collect_backlight(),
            memory=memory,
            throttle=throttle,
            notes=notes,
            sources=sources,
        )


def dump_snapshot() -> str:
    sampler = Sampler()
    sampler.snapshot()
    time.sleep(0.3)
    return json.dumps(sampler.snapshot().to_dict(), indent=2)
