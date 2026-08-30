from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from machina.util import read_text, run_cmd, which


@dataclass
class NetIface:
    name: str
    kind: str
    state: str
    connection: str | None
    ipv4: str | None
    rx_bps: float | None
    tx_bps: float | None
    rx_b: int
    tx_b: int
    wifi_ssid: str | None = None
    wifi_signal: int | None = None


@dataclass
class NetworkInfo:
    ifaces: list[NetIface] = field(default_factory=list)
    default_route: str | None = None
    vpn: str | None = None
    listening: list[str] = field(default_factory=list)
    established: int | None = None
    downloads: list[str] = field(default_factory=list)
    note: str = ""
    ts: float = 0.0


class NetworkSampler:
    def __init__(self) -> None:
        self._prev: dict[str, tuple[int, int, float]] = {}
        self._wifi_ssid: str | None = None
        self._wifi_signal: int | None = None
        self._wifi_ts = 0.0
        self._nm_ts = 0.0
        self._nm: dict[str, tuple[str, str, str | None]] = {}
        self._vpn: str | None = None
        self._addrs: dict[str, str] = {}
        self._addr_ts = 0.0
        self._listening: list[str] = []
        self._established: int | None = None
        self._tcp_ts = 0.0

    def sample(self, download_hints: list[str] | None = None) -> NetworkInfo:
        now = time.time()
        counters = _read_dev()
        if now - self._addr_ts >= 8.0:
            self._addrs = _all_ipv4()
            self._addr_ts = now
        addrs = self._addrs
        self._wifi_from_proc()
        if now - self._nm_ts >= 8.0:
            self._nm = _nmcli_devices()
            self._vpn = _nmcli_vpn()
            self._nm_ts = now
        if now - self._tcp_ts >= 2.0:
            self._listening = _listening_ports()
            self._established = _established_count()
            self._tcp_ts = now
        ifaces: list[NetIface] = []
        for name, (rx, tx) in counters.items():
            if name == "lo":
                continue
            prev = self._prev.get(name)
            rx_bps = tx_bps = None
            if prev:
                dt = now - prev[2]
                if dt > 0:
                    rx_bps = max(0.0, (rx - prev[0]) / dt)
                    tx_bps = max(0.0, (tx - prev[1]) / dt)
            self._prev[name] = (rx, tx, now)
            kind, state, conn = self._nm.get(name, (_guess_kind(name), "unknown", None))
            ipv4 = addrs.get(name)
            ssid = conn if kind == "wifi" else None
            if kind == "wifi" and self._wifi_ssid:
                ssid = self._wifi_ssid
            signal = self._wifi_signal if kind == "wifi" else None
            ifaces.append(
                NetIface(
                    name=name,
                    kind=kind,
                    state=state,
                    connection=conn,
                    ipv4=ipv4,
                    rx_bps=rx_bps,
                    tx_bps=tx_bps,
                    rx_b=rx,
                    tx_b=tx,
                    wifi_ssid=ssid,
                    wifi_signal=signal,
                )
            )
        vpn = None
        for iface in ifaces:
            if iface.kind in {"tun", "wireguard", "vpn"} or iface.name.startswith(("tun", "wg", "tailscale")):
                vpn = iface.connection or iface.name
                break
        if vpn is None:
            vpn = self._vpn
        return NetworkInfo(
            ifaces=ifaces,
            default_route=_default_route(),
            vpn=vpn,
            listening=self._listening,
            established=self._established,
            downloads=download_hints or [],
            ts=now,
        )

    def _wifi_from_proc(self) -> None:
        wireless = Path("/proc/net/wireless")
        if not wireless.exists():
            return
        try:
            for line in wireless.read_text(encoding="utf-8", errors="replace").splitlines()[2:]:
                parts = line.replace(":", " ").split()
                if len(parts) >= 3:
                    try:
                        self._wifi_signal = int(float(parts[2]))
                    except ValueError:
                        pass
        except OSError:
            pass


def _read_dev() -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    try:
        lines = Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]
    except OSError:
        return out
    for line in lines:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        parts = rest.split()
        if len(parts) < 9:
            continue
        try:
            out[name.strip()] = (int(parts[0]), int(parts[8]))
        except ValueError:
            continue
    return out


def _guess_kind(name: str) -> str:
    if name.startswith("wl") or name.startswith("wlp"):
        return "wifi"
    if name.startswith(("en", "eth")):
        return "ethernet"
    if name.startswith("docker") or name.startswith("br-"):
        return "bridge"
    if name.startswith(("tun", "wg", "tailscale")):
        return "vpn"
    return "other"


def _all_ipv4() -> dict[str, str]:
    code, out, _ = run_cmd(["ip", "-br", "-4", "addr"], timeout=0.8)
    if code != 0:
        return {}
    result: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        for token in parts[2:]:
            if "/" in token and token[0].isdigit():
                result[parts[0]] = token
                break
    return result


def _nmcli_devices() -> dict[str, tuple[str, str, str | None]]:
    nmcli = which("nmcli")
    if not nmcli:
        return {}
    code, out, _ = run_cmd([nmcli, "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"], timeout=1.2)
    if code != 0:
        return {}
    result: dict[str, tuple[str, str, str | None]] = {}
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        conn = parts[3] if len(parts) > 3 and parts[3] not in {"", "--"} else None
        result[parts[0]] = (parts[1], parts[2], conn)
    return result


def _nmcli_vpn() -> str | None:
    nmcli = which("nmcli")
    if not nmcli:
        return None
    code, out, _ = run_cmd(
        [nmcli, "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],
        timeout=1.0,
    )
    if code != 0:
        return None
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and ("vpn" in parts[1] or "wireguard" in parts[1]):
            return parts[0]
    return None


def _default_route() -> str | None:
    try:
        for line in Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "00000000":
                return parts[0]
    except OSError:
        pass
    return None


def _listening_ports() -> list[str]:
    interesting = {11434, 8080, 8000, 8888, 5000, 3000, 5173, 11435}
    found: list[str] = []
    for proc_file, ipver in (("/proc/net/tcp", 4), ("/proc/net/tcp6", 6)):
        try:
            lines = Path(proc_file).read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 4 or parts[3] != "0A":
                continue
            local = parts[1]
            try:
                port = int(local.rsplit(":", 1)[1], 16)
            except ValueError:
                continue
            if port in interesting or port >= 8000 and port < 8100:
                found.append(f":{port}")
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:16]


def _established_count() -> int | None:
    try:
        lines = Path("/proc/net/tcp").read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return None
    n = 0
    for line in lines:
        parts = line.split()
        if len(parts) >= 4 and parts[3] == "01":
            n += 1
    return n
