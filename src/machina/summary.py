from __future__ import annotations

from dataclasses import dataclass

from machina.jobs import Job
from machina.models import ModelHub
from machina.processes import Process
from machina.telemetry import Snapshot
from machina.util import fmt_bytes


@dataclass
class StatusSummary:
    status: str
    level: str  # ok | warn | critical | unknown
    lines: list[str]
    weak: bool = False


def interpret(
    snap: Snapshot,
    processes: list[Process],
    models: ModelHub,
    jobs: list[Job],
) -> StatusSummary:
    lines: list[str] = []
    weak = False
    level = "ok"
    status = "HEALTHY"

    gpu = snap.gpu
    cpu_t = snap.cpu.package_temp_c
    gpu_t = gpu.temp_c if gpu.present and not gpu.error else None
    gpu_stale = bool(gpu.present and (gpu.error or (snap.sources.get("gpu") and snap.sources["gpu"].stale)))

    if gpu_stale or cpu_t is None:
        weak = True

    hot = [t for t in (cpu_t, gpu_t) if t is not None]
    hottest = max(hot) if hot else None
    throttling = bool(gpu.thermal_slowdown or gpu.hw_thermal_slowdown or snap.throttle.rising)

    if hottest is not None and hottest >= 97:
        status, level = "THERMALLY CRITICAL", "critical"
        lines.append(f"Hottest sensor {hottest:.0f} °C.")
    elif throttling or (hottest is not None and hottest >= 90):
        status, level = "THERMALLY CONSTRAINED", "warn"
        if hottest is not None:
            lines.append(f"Hottest sensor {hottest:.0f} °C.")
    elif hottest is not None and hottest >= 80:
        status, level = "WARM", "warn"
        lines.append(f"Hottest sensor {hottest:.0f} °C.")
    elif hottest is None:
        status, level = "UNKNOWN", "unknown"
        lines.append("Not enough fresh thermal data to claim a health state.")
        weak = True

    if status != "UNKNOWN":
        if cpu_t is not None and snap.cpu.usage is None:
            lines.append(f"CPU at {cpu_t:.0f} °C.")
            weak = True
        elif cpu_t is not None and snap.cpu.usage is not None and snap.cpu.usage < 25:
            lines.append(f"CPU lightly loaded ({snap.cpu.usage:.0f}%) at {cpu_t:.0f} °C.")
        elif cpu_t is not None and snap.cpu.usage is not None:
            lines.append(f"CPU {snap.cpu.usage:.0f}% at {cpu_t:.0f} °C.")
        elif cpu_t is None:
            lines.append("CPU temperature unavailable.")
            weak = True

    if gpu.present and not gpu.error:
        vram = ""
        if gpu.mem_used_mib is not None:
            vram = f"{gpu.mem_used_mib / 1024:.1f} GB VRAM in use." if gpu.mem_used_mib >= 1024 else f"{gpu.mem_used_mib:.0f} MiB VRAM in use."
        loaded = list(models.loaded)
        gpu_procs = [p for p in processes if p.gpu_vram_mib]
        if loaded:
            parts = []
            for model in loaded:
                kind = model.source or "model"
                if kind == "llama.cpp":
                    kind = "llama.cpp"
                elif kind == "freetoken":
                    kind = "FreeToken"
                elif kind in {"ollama", "disk"}:
                    kind = "Ollama"
                parts.append(f"{kind} ({model.name})")
            lines.append("GPU currently running " + "; ".join(parts) + ".")
            if vram:
                lines.append(vram)
        elif gpu.util is not None and gpu.util >= 15:
            who = gpu_procs[0].name if gpu_procs else "an unknown process"
            lines.append(f"GPU busy ({gpu.util:.0f}% · {who}).")
            if vram:
                lines.append(vram)
        elif gpu.util is not None:
            lines.append("GPU idle." if gpu.util < 8 else f"GPU {gpu.util:.0f}%.")
            if vram and gpu.mem_used_mib and gpu.mem_used_mib >= 200:
                lines.append(vram)
    elif gpu.present and gpu.error:
        lines.append(f"GPU telemetry unavailable: {gpu.error}")
        weak = True

    if throttling:
        bits = []
        if gpu.thermal_slowdown:
            bits.append("NVIDIA software thermal slowdown")
        if gpu.hw_thermal_slowdown:
            bits.append("NVIDIA hardware thermal slowdown")
        if snap.throttle.rising:
            bits.append("Intel thermal throttle count rising")
        lines.append("Thermal throttling detected: " + ", ".join(bits) + ".")
    if gpu.present and not gpu.error and snap.throttle.available and not throttling:
        lines.append("No thermal throttling detected in this interval.")
    elif not snap.throttle.available and not (gpu.present and not gpu.error):
        lines.append("Throttle counters are not fully available; not claiming a clean thermal path.")
        weak = True

    if snap.profile.current:
        lines.append(f"Performance profile: {snap.profile.current.title()}.")
    if snap.fans.present:
        extra = f" · {max(snap.fans.rpm):,} rpm" if snap.fans.rpm else ""
        lines.append(f"Fan control: {snap.fans.mode_label}{extra}.")

    active_jobs = [j for j in jobs if j.status in {"running", "detected", "paused"}]
    for job in active_jobs[:4]:
        where = f" on {job.project}" if job.project else ""
        gpu_bit = " (GPU)" if job.gpu_vram_mib else ""
        lines.append(f"{job.name}{where} is {job.status}{gpu_bit}.")

    if snap.battery.present and snap.battery.ac_online is False:
        lines.append(f"On battery ({snap.battery.percent}%).")
        if status == "HEALTHY" and (snap.cpu.usage or 0) < 30:
            pass
        elif status == "HEALTHY":
            status = "ON BATTERY"

    mem = snap.memory
    if mem.used_b and mem.total_b:
        pct = 100.0 * mem.used_b / mem.total_b
        if pct >= 90:
            lines.append(f"RAM {pct:.0f}% used ({fmt_bytes(mem.used_b)}).")
            if level == "ok":
                level = "warn"
                if status == "HEALTHY":
                    status = "MEMORY PRESSURE"
        elif mem.swap_used_b and mem.swap_used_b > 256 * 1024 * 1024:
            lines.append(f"Swap in use: {fmt_bytes(mem.swap_used_b)}.")

    if weak and status == "HEALTHY":
        status = "HEALTHY (partial data)"

    # Deduplicate adjacent similar lines
    deduped: list[str] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return StatusSummary(status=status, level=level, lines=deduped[:12], weak=weak)
