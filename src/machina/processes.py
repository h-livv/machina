from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from machina.nvml import compute_apps as _nvml_apps
from machina.util import current_uid, username_for


CLK_TCK = os.sysconf("SC_CLK_TCK") or 100
PAGE = os.sysconf("SC_PAGE_SIZE") or 4096
_O_RDONLY = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
_BOOT: float | None = None


@dataclass
class GpuProc:
    pid: int
    name: str
    vram_mib: float | None
    sm: float | None = None


@dataclass
class Process:
    pid: int
    name: str
    user: str
    uid: int
    cpu: float | None
    rss_b: int
    cmdline: str
    cwd: str | None
    ppid: int
    elapsed_s: float | None
    parent_name: str | None
    project: str | None
    gpu_vram_mib: float | None = None
    gpu_sm: float | None = None
    own: bool = False


class ProcessSampler:
    def __init__(self) -> None:
        self._prev: dict[int, tuple[float, float]] = {}  # pid -> (proc_time, wall)
        self._names: dict[int, str] = {}

    def sample(self, project_roots: list[tuple[str, Path]], gpu_procs: list[GpuProc] | None = None) -> list[Process]:
        gpu_map = {g.pid: g for g in (gpu_procs or [])}
        roots = project_roots
        uid = current_uid()
        now = time.time()
        boot = _boot_time()
        rows: list[Process] = []
        seen: set[int] = set()
        try:
            entries = os.scandir("/proc")
        except OSError:
            return []

        with entries:
            for entry in entries:
                name = entry.name
                if not name.isdigit():
                    continue
                pid = int(name)
                parsed = _parse_pid(entry.path, pid, boot, now)
                if parsed is None:
                    continue
                comm, state, ppid, proc_time, start_s, rss_pages, cmdline, status_uid, status_name = parsed
                if state == "Z":
                    continue
                wall_prev = self._prev.get(pid)
                cpu = None
                if wall_prev is not None:
                    dt = now - wall_prev[1]
                    if dt > 0:
                        cpu = max(0.0, 100.0 * (proc_time - wall_prev[0]) / dt)
                self._prev[pid] = (proc_time, now)
                seen.add(pid)

                cwd = None
                interesting = (
                    pid in gpu_map
                    or (cpu is not None and cpu >= 1.0)
                    or (rss_pages * PAGE) >= 80 * 1024 * 1024
                )
                if interesting:
                    try:
                        cwd = os.readlink(f"{entry.path}/cwd")
                    except OSError:
                        cwd = None

                project = _match_project(cwd, cmdline, roots)
                gpu = gpu_map.get(pid)
                puid = status_uid if status_uid is not None else -1
                rows.append(
                    Process(
                        pid=pid,
                        name=status_name or comm,
                        user=username_for(puid) if puid >= 0 else "?",
                        uid=puid,
                        cpu=cpu,
                        rss_b=rss_pages * PAGE,
                        cmdline=cmdline or comm,
                        cwd=cwd,
                        ppid=ppid,
                        elapsed_s=(now - start_s) if start_s else None,
                        parent_name=self._names.get(ppid),
                        project=project,
                        gpu_vram_mib=gpu.vram_mib if gpu else None,
                        gpu_sm=gpu.sm if gpu else None,
                        own=puid == uid,
                    )
                )
                self._names[pid] = status_name or comm

        self._prev = {pid: val for pid, val in self._prev.items() if pid in seen}
        return rows


def collect_gpu_procs() -> tuple[list[GpuProc], str | None]:
    apps = _nvml_apps()
    if apps is not None:
        return [GpuProc(pid=pid, name=name, vram_mib=vram) for pid, name, vram in apps], None
    from machina.util import run_cmd, which

    smi = which("nvidia-smi")
    if not smi:
        return [], "nvidia-smi not found"
    code, out, err = run_cmd(
        [smi, "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader,nounits"],
        timeout=1.5,
    )
    if code != 0:
        return [], (err or out or "nvidia-smi compute-apps failed").strip()[:200]
    rows: list[GpuProc] = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        if parts[0] in {"[N/A]", "N/A", ""}:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        vram = None
        try:
            vram = float(parts[2])
        except ValueError:
            pass
        rows.append(GpuProc(pid=pid, name=parts[1], vram_mib=vram))
    return rows, None


def _boot_time() -> float:
    global _BOOT
    if _BOOT is not None:
        return _BOOT
    try:
        fd = os.open("/proc/stat", _O_RDONLY)
        try:
            text = os.read(fd, 65536).decode("utf-8", "replace")
        finally:
            os.close(fd)
        for line in text.splitlines():
            if line.startswith("btime "):
                _BOOT = float(line.split()[1])
                return _BOOT
    except (OSError, ValueError, IndexError):
        pass
    _BOOT = time.time() - _uptime()
    return _BOOT


def _uptime() -> float:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def _read_proc(path: str, cap: int = 4096) -> bytes | None:
    try:
        fd = os.open(path, _O_RDONLY)
    except OSError:
        return None
    try:
        chunks: list[bytes] = []
        n = 0
        while n < cap:
            buf = os.read(fd, min(4096, cap - n))
            if not buf:
                break
            chunks.append(buf)
            n += len(buf)
            if len(buf) < 4096:
                break
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(fd)


def _parse_pid(
    pid_dir: str, pid: int, boot: float, now: float
) -> tuple[str, str, int, float, float, int, str, int | None, str] | None:
    raw = _read_proc(f"{pid_dir}/stat", 512)
    if not raw:
        return None
    stat = raw.decode("utf-8", "replace")
    lpar = stat.find("(")
    rpar = stat.rfind(")")
    if lpar < 0 or rpar < 0:
        return None
    comm = stat[lpar + 1 : rpar]
    rest = stat[rpar + 2 :].split()
    if len(rest) < 22:
        return None
    state = rest[0]
    try:
        ppid = int(rest[1])
        utime = int(rest[11])
        stime = int(rest[12])
        start_ticks = int(rest[19])
        rss_pages = int(rest[21])
    except (ValueError, IndexError):
        return None
    proc_time = (utime + stime) / CLK_TCK
    start_s = boot + (start_ticks / CLK_TCK)
    cmdline = ""
    cmd_raw = _read_proc(f"{pid_dir}/cmdline", 8192)
    if cmd_raw:
        cmdline = cmd_raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    status_uid = None
    try:
        status_uid = os.stat(pid_dir).st_uid
    except OSError:
        pass
    return comm, state, ppid, proc_time, start_s, rss_pages, cmdline, status_uid, comm


def _match_project(cwd: str | None, cmdline: str, roots: list[tuple[str, Path]]) -> str | None:
    hay = cwd or ""
    if hay:
        try:
            hay = str(Path(hay).resolve())
        except OSError:
            pass
        best: tuple[int, str] | None = None
        for name, root in roots:
            prefix = str(root)
            if hay == prefix or (prefix and hay.startswith(prefix.rstrip("/") + "/")):
                depth = prefix.count("/")
                if best is None or depth > best[0]:
                    best = (depth, name)
        if best:
            return best[1]
    for name, root in roots:
        token = str(root)
        if token and token in cmdline:
            return name
    return None
