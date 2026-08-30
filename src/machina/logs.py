from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from machina.freetoken import log_path as freetoken_log_path
from machina.jobs import Job
from machina.models import llama_log_path, ollama_log_path
from machina.paths import audit_path, events_path, jobs_dir, logs_dir
from machina.util import run_cmd


@dataclass
class LogSource:
    id: str
    title: str
    kind: str  # file | journal | jobs
    path: str | None
    unit: str | None
    note: str = ""


@dataclass
class LogLine:
    ts: float | None
    source: str
    severity: str
    text: str


def list_sources(jobs: list[Job] | None = None) -> list[LogSource]:
    sources = [
        LogSource("machina-audit", "Machina audit", "file", str(audit_path()), None, "Hardware apply log"),
        LogSource("machina-events", "Machina events", "file", str(events_path()), None, "Control-plane events"),
        LogSource("ollama-file", "Ollama (Machina-spawned)", "file", str(ollama_log_path()), None, "Only if Machina started ollama serve"),
        LogSource("llama-file", "llama.cpp serve", "file", str(llama_log_path()), None, "Only if Machina started llama serve"),
        LogSource("freetoken-file", "FreeToken UI", "file", str(freetoken_log_path()), None, "Launch log if Machina started the AppImage"),
        LogSource("journal-ollama", "Ollama systemd", "journal", None, "ollama.service", "system journal"),
        LogSource("journal-nvidia", "nvidia-powerd", "journal", None, "nvidia-powerd.service"),
        LogSource("journal-docker", "Docker", "journal", None, "docker.service"),
    ]
    for job in jobs or []:
        if job.log_path:
            sources.append(LogSource(f"job-{job.id}", f"Job {job.name}", "file", job.log_path, None, job.project or ""))
    return sources


def read_source(source: LogSource, limit: int = 250, query: str = "", severity: str = "") -> list[LogLine]:
    if source.kind == "journal" and source.unit:
        return _journal(source, limit, query, severity)
    if source.path:
        return _file(source, limit, query, severity)
    return []


def _file(source: LogSource, limit: int, query: str, severity: str) -> list[LogLine]:
    path = Path(source.path) if source.path else None
    if path is None or not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    q = query.lower()
    out: list[LogLine] = []
    for line in lines[-max(limit * 3, limit) :]:
        sev = _severity(line)
        if severity and sev != severity and not (severity == "info" and sev == "debug"):
            if severity != sev:
                continue
        if q and q not in line.lower():
            continue
        out.append(LogLine(ts=None, source=source.id, severity=sev, text=line))
    return out[-limit:]


def _journal(source: LogSource, limit: int, query: str, severity: str) -> list[LogLine]:
    argv = ["journalctl", "-u", source.unit or "", "-n", str(limit), "--no-pager", "-o", "short-iso"]
    if severity == "error":
        argv += ["-p", "err"]
    elif severity == "warn":
        argv += ["-p", "warning"]
    code, out, err = run_cmd(argv, timeout=1.5)
    if code != 0:
        return [
            LogLine(
                ts=time.time(),
                source=source.id,
                severity="warn",
                text=(err or out or "journalctl unavailable").strip()[:400],
            )
        ]
    q = query.lower()
    rows: list[LogLine] = []
    for line in out.splitlines():
        if q and q not in line.lower():
            continue
        rows.append(LogLine(ts=None, source=source.id, severity=_severity(line), text=line))
    return rows[-limit:]


def _severity(line: str) -> str:
    low = line.lower()
    if any(tok in low for tok in (" error", "fail", "fatal", "critical", "traceback")):
        return "error"
    if any(tok in low for tok in (" warn", "warning", "thermal")):
        return "warn"
    return "info"
