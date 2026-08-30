from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from machina.paths import disk_cache_path
from machina.util import fmt_bytes, run_cmd


SKIP_TOP = {".git", "node_modules", "__pycache__", ".cache"}


@dataclass
class Mount:
    device: str
    fstype: str
    target: str
    total_b: int
    used_b: int
    free_b: int
    removable: bool
    model: str | None = None


@dataclass
class DirUsage:
    path: str
    bytes: int
    delta_b: int | None = None
    project: str | None = None


@dataclass
class BlockDev:
    name: str
    size_b: int | None
    model: str | None
    tran: str | None
    hotplug: bool
    mountpoint: str | None
    fstype: str | None


@dataclass
class StorageInfo:
    mounts: list[Mount] = field(default_factory=list)
    blocks: list[BlockDev] = field(default_factory=list)
    largest: list[DirUsage] = field(default_factory=list)
    growing: list[DirUsage] = field(default_factory=list)
    scanned_at: float | None = None
    scanning: bool = False
    note: str = ""
    nvme_model: str | None = None
    nvme_fw: str | None = None
    smart: str | None = None  # explicit: unavailable unless privileged refresh


def collect_storage_light() -> StorageInfo:
    mounts = _mounts()
    blocks = _blocks()
    nvme_model = _read_sys("/sys/class/nvme/nvme0/model")
    nvme_fw = _read_sys("/sys/class/nvme/nvme0/firmware_rev")
    info = StorageInfo(
        mounts=mounts,
        blocks=blocks,
        nvme_model=nvme_model,
        nvme_fw=nvme_fw,
        smart="SMART needs a privileged one-shot read (nvme/smartctl are root-only here).",
        note="",
    )
    cache = _load_cache()
    if cache:
        info.largest = [DirUsage(**row) for row in cache.get("largest", [])]
        info.growing = [DirUsage(**row) for row in cache.get("growing", [])]
        info.scanned_at = cache.get("scanned_at")
    return info


