"""In-process NVIDIA telemetry via libnvidia-ml. Same metrics as nvidia-smi, without forking."""

from __future__ import annotations

import ctypes
import time
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_char_p,
    c_uint,
    c_ulonglong,
    c_void_p,
    create_string_buffer,
)
from typing import Any


NVML_SUCCESS = 0
NVML_ERROR_INSUFFICIENT_SIZE = 7
NVML_TEMPERATURE_GPU = 0
NVML_CLOCK_GRAPHICS = 0
NVML_CLOCK_MEM = 2
NVML_VALUE_NOT_AVAILABLE = 0xFFFFFFFFFFFFFFFF
# Clocks throttle / event reason bits (stable across NVML header renames).
_SW_THERMAL = 0x0000000000000020
_HW_THERMAL = 0x0000000000000040

_lib = None
_dev = None
_ok: bool | None = None
_fail_ts = 0.0
_FAIL_RETRY_S = 30.0


class _Utilization(Structure):
    _fields_ = [("gpu", c_uint), ("memory", c_uint)]


class _Memory(Structure):
    _fields_ = [("total", c_ulonglong), ("free", c_ulonglong), ("used", c_ulonglong)]


class _ProcessV3(Structure):
    _fields_ = [
        ("pid", c_uint),
        ("usedGpuMemory", c_ulonglong),
        ("gpuInstanceId", c_uint),
        ("computeInstanceId", c_uint),
    ]


def _load() -> bool:
    global _lib, _dev, _ok, _fail_ts
    now = time.time()
    if _ok is False and (now - _fail_ts) < _FAIL_RETRY_S:
        return False
    if _ok is True and _lib is not None and _dev is not None:
        return True
    try:
        lib = ctypes.CDLL("libnvidia-ml.so.1")
    except OSError:
        _ok = False
        _fail_ts = now
        return False

    def _call(name: str, *alt: str):
        for candidate in (name, *alt):
            if hasattr(lib, candidate):
                return getattr(lib, candidate)
        return None

    init = _call("nvmlInit_v2", "nvmlInit")
    if init is None or init() != NVML_SUCCESS:
        _ok = False
        _fail_ts = now
        return False

    handle = c_void_p()
    by_index = _call("nvmlDeviceGetHandleByIndex_v2", "nvmlDeviceGetHandleByIndex")
    if by_index is None:
        _ok = False
        _fail_ts = now
        return False
    by_index.argtypes = [c_uint, POINTER(c_void_p)]
    if by_index(0, byref(handle)) != NVML_SUCCESS or not handle.value:
        _ok = False
        _fail_ts = now
        return False

    get_name = _call("nvmlDeviceGetName")
    get_temp = _call("nvmlDeviceGetTemperature")
    get_util = _call("nvmlDeviceGetUtilizationRates")
    get_power = _call("nvmlDeviceGetPowerUsage")
    get_enforced = _call("nvmlDeviceGetEnforcedPowerLimit")
    get_limits = _call("nvmlDeviceGetPowerManagementLimitConstraints")
    get_default = _call("nvmlDeviceGetPowerManagementDefaultLimit")
    get_mem = _call("nvmlDeviceGetMemoryInfo")
    get_pstate = _call("nvmlDeviceGetPerformanceState")
    get_clock = _call("nvmlDeviceGetClockInfo")
    get_throttle = _call("nvmlDeviceGetCurrentClocksThrottleReasons", "nvmlDeviceGetCurrentClocksEventReasons")
    get_driver = _call("nvmlSystemGetDriverVersion")
    get_procs = _call("nvmlDeviceGetComputeRunningProcesses_v3", "nvmlDeviceGetComputeRunningProcesses_v2")

    if get_name:
        get_name.argtypes = [c_void_p, c_char_p, c_uint]
    if get_temp:
        get_temp.argtypes = [c_void_p, c_uint, POINTER(c_uint)]
    if get_util:
        get_util.argtypes = [c_void_p, POINTER(_Utilization)]
    if get_power:
        get_power.argtypes = [c_void_p, POINTER(c_uint)]
    if get_enforced:
        get_enforced.argtypes = [c_void_p, POINTER(c_uint)]
    if get_limits:
        get_limits.argtypes = [c_void_p, POINTER(c_uint), POINTER(c_uint)]
    if get_default:
        get_default.argtypes = [c_void_p, POINTER(c_uint)]
    if get_mem:
        get_mem.argtypes = [c_void_p, POINTER(_Memory)]
    if get_pstate:
        get_pstate.argtypes = [c_void_p, POINTER(c_uint)]
    if get_clock:
        get_clock.argtypes = [c_void_p, c_uint, POINTER(c_uint)]
    if get_throttle:
        get_throttle.argtypes = [c_void_p, POINTER(c_ulonglong)]
    if get_driver:
        get_driver.argtypes = [c_char_p, c_uint]
    if get_procs:
        get_procs.argtypes = [c_void_p, POINTER(c_uint), POINTER(_ProcessV3)]

    lib._get_name = get_name
    lib._get_temp = get_temp
    lib._get_util = get_util
    lib._get_power = get_power
    lib._get_enforced = get_enforced
    lib._get_limits = get_limits
    lib._get_default = get_default
    lib._get_mem = get_mem
    lib._get_pstate = get_pstate
    lib._get_clock = get_clock
    lib._get_throttle = get_throttle
    lib._get_driver = get_driver
    lib._get_procs = get_procs

    _lib = lib
    _dev = handle
    _ok = True
    return True


