from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout

from machina.guardrails import load_guardrails
from machina.telemetry import Snapshot
from machina.ui.pages import Page
from machina.ui.widgets import Kpi, SliderRow, card, muted


class PowerPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        cfg = load_guardrails()
        self._pl1 = SliderRow("PL1 sustained (package)", int(cfg["rapl_pl1_min_w"]), int(cfg["rapl_pl1_max_w"]), " W")
        self._pl2 = SliderRow("PL2 short burst (package)", int(cfg["rapl_pl2_min_w"]), int(cfg["rapl_pl2_max_w"]), " W")
        self._pending_pl1 = None
        self._pending_pl2 = None
        self._bright = SliderRow("Panel brightness", 1, 100, "%")
        self._bright.valueCommitted.connect(
            lambda v: self.request_actions.emit([{"op": "set_backlight", "percent": v}], "backlight")
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Power & battery")
        title.setObjectName("section")
        root.addWidget(title)

        grid = QGridLayout()
        self.charge = Kpi("Charge")
        self.health = Kpi("Battery health")
        self.cycles = Kpi("Cycles")
        self.draw = Kpi("Battery power")
        for i, w in enumerate((self.charge, self.health, self.cycles, self.draw)):
            grid.addWidget(w, 0, i)
        root.addLayout(grid)

        apply_btn = QPushButton("Apply RAPL limits")
        apply_btn.setObjectName("accent")
        apply_btn.clicked.connect(self._commit_rapl)
        root.addWidget(
            card(
                self._pl1,
                self._pl2,
                apply_btn,
                muted(
                    "Intel RAPL PL1 is the sustained CPU package cap (this 13420H reports 45 W max). "
                    "PL2 is the short burst cap (90 W). Machina will not write above those hardware maxima."
                ),
                title="CPU package power limits",
            )
        )
        root.addWidget(card(self._bright, title="Display"))
        self.note = muted("")
        root.addWidget(self.note)
        root.addStretch()

    def _commit_rapl(self, *_args) -> None:
        self.request_actions.emit(
            [{"op": "set_rapl", "pl1_w": self._pl1.slider.value(), "pl2_w": self._pl2.slider.value()}],
            "rapl",
        )

    def apply_snapshot(self, snap: Snapshot) -> None:
        bat = snap.battery
        if bat.present:
            ac = "AC" if bat.ac_online else "battery"
            self.charge.set_value(f"{bat.percent}%", f"{bat.status} · {ac}")
            self.health.set_value("—" if bat.health_pct is None else f"{bat.health_pct:.0f}%", "full / design")
            self.cycles.set_value("—" if bat.cycle_count is None else str(bat.cycle_count), "charge cycles")
            if bat.power_w:
                self.draw.set_value(f"{bat.power_w:.1f} W", "power_now")
            else:
                self.draw.set_value("0 W", "idle / full")
        limits = {item.name: item for item in snap.power.rapl_limits}
        if "long_term" in limits and limits["long_term"].power_limit_w and not self._pl1.slider.isSliderDown():
            self._pl1.set_value_silent(int(round(limits["long_term"].power_limit_w)))
        if "short_term" in limits and limits["short_term"].power_limit_w and not self._pl2.slider.isSliderDown():
            self._pl2.set_value_silent(int(round(limits["short_term"].power_limit_w)))
        if snap.backlight.present and snap.backlight.percent is not None and not self._bright.slider.isSliderDown():
            self._bright.set_value_silent(int(round(snap.backlight.percent)))
        extra = []
        if not snap.power.rapl_energy_readable:
            extra.append("Live CPU wattage needs root to read energy_uj; limits can still be written via pkexec.")
        self.note.setText(" ".join(extra))
