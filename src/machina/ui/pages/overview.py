from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from machina.state import HostState
from machina.telemetry import Snapshot
from machina.ui.pages import Page
from machina.ui.widgets import CircularGauge, Kpi, card, muted
from machina.util import fmt_bytes


class OverviewPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self.machine = QLabel("Detecting hardware…")
        self.machine.setObjectName("muted")
        root.addWidget(self.machine)

        self.status = QLabel("READING")
        self.status.setObjectName("statusUnknown")
        self.summary_body = muted("Waiting for the first complete sample.")
        self.summary_body.setMaximumHeight(72)
        root.addWidget(card(self.status, self.summary_body))

        gauges = QHBoxLayout()
        gauges.setSpacing(10)
        self.cpu_temp = CircularGauge("CPU", "°C", 100)
        self.gpu_temp = CircularGauge("GPU", "°C", 100)
        self.cpu_load = CircularGauge("CPU load", "%", 100)
        self.cpu_load.warn_at = 70
        self.cpu_load.danger_at = 90
        self.gpu_load = CircularGauge("GPU load", "%", 100)
        self.gpu_load.warn_at = 80
        self.gpu_load.danger_at = 95
        for g in (self.cpu_temp, self.gpu_temp, self.cpu_load, self.gpu_load):
            g.setMinimumSize(110, 128)
            g.setMaximumHeight(140)
            gauges.addWidget(card(g))
        root.addLayout(gauges)

        kpis = QGridLayout()
        kpis.setSpacing(10)
        self.kpi_ram = Kpi("RAM")
        self.kpi_vram = Kpi("VRAM")
        self.kpi_clock = Kpi("CPU clock")
        self.kpi_gpu_w = Kpi("GPU power")
        for i, w in enumerate((self.kpi_ram, self.kpi_vram, self.kpi_clock, self.kpi_gpu_w)):
            kpis.addWidget(w, 0, i)
        root.addLayout(kpis)
        root.addStretch()

    def apply_snapshot(self, snap: Snapshot) -> None:
        host = snap.host
        self.machine.setText(f"{host.product}  ·  {host.os_pretty}")
        self.cpu_temp.set_value(snap.cpu.package_temp_c)
        self.gpu_temp.set_value(snap.gpu.temp_c if snap.gpu.present else None)
        self.cpu_load.set_value(snap.cpu.usage)
        self.gpu_load.set_value(snap.gpu.util if snap.gpu.present else None)

        mem = snap.memory
        if mem.used_b and mem.total_b:
            pct = 100.0 * mem.used_b / mem.total_b
            swap = f" · swap {fmt_bytes(mem.swap_used_b)}" if mem.swap_used_b else ""
            self.kpi_ram.set_value(f"{pct:.0f}%", f"{fmt_bytes(mem.used_b)} / {fmt_bytes(mem.total_b)}{swap}")
        else:
            self.kpi_ram.set_value("—", "RAM")
        if snap.gpu.present and snap.gpu.mem_used_mib is not None and snap.gpu.mem_total_mib:
            self.kpi_vram.set_value(
                f"{snap.gpu.mem_used_mib:.0f} MiB",
                f"of {snap.gpu.mem_total_mib:.0f} MiB",
            )
        else:
            self.kpi_vram.set_value("—", "VRAM")
        if snap.cpu.avg_mhz:
            self.kpi_clock.set_value(f"{snap.cpu.avg_mhz:.0f} MHz", snap.cpu.model.split("(")[0].strip())
        else:
            self.kpi_clock.set_value("—", "CPU clock")
        if snap.gpu.present and snap.gpu.power_w is not None:
            cap = f"cap {snap.gpu.power_limit_w:.0f} W" if snap.gpu.power_limit_w else "GPU"
            self.kpi_gpu_w.set_value(f"{snap.gpu.power_w:.1f} W", cap)
        else:
            self.kpi_gpu_w.set_value("—", "GPU power")

    def apply_state(self, state: HostState) -> None:
        self.apply_snapshot(state.snap)
        summary = state.summary
        if not summary:
            return
        self.status.setText(summary.status)
        level = {"ok": "statusOk", "warn": "statusWarn", "critical": "statusBad"}.get(summary.level, "statusUnknown")
        if self.status.objectName() != level:
            self.status.setObjectName(level)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
        lines = list(summary.lines[:4])
        if summary.weak:
            lines.append("Partial data — claims are qualified.")
        self.summary_body.setText("\n".join(lines))
