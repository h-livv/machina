from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from machina.paths import events_path


@dataclass
class Event:
    ts: float
    kind: str
    title: str
    detail: str
    level: str  # info | warn | critical
    key: str = ""


class EventLog:
    def __init__(self) -> None:
        self._items: list[Event] = []
        self._last_emit: dict[str, float] = {}
        self._load()

    def recent(self, limit: int = 80) -> list[Event]:
        return list(reversed(self._items[-limit:]))

    def emit(self, kind: str, title: str, detail: str, level: str = "info", key: str = "", cooldown_s: float = 45.0) -> Event | None:
        now = time.time()
        dedupe = key or f"{kind}:{title}"
        last = self._last_emit.get(dedupe, 0.0)
        if cooldown_s and now - last < cooldown_s:
            return None
        event = Event(ts=now, kind=kind, title=title, detail=detail, level=level, key=dedupe)
        self._last_emit[dedupe] = now
        self._items.append(event)
        self._items = self._items[-800:]
        _append(event)
        return event

    def observe(self, prev: Any, cur: Any) -> list[Event]:
        """Compare consecutive HostState-like objects. prev may be None."""
        emitted: list[Event] = []

        def add(*args: Any, **kwargs: Any) -> None:
            event = self.emit(*args, **kwargs)
            if event:
                emitted.append(event)

        snap = cur.snap
        if snap.gpu.present and snap.gpu.thermal_slowdown:
            add("thermal", "GPU software thermal slowdown", "NVIDIA clocks_event_reasons.sw_thermal_slowdown is active.", "warn", "gpu-sw-throttle", 60)
        if snap.gpu.present and snap.gpu.hw_thermal_slowdown:
            add("thermal", "GPU hardware thermal slowdown", "NVIDIA hw thermal slowdown is active.", "critical", "gpu-hw-throttle", 30)
        if snap.throttle.rising:
            add("thermal", "CPU thermal throttle count increased", snap.throttle.note, "warn", "cpu-throttle-rise", 60)
        if prev is not None:
            if prev.snap.fans.mode != snap.fans.mode:
                add("hardware", f"Fan mode → {snap.fans.mode_label}", f"{prev.snap.fans.mode} → {snap.fans.mode}", "info", f"fan-{snap.fans.mode}", 5)
            if (prev.snap.profile.current or "") != (snap.profile.current or ""):
                add("hardware", f"Profile → {snap.profile.current}", "ACPI platform profile changed.", "info", f"profile-{snap.profile.current}", 5)
            prev_loaded = {m.name for m in prev.models.loaded}
            cur_loaded = {m.name for m in cur.models.loaded}
            for name in cur_loaded - prev_loaded:
                add("model", f"Model loaded: {name}", "Ollama resident model changed.", "info", f"load-{name}", 5)
            for name in prev_loaded - cur_loaded:
                add("model", f"Model unloaded: {name}", "Ollama resident model changed.", "info", f"unload-{name}", 5)
            prev_jobs = {j.id: j.status for j in prev.jobs}
            for job in cur.jobs:
                was = prev_jobs.get(job.id)
                if was in {"running", "detected", "paused"} and job.status in {"exited", "failed"}:
                    level = "info" if job.status == "exited" else "warn"
                    add("job", f"{job.name} {job.status}", job.command, level, f"job-end-{job.id}", 2)
            prev_svc = {s.unit: s.active for s in prev.services}
            for svc in cur.services:
                if prev_svc.get(svc.unit) == "active" and svc.active != "active":
                    add("service", f"{svc.unit} stopped", f"state={svc.active}/{svc.sub}", "warn", f"svc-{svc.unit}", 15)
            if prev.models.ollama_running and not cur.models.ollama_running:
                add("service", "Ollama API went away", cur.models.ollama_error or "", "warn", "ollama-down", 20)
            if not prev.models.ollama_running and cur.models.ollama_running:
                add("service", "Ollama API is up", cur.models.ollama_version or "", "info", "ollama-up", 10)
            gpu_ok_prev = prev.snap.sources.get("gpu")
            gpu_ok_cur = snap.sources.get("gpu")
            if gpu_ok_prev and gpu_ok_prev.ok and gpu_ok_cur and not gpu_ok_cur.ok:
                add("telemetry", "NVIDIA telemetry unavailable", gpu_ok_cur.detail or "", "warn", "gpu-gone", 30)
        for mount in cur.storage.mounts:
            if mount.total_b > 0 and mount.used_b / mount.total_b >= 0.90:
                add(
                    "storage",
                    f"{mount.target} is {100 * mount.used_b / mount.total_b:.0f}% full",
                    f"{mount.used_b} of {mount.total_b} bytes",
                    "warn",
                    f"disk-{mount.target}",
                    600,
                )
        return emitted

    def _load(self) -> None:
        path = events_path()
        if not path.exists():
            return
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
        except OSError:
            return
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                self._items.append(Event(**{k: row[k] for k in ("ts", "kind", "title", "detail", "level") if k in row}, key=row.get("key", "")))
            except TypeError:
                continue


def _append(event: Event) -> None:
    try:
        with events_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event)) + "\n")
    except OSError:
        pass
