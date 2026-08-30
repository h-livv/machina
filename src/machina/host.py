from __future__ import annotations

import time
from collections import deque
from pathlib import Path

from machina.events import EventLog
from machina.jobs import job_manager
from machina.models import collect_models, refresh_generation_rate
from machina.network import NetworkSampler
from machina.processes import ProcessSampler, collect_gpu_procs
from machina.projects import discover_projects
from machina.services import collect_services
from machina.state import HostState, TimelineItem
from machina.storage import StorageAnalyzer
from machina.summary import interpret
from machina.telemetry import Sampler, SourceStatus, Snapshot


def _project_roots(projects: list) -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = []
    for project in projects:
        try:
            roots.append((project.name, Path(project.path).resolve()))
        except OSError:
            roots.append((project.name, Path(project.path)))
    return roots


class Engine:
    def __init__(self) -> None:
        self.sampler = Sampler()
        self.procs = ProcessSampler()
        self.network = NetworkSampler()
        self.storage = StorageAnalyzer()
        self.events = EventLog()
        self._projects = discover_projects()
        self._projects_ts = 0.0
        self._roots = _project_roots(self._projects)
        self._gpu_procs: list = []
        self._processes: list = []
        self._models = collect_models()
        self._services: list = []
        self._last = {"gpu": 0.0, "proc": 0.0, "models": 0.0, "svc": 0.0, "proj": 0.0}
        self._prev: HostState | None = None
        self._timeline: deque[TimelineItem] = deque(maxlen=80)
        self._last_gpu_util: float | None = None
        self._last_vram: float | None = None
        self._last_temp: float | None = None
        self._last_fan: int | None = None

    def tick(self) -> HostState:
        now = time.time()
        include_gpu = (now - self._last["gpu"]) >= 2.0 or self.sampler._gpu is None
        snap = self.sampler.snapshot(include_gpu=include_gpu)
        if include_gpu:
            self._last["gpu"] = now
            gpu_procs, gpu_err = collect_gpu_procs()
            self._gpu_procs = gpu_procs
            if gpu_err and snap.sources.get("gpu") and snap.sources["gpu"].ok:
                snap.sources["gpu_procs"] = SourceStatus("gpu_procs", False, now, gpu_err, stale=False)
            else:
                snap.sources["gpu_procs"] = SourceStatus("gpu_procs", True, now, None, stale=False)

        if now - self._last["proj"] >= 90.0 or not self._projects:
            self._projects = discover_projects()
            self._last["proj"] = now
            self._roots = _project_roots(self._projects)

        if now - self._last["proc"] >= 2.0:
            self._processes = self.procs.sample(self._roots, self._gpu_procs)
            self._last["proc"] = now
            snap.sources["processes"] = SourceStatus("processes", True, now, None, stale=False)

        if now - self._last["models"] >= 4.0:
            self._models = collect_models()
            self._last["models"] = now
        else:
            refresh_generation_rate(self._models)

        if now - self._last["svc"] >= 8.0:
            self._services = collect_services()
            self._last["svc"] = now

        downloads = [
            p.name
            for p in self._processes
            if p.name in {"curl", "wget", "aria2c", "huggingface-cli", "hf"}
            or "ollama pull" in p.cmdline
            or "llama download" in p.cmdline
        ]
        net = self.network.sample(downloads)
        storage = self.storage.snapshot()
        self.storage.maybe_schedule(180.0)

        jobs = job_manager().poll(self._processes, self._projects)
        summary = interpret(snap, self._processes, self._models, jobs)
        state = HostState(
            snap=snap,
            processes=self._processes,
            gpu_procs=self._gpu_procs,
            models=self._models,
            services=self._services,
            jobs=jobs,
            projects=self._projects,
            storage=storage,
            network=net,
            summary=summary,
            events=self.events.recent(40),
            sources=snap.sources,
        )
        self.events.observe(self._prev, state)
        state.events = self.events.recent(40)
        self._push_timeline(snap, state)
        state.timeline = list(self._timeline)
        self._prev = state
        return state

    def _push_timeline(self, snap: Snapshot, state: HostState) -> None:
        now = snap.ts
        gpu = snap.gpu
        util = gpu.util if gpu.present and not gpu.error else None
        vram = gpu.mem_used_mib if gpu.present and not gpu.error else None
        temp = snap.cpu.package_temp_c
        fan = max(snap.fans.rpm) if snap.fans.rpm else None

        def add(kind: str, title: str, detail: str) -> None:
            if self._timeline and self._timeline[-1].title == title:
                return
            self._timeline.append(TimelineItem(ts=now, title=title, detail=detail, kind=kind))

        if self._prev is None:
            add("boot", "Machina started sampling", snap.host.product)
            return

        for job in state.jobs:
            prev_ids = {j.id: j.status for j in self._prev.jobs}
            if job.id not in prev_ids and job.status in {"running", "detected"}:
                add("job", f"{job.name} started", job.command[:160])
            was = prev_ids.get(job.id)
            if was in {"running", "detected"} and job.status in {"exited", "failed"}:
                add("job", f"{job.name} {job.status}", job.command[:160])

        if util is not None and self._last_gpu_util is not None:
            if self._last_gpu_util < 12 <= util:
                add("gpu", "GPU usage increased", f"{self._last_gpu_util:.0f}% → {util:.0f}%")
            elif self._last_gpu_util >= 12 > util:
                add("gpu", "GPU usage dropped", f"{self._last_gpu_util:.0f}% → {util:.0f}%")
        if vram is not None and self._last_vram is not None and abs(vram - self._last_vram) >= 400:
            add("gpu", "VRAM changed", f"{self._last_vram:.0f} → {vram:.0f} MiB")
        if temp is not None and self._last_temp is not None and temp - self._last_temp >= 6:
            add("thermals", "Temperature increased", f"{self._last_temp:.0f} → {temp:.0f} °C")
        if fan is not None and self._last_fan is not None and fan - self._last_fan >= 800:
            add("cooling", "Cooling increased", f"{self._last_fan:,} → {fan:,} rpm")

        self._last_gpu_util = util
        self._last_vram = vram
        self._last_temp = temp
        self._last_fan = fan
