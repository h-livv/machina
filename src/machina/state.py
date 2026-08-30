from __future__ import annotations

from dataclasses import dataclass, field

from machina.events import Event
from machina.jobs import Job
from machina.models import ModelHub
from machina.network import NetworkInfo
from machina.processes import GpuProc, Process
from machina.projects import Project
from machina.services import Service
from machina.storage import StorageInfo
from machina.summary import StatusSummary
from machina.telemetry import Snapshot, SourceStatus


@dataclass
class TimelineItem:
    ts: float
    title: str
    detail: str
    kind: str


@dataclass
class HostState:
    snap: Snapshot
    processes: list[Process] = field(default_factory=list)
    gpu_procs: list[GpuProc] = field(default_factory=list)
    models: ModelHub | None = None
    services: list[Service] = field(default_factory=list)
    jobs: list[Job] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    storage: StorageInfo | None = None
    network: NetworkInfo | None = None
    summary: StatusSummary | None = None
    events: list[Event] = field(default_factory=list)
    timeline: list[TimelineItem] = field(default_factory=list)
    sources: dict[str, SourceStatus] = field(default_factory=dict)