class StorageAnalyzer:
    """Background du of a small set of well-known roots. Never deletes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._info = collect_storage_light()
        self._wanted = False

    def snapshot(self) -> StorageInfo:
        with self._lock:
            info = self._info
            info.scanning = bool(self._thread and self._thread.is_alive())
            return info

    def request(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="machina-du", daemon=True)
            self._thread.start()

    def maybe_schedule(self, interval_s: float = 180.0) -> None:
        with self._lock:
            scanned = self._info.scanned_at
        if scanned is None or (time.time() - scanned) >= interval_s:
            self.request()

    def _run(self) -> None:
        try:
            os.nice(10)
        except OSError:
            pass
        light = collect_storage_light()
        prev = {row.path: row.bytes for row in light.largest}
        targets = _scan_targets()
        usage = _du(targets)
        largest = sorted(
            [
                DirUsage(path=p, bytes=b, delta_b=(b - prev[p]) if p in prev else None, project=_project_for(p))
                for p, b in usage.items()
            ],
            key=lambda r: r.bytes,
            reverse=True,
        )
        growing = [row for row in largest if (row.delta_b or 0) > 8 * 1024 * 1024]
        growing.sort(key=lambda r: r.delta_b or 0, reverse=True)
        light.largest = largest[:40]
        light.growing = growing[:20]
        light.scanned_at = time.time()
        light.scanning = False
        _save_cache(light)
        with self._lock:
            self._info = light


def _read_sys(path: str) -> str | None:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return text or None


def _mounts() -> list[Mount]:
    skip_fs = {"tmpfs", "devtmpfs", "squashfs", "overlay", "efivarfs", "proc", "sysfs", "cgroup2", "devpts"}
    skip_targets = {"/boot", "/boot/efi"}
    result: list[Mount] = []
    seen: set[str] = set()
    try:
        lines = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    removable_devs = _removable_devices()
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        device, target, fstype = parts[0], parts[1], parts[2]
        if fstype in skip_fs or target in skip_targets:
            continue
        if not target.startswith("/") or target.startswith("/snap"):
            continue
        if target in seen:
            continue
        if not device.startswith("/dev/") and target not in {"/"}:
            continue
        try:
            usage = os.statvfs(target)
        except OSError:
            continue
        total = usage.f_frsize * usage.f_blocks
        free = usage.f_frsize * usage.f_bavail
        used = total - (usage.f_frsize * usage.f_bfree)
        seen.add(target)
        result.append(
            Mount(
                device=device,
                fstype=fstype,
                target=target,
                total_b=total,
                used_b=used,
                free_b=free,
                removable=any(dev in device for dev in removable_devs),
            )
        )
    return result


def _removable_devices() -> set[str]:
    found: set[str] = set()
    root = Path("/sys/block")
    if not root.exists():
        return found
    for entry in root.iterdir():
        rem = (entry / "removable").read_text(encoding="utf-8", errors="replace").strip() if (entry / "removable").exists() else "0"
        if rem == "1":
            found.add(entry.name)
    return found


def _blocks() -> list[BlockDev]:
    rows: list[BlockDev] = []
    root = Path("/sys/block")
    if not root.exists():
        return rows
    for entry in sorted(root.iterdir()):
        name = entry.name
        if name.startswith(("loop", "ram", "zram", "dm-")):
            continue
        size_sectors = _int_file(entry / "size")
        size_b = size_sectors * 512 if size_sectors else None
        model = _read_sys(str(entry / "device" / "model"))
        tran = None
        if (entry / "device" / "transport").exists():
            tran = _read_sys(str(entry / "device" / "transport"))
        if name.startswith("nvme"):
            tran = tran or "nvme"
        hotplug = _read_sys(str(entry / "removable")) == "1"
        rows.append(
            BlockDev(
                name=name,
                size_b=size_b,
                model=model,
                tran=tran,
                hotplug=hotplug,
                mountpoint=None,
                fstype=None,
            )
        )
    return rows


def _int_file(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _scan_targets() -> list[Path]:
    home = Path.home()
    targets = [
        home / "Projects",
        home / "Labs",
        home / "models-gguf",
        home / "Downloads",
        home / ".cache",
        home / ".local" / "share",
        home / ".ollama",
        home / "opt",
        home / "machina",
    ]
    for child in ("Projects", "Labs"):
        root = home / child
        if root.is_dir():
            try:
                for item in root.iterdir():
                    if item.is_dir() and not item.name.startswith("."):
                        targets.append(item)
            except OSError:
                pass
    vault = Path("/run/media") / os.environ.get("USER", "h-livv")
    media = Path("/run/media/h-livv")
    if media.is_dir():
        try:
            for item in media.iterdir():
                if item.is_dir():
                    targets.append(item)
                    try:
                        for child in item.iterdir():
                            if child.is_dir() and child.name not in SKIP_TOP:
                                targets.append(child)
                    except OSError:
                        pass
        except OSError:
            pass
    return [p for p in targets if p.exists()]


def _du(paths: list[Path]) -> dict[str, int]:
    if not paths:
        return {}
    argv = ["du", "-s", "-b", "--apparent-size"]
    argv.extend(str(p) for p in paths)
    code, out, _ = run_cmd(argv, timeout=90.0)
    result: dict[str, int] = {}
    if code not in {0, 1}:  # du returns 1 if some dirs unreadable
        return result
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        try:
            result[parts[1]] = int(parts[0])
        except ValueError:
            continue
    return result


def _project_for(path: str) -> str | None:
    p = Path(path)
    home = Path.home()
    for root_name in ("Projects", "Labs"):
        root = home / root_name
        try:
            rel = p.resolve().relative_to(root)
        except (ValueError, OSError):
            continue
        parts = rel.parts
        if parts:
            return parts[0]
    return None


def _load_cache() -> dict | None:
    path = disk_cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _save_cache(info: StorageInfo) -> None:
    payload = {
        "scanned_at": info.scanned_at,
        "largest": [asdict(x) for x in info.largest],
        "growing": [asdict(x) for x in info.growing],
    }
    try:
        disk_cache_path().write_text(json.dumps(payload) + "\n", encoding="utf-8")
    except OSError:
        pass
