from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from machina.paths import jobs_dir
from machina.processes import Process
from machina.projects import Project, Task


DESKTOP_SKIP = {
    "kwin_wayland",
    "plasmashell",
    "firefox",
    "cursor",
    "konsole",
    "dolphin",
    "Xorg",
    "systemd",
    "pipewire",
    "wireplumber",
    "dbus-broker",
    "baloo_file",
}


@dataclass
class Job:
    id: str
    pid: int | None
    name: str
    project: str | None
    command: str
    cwd: str | None
    log_path: str | None
    started_at: float
    ended_at: float | None
    status: str  # running | pausing | paused | exiting | exited | failed | detected
    returncode: int | None
    cpu: float | None = None
    rss_b: int | None = None
    gpu_vram_mib: float | None = None
    gpu_sm: float | None = None
    own: bool = False
    argv: list[str] = field(default_factory=list)


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._procs: dict[str, subprocess.Popen] = {}

    def launch(self, task: Task, python: str | None = None, extra_env: dict[str, str] | None = None) -> Job:
        argv = list(task.argv)
        if python and argv and argv[0] in {"python", "python3"}:
            argv[0] = python
        env = os.environ.copy()
        env.update(task.env)
        if extra_env:
            env.update(extra_env)
        if python:
            env["PATH"] = str(Path(python).parent) + ":" + env.get("PATH", "")
        log_path = jobs_dir() / f"{int(time.time())}-{task.id.replace('/', '_')[:80]}.log"
        handle = log_path.open("w", encoding="utf-8")
        handle.write(f"$ {' '.join(argv)}\ncwd={task.cwd}\n\n")
        handle.flush()
        try:
            proc = subprocess.Popen(
                argv,
                cwd=task.cwd,
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            handle.write(f"\nfailed to start: {exc}\n")
            handle.close()
            job = Job(
                id=str(uuid.uuid4())[:8],
                pid=None,
                name=task.title,
                project=Path(task.cwd).name,
                command=" ".join(argv),
                cwd=task.cwd,
                log_path=str(log_path),
                started_at=time.time(),
                ended_at=time.time(),
                status="failed",
                returncode=None,
                own=True,
                argv=argv,
            )
            with self._lock:
                self._jobs[job.id] = job
            return job
        job = Job(
            id=str(uuid.uuid4())[:8],
            pid=proc.pid,
            name=task.title,
            project=Path(task.cwd).name,
            command=" ".join(argv),
            cwd=task.cwd,
            log_path=str(log_path),
            started_at=time.time(),
            ended_at=None,
            status="running",
            returncode=None,
            own=True,
            argv=argv,
        )
        with self._lock:
            self._jobs[job.id] = job
            self._procs[job.id] = proc
        return job

    def spawn_logged(self, name: str, argv: list[str], log_path: Path, extra_env: dict[str, str] | None = None) -> Job:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("a", encoding="utf-8")
        handle.write(f"\n$ {' '.join(argv)}\n")
        handle.flush()
        proc = subprocess.Popen(
            argv,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        job = Job(
            id=str(uuid.uuid4())[:8],
            pid=proc.pid,
            name=name,
            project=None,
            command=" ".join(argv),
            cwd=str(Path.cwd()),
            log_path=str(log_path),
            started_at=time.time(),
            ended_at=None,
            status="running",
            returncode=None,
            own=True,
            argv=argv,
        )
        with self._lock:
            self._jobs[job.id] = job
            self._procs[job.id] = proc
        return job

    def poll(self, processes: list[Process], projects: list[Project]) -> list[Job]:
        now = time.time()
        by_pid = {p.pid: p for p in processes}
        with self._lock:
            for job_id, proc in list(self._procs.items()):
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                rc = proc.poll()
                if rc is None:
                    procinfo = by_pid.get(proc.pid)
                    if procinfo:
                        job.cpu = procinfo.cpu
                        job.rss_b = procinfo.rss_b
                        job.gpu_vram_mib = procinfo.gpu_vram_mib
                        job.gpu_sm = procinfo.gpu_sm
                    if job.status == "pausing":
                        job.status = "paused"
                else:
                    job.returncode = rc
                    job.ended_at = now
                    job.status = "exited" if rc == 0 else "failed"
                    self._procs.pop(job_id, None)
            launched_pids = {job.pid for job in self._jobs.values() if job.pid}
            detected: list[Job] = []
            project_names = {p.name for p in projects}
            for proc in processes:
                if proc.pid in launched_pids:
                    continue
                if proc.name in DESKTOP_SKIP:
                    continue
                if not _looks_like_job(proc, project_names):
                    continue
                key = f"det-{proc.pid}"
                existing = self._jobs.get(key)
                if existing and existing.status in {"running", "detected", "paused"}:
                    existing.cpu = proc.cpu
                    existing.rss_b = proc.rss_b
                    existing.gpu_vram_mib = proc.gpu_vram_mib
                    existing.command = proc.cmdline
                    continue
                detected.append(
                    Job(
                        id=key,
                        pid=proc.pid,
                        name=proc.name,
                        project=proc.project,
                        command=proc.cmdline,
                        cwd=proc.cwd,
                        log_path=_guess_log(proc),
                        started_at=now - (proc.elapsed_s or 0),
                        ended_at=None,
                        status="detected",
                        returncode=None,
                        cpu=proc.cpu,
                        rss_b=proc.rss_b,
                        gpu_vram_mib=proc.gpu_vram_mib,
                        own=proc.own,
                        argv=[],
                    )
                )
            for job in detected:
                self._jobs[job.id] = job
            live_det = {f"det-{p.pid}" for p in processes}
            for key, job in list(self._jobs.items()):
                if key.startswith("det-") and key not in live_det and job.status == "detected":
                    job.status = "exited"
                    job.ended_at = now
            return [self._jobs[k] for k in self._jobs]

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def signal(self, job_id: str, sig: int) -> str:
        with self._lock:
            job = self._jobs.get(job_id)
            proc = self._procs.get(job_id)
        if job is None or job.pid is None:
            return "Job has no process."
        try:
            if proc is not None:
                try:
                    os.killpg(job.pid, sig)
                except OSError:
                    os.kill(job.pid, sig)
            else:
                os.kill(job.pid, sig)
        except ProcessLookupError:
            return "Process already gone."
        except PermissionError:
            raise
        except OSError as exc:
            return str(exc)
        if sig == signal.SIGSTOP:
            job.status = "paused"
        elif sig == signal.SIGCONT:
            job.status = "running"
        elif sig in {signal.SIGTERM, signal.SIGKILL}:
            job.status = "exiting"
        return "ok"


def _looks_like_job(proc: Process, project_names: set[str]) -> bool:
    if proc.project and proc.project in project_names:
        heavy = (proc.cpu or 0) >= 8 or proc.rss_b >= 150 * 1024 * 1024 or proc.gpu_vram_mib
        long = (proc.elapsed_s or 0) >= 15
        if heavy or long:
            return True
    cmd = proc.cmdline.lower()
    hints = (
        "main.py",
        "collision/run.py",
        "transport/run.py",
        "physics_benchmark",
        "sgl_",
        "parameter_sweep",
        "pytest",
        "geant4",
        "ollama serve",
        "llama serve",
        "train.py",
        "evaluation/eval.py",
    )
    return any(h in cmd for h in hints)


def _guess_log(proc: Process) -> str | None:
    if not proc.cwd:
        return None
    cwd = Path(proc.cwd)
    for rel in ("outputs", "output", "data", "logs"):
        candidate = cwd / rel
        if candidate.is_dir():
            return str(candidate)
    return None


_MANAGER: JobManager | None = None
_MANAGER_LOCK = threading.Lock()


def job_manager() -> JobManager:
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = JobManager()
        return _MANAGER