def _mw_to_w(raw: int | None) -> float | None:
    if raw is None:
        return None
    return raw / 1000.0


def _u32(fn, *args) -> int | None:
    if fn is None:
        return None
    val = c_uint()
    if fn(*args, byref(val)) != NVML_SUCCESS:
        return None
    return val.value


def query_gpu() -> dict[str, Any] | None:
    if not _load():
        return None
    lib, dev = _lib, _dev
    assert lib is not None and dev is not None

    name = None
    if lib._get_name:
        buf = create_string_buffer(96)
        if lib._get_name(dev, buf, 96) == NVML_SUCCESS:
            name = buf.value.decode("utf-8", "replace") or None

    driver = None
    if lib._get_driver:
        buf = create_string_buffer(80)
        if lib._get_driver(buf, 80) == NVML_SUCCESS:
            driver = buf.value.decode("utf-8", "replace") or None

    temp = _u32(lib._get_temp, dev, NVML_TEMPERATURE_GPU)
    util = mem_util = None
    if lib._get_util:
        rates = _Utilization()
        if lib._get_util(dev, byref(rates)) == NVML_SUCCESS:
            util = float(rates.gpu)
            mem_util = float(rates.memory)

    power_w = _mw_to_w(_u32(lib._get_power, dev))
    power_limit_w = _mw_to_w(_u32(lib._get_enforced, dev))
    power_min_w = power_max_w = None
    if lib._get_limits:
        lo, hi = c_uint(), c_uint()
        if lib._get_limits(dev, byref(lo), byref(hi)) == NVML_SUCCESS:
            power_min_w = _mw_to_w(lo.value)
            power_max_w = _mw_to_w(hi.value)
    power_default_w = _mw_to_w(_u32(lib._get_default, dev))

    mem_used = mem_total = None
    if lib._get_mem:
        mem = _Memory()
        if lib._get_mem(dev, byref(mem)) == NVML_SUCCESS:
            mem_used = mem.used / (1024.0 * 1024.0)
            mem_total = mem.total / (1024.0 * 1024.0)

    pstate = None
    ps = _u32(lib._get_pstate, dev)
    if ps is not None:
        pstate = f"P{ps}"

    clock_gr = _u32(lib._get_clock, dev, NVML_CLOCK_GRAPHICS)
    clock_mem = _u32(lib._get_clock, dev, NVML_CLOCK_MEM)

    sw_slow = hw_slow = None
    if lib._get_throttle:
        reasons = c_ulonglong()
        if lib._get_throttle(dev, byref(reasons)) == NVML_SUCCESS:
            sw_slow = bool(reasons.value & _SW_THERMAL)
            hw_slow = bool(reasons.value & _HW_THERMAL)

    return {
        "name": name,
        "driver": driver,
        "temp_c": float(temp) if temp is not None else None,
        "util": util,
        "mem_util": mem_util,
        "power_w": power_w,
        "power_limit_w": power_limit_w,
        "power_min_w": power_min_w,
        "power_max_w": power_max_w,
        "power_default_w": power_default_w,
        "clock_graphics_mhz": float(clock_gr) if clock_gr is not None else None,
        "clock_memory_mhz": float(clock_mem) if clock_mem is not None else None,
        "mem_used_mib": mem_used,
        "mem_total_mib": mem_total,
        "pstate": pstate,
        "thermal_slowdown": sw_slow,
        "hw_thermal_slowdown": hw_slow,
    }


def compute_apps() -> list[tuple[int, str, float | None]] | None:
    if not _load():
        return None
    lib, dev = _lib, _dev
    assert lib is not None and dev is not None
    if lib._get_procs is None:
        return None
    count = 8
    while count <= 256:
        n = c_uint(count)
        arr = (_ProcessV3 * count)()
        rc = lib._get_procs(dev, byref(n), arr)
        if rc == NVML_ERROR_INSUFFICIENT_SIZE:
            count = max(count * 2, n.value + 4)
            continue
        if rc != NVML_SUCCESS:
            return None
        rows: list[tuple[int, str, float | None]] = []
        for i in range(n.value):
            pid = int(arr[i].pid)
            used = arr[i].usedGpuMemory
            vram = None if used == NVML_VALUE_NOT_AVAILABLE else used / (1024.0 * 1024.0)
            rows.append((pid, _comm(pid), vram))
        return rows
    return None


def _comm(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as handle:
            return handle.read().strip() or str(pid)
    except OSError:
        return str(pid)
