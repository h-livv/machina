from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout

from machina.control import apply_actions
from machina.state import HostState
from machina.telemetry import Snapshot
from machina.ui.pages import Page
from machina.ui.theme import TEXT_DIM
from machina.ui.widgets import Kpi, card, muted
from machina.util import fmt_bytes


class HealthPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Hardware health")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(muted("Only sensors this kernel actually exports. SMART is root-only here and is a one-shot privileged read."))

        grid = QGridLayout()
        self.cpu = Kpi("CPU package")
        self.gpu = Kpi("GPU")
        self.nvme = Kpi("NVMe")
        self.fan = Kpi("Fans")
        self.throttle = Kpi("Throttle")
        self.batt = Kpi("Battery health")
        for i, w in enumerate((self.cpu, self.gpu, self.nvme, self.fan, self.throttle, self.batt)):
            grid.addWidget(w, i // 3, i % 3)
        root.addLayout(grid)

        self.temps = QLabel()
        self.temps.setWordWrap(True)
        self.temps.setStyleSheet(f"color: {TEXT_DIM};")
        root.addWidget(card(self.temps, title="Thermal sensors"))

        self.smart = muted("SMART: not read yet. nvme/smartctl need root on this box.")
        smart_btn = QPushButton("Read NVMe SMART (pkexec)")
        smart_btn.clicked.connect(self._smart)
        root.addWidget(card(self.smart, smart_btn, title="Drive"))
        self.power = muted("")
        root.addWidget(self.power)

    def apply_snapshot(self, snap: Snapshot) -> None:
        self.cpu.set_value(
            "—" if snap.cpu.package_temp_c is None else f"{snap.cpu.package_temp_c:.0f} °C",
            f"{snap.cpu.avg_mhz:.0f} MHz" if snap.cpu.avg_mhz else snap.cpu.model,
        )
        if snap.gpu.present and not snap.gpu.error:
            extra = snap.gpu.pstate or ""
            if snap.gpu.thermal_slowdown:
                extra = "software thermal slowdown"
            self.gpu.set_value(
                "—" if snap.gpu.temp_c is None else f"{snap.gpu.temp_c:.0f} °C",
                extra,
            )
        else:
            self.gpu.set_value("—", snap.gpu.error or "no GPU telemetry")
        nvme = next((t for t in snap.thermals if t.source == "nvme" and "composite" in t.label.lower()), None)
        self.nvme.set_value("—" if nvme is None else f"{nvme.temp_c:.0f} °C", nvme.label if nvme else "no nvme hwmon")
        if snap.fans.rpm:
            self.fan.set_value(" / ".join(f"{r:,}" for r in snap.fans.rpm), snap.fans.mode_label)
        else:
            self.fan.set_value("—", snap.fans.note)
        th = snap.throttle
        if not th.available:
            self.throttle.set_value("Unavailable", th.note)
        elif th.rising:
            self.throttle.set_value("Rising", f"core {th.core_count}  pkg {th.package_count}")
        else:
            self.throttle.set_value("Idle", f"core count {th.core_count} since boot")
        if snap.battery.present:
            health = "—" if snap.battery.health_pct is None else f"{snap.battery.health_pct:.0f}%"
            extra = snap.battery.status or ""
            if snap.battery.ac_online:
                extra = "AC · " + extra
            self.batt.set_value(health, extra)
        lines = []
        for point in snap.thermals:
            extra = f"  crit {point.crit_c:.0f}" if point.crit_c else ""
            lines.append(f"{point.source:10}  {point.label:18}  {point.temp_c:5.1f} °C{extra}")
        self.temps.setText("\n".join(lines) if lines else "No thermal sensors.")
        bits = []
        if snap.power.package_power_w is None:
            bits.append("CPU package watts: unavailable (energy_uj is root-only).")
        if snap.gpu.present and snap.gpu.power_w is not None:
            bits.append(f"GPU {snap.gpu.power_w:.1f} W / cap {snap.gpu.power_limit_w or 0:.0f} W.")
        mem = snap.memory
        if mem.used_b and mem.total_b:
            bits.append(f"RAM {fmt_bytes(mem.used_b)} / {fmt_bytes(mem.total_b)}.")
        self.power.setText("  ".join(bits))

    def apply_state(self, state: HostState) -> None:
        self.apply_snapshot(state.snap)
        store = state.storage
        if store and store.nvme_model:
            self.smart.setText(
                f"{store.nvme_model}  fw {store.nvme_fw or '—'}  ·  {store.smart or 'SMART not read'}"
            )

    def _smart(self) -> None:
        result = apply_actions([{"op": "read_nvme_smart"}], reason="smart")
        if result.cancelled:
            self.smart.setText("SMART read cancelled.")
            return
        if result.ok:
            text = result.details[-1] if result.details else result.message
            self.smart.setText(text[:1500])
        else:
            self.smart.setText(result.message)
