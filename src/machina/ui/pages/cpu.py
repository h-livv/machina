from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from machina.guardrails import load_guardrails
from machina.telemetry import Snapshot
from machina.ui.pages import Page
from machina.ui.widgets import CoreBar, Kpi, SliderRow, card, muted


class CpuPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        cfg = load_guardrails()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("CPU")
        title.setObjectName("section")
        root.addWidget(title)
        self.model = muted("")
        root.addWidget(self.model)

        grid = QGridLayout()
        self.usage = Kpi("Utilization")
        self.clock = Kpi("Average clock")
        self.temp = Kpi("Package")
        self.turbo = Kpi("Turbo")
        for i, w in enumerate((self.usage, self.clock, self.temp, self.turbo)):
            grid.addWidget(w, 0, i)
        root.addLayout(grid)

        self.bars = CoreBar()
        root.addWidget(card(self.bars, title="Per-logical-CPU utilization"))

        self.min_pct = SliderRow("Minimum performance %", int(cfg["min_perf_pct_floor"]), 100, " %")
        self.max_pct = SliderRow("Maximum performance %", int(cfg["min_perf_pct_floor"]), 100, " %")
        apply_p = QPushButton("Apply P-state limits")
        apply_p.setObjectName("accent")
        apply_p.clicked.connect(self._apply_pstate)
        root.addWidget(card(self.min_pct, self.max_pct, apply_p, title="Intel P-state floors"))

        policy = QWidget()
        row = QHBoxLayout(policy)
        row.setContentsMargins(0, 0, 0, 0)
        self.epp = QComboBox()
        self.gov = QComboBox()
        epp_btn = QPushButton("Set energy preference")
        gov_btn = QPushButton("Set governor")
        epp_btn.clicked.connect(self._apply_epp)
        gov_btn.clicked.connect(self._apply_gov)
        row.addWidget(self.epp, 2)
        row.addWidget(epp_btn)
        row.addWidget(self.gov, 2)
        row.addWidget(gov_btn)
        turbo_on = QPushButton("Enable turbo")
        turbo_off = QPushButton("Disable turbo")
        turbo_off.setObjectName("danger")
        turbo_on.clicked.connect(lambda: self.request_actions.emit([{"op": "set_turbo", "enabled": True}], "turbo:on"))
        turbo_off.clicked.connect(lambda: self.request_actions.emit([{"op": "set_turbo", "enabled": False}], "turbo:off"))
        row.addWidget(turbo_on)
        row.addWidget(turbo_off)
        root.addWidget(card(policy, title="Policy knobs"))
        root.addStretch()
        self._snap: Snapshot | None = None

    def _apply_pstate(self) -> None:
        self.request_actions.emit(
            [{"op": "set_pstate", "min_pct": self.min_pct.slider.value(), "max_pct": self.max_pct.slider.value()}],
            "pstate",
        )

    def _apply_epp(self) -> None:
        self.request_actions.emit([{"op": "set_epp", "value": self.epp.currentText()}], "epp")

    def _apply_gov(self) -> None:
        self.request_actions.emit([{"op": "set_governor", "value": self.gov.currentText()}], "governor")

    def apply_snapshot(self, snap: Snapshot) -> None:
        self._snap = snap
        cpu = snap.cpu
        self.model.setText(f"{cpu.model}  ·  {cpu.logical_cpus} threads  ·  driver {cpu.driver}  ·  load {cpu.loadavg[0]:.2f}")
        self.usage.set_value("—" if cpu.usage is None else f"{cpu.usage:.0f} %", "all cores")
        self.clock.set_value("—" if cpu.avg_mhz is None else f"{cpu.avg_mhz:.0f} MHz", f"max {cpu.max_mhz:.0f} MHz" if cpu.max_mhz else "")
        self.temp.set_value("—" if cpu.package_temp_c is None else f"{cpu.package_temp_c:.0f} °C", "coretemp")
        if cpu.turbo_enabled is None:
            self.turbo.set_value("—", "intel_pstate")
        else:
            self.turbo.set_value("On" if cpu.turbo_enabled else "Off", "no_turbo sysfs")
        bars = []
        for core in cpu.cores:
            bars.append((str(core.index), core.usage or 0.0))
        self.bars.set_cores(bars)
        if cpu.min_perf_pct is not None and not self.min_pct.slider.isSliderDown():
            self.min_pct.set_value_silent(cpu.min_perf_pct)
        if cpu.max_perf_pct is not None and not self.max_pct.slider.isSliderDown():
            self.max_pct.set_value_silent(cpu.max_perf_pct)
        if self.epp.count() == 0 and cpu.epp_available:
            self.epp.addItems(cpu.epp_available)
        if cpu.epp:
            idx = self.epp.findText(cpu.epp)
            if idx >= 0:
                self.epp.setCurrentIndex(idx)
        if self.gov.count() == 0 and cpu.governors:
            self.gov.addItems(cpu.governors)
        if cpu.governor:
            idx = self.gov.findText(cpu.governor)
            if idx >= 0:
                self.gov.setCurrentIndex(idx)
