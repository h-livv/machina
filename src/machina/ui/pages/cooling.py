from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from machina.telemetry import Snapshot
from machina.ui.pages import Page
from machina.ui.theme import TEXT_DIM
from machina.ui.widgets import Kpi, card, muted


class CoolingPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Cooling")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(
            muted(
                "Victus firmware (hp-wmi) exposes two fans and a single override. Auto lets the EC run the curve. "
                "Max forces the override Omen calls “fan always on / max”."
            )
        )

        self.fan_kpis = QHBoxLayout()
        self.fan1 = Kpi("Fan 1")
        self.fan2 = Kpi("Fan 2")
        self.mode = Kpi("Control")
        self.fan_kpis.addWidget(self.fan1)
        self.fan_kpis.addWidget(self.fan2)
        self.fan_kpis.addWidget(self.mode)
        root.addLayout(self.fan_kpis)

        actions = QHBoxLayout()
        self.btn_auto = QPushButton("BIOS auto")
        self.btn_auto.setObjectName("accent")
        self.btn_max = QPushButton("Maximum override")
        self.btn_max.setObjectName("danger")
        self.btn_auto.clicked.connect(lambda: self.request_actions.emit([{"op": "set_fan_mode", "value": "auto"}], "fan:auto"))
        self.btn_max.clicked.connect(lambda: self.request_actions.emit([{"op": "set_fan_mode", "value": "max"}], "fan:max"))
        actions.addWidget(self.btn_auto)
        actions.addWidget(self.btn_max)
        actions.addStretch()
        root.addLayout(actions)

        self.temps = QLabel()
        self.temps.setWordWrap(True)
        self.temps.setStyleSheet(f"color: {TEXT_DIM};")
        root.addWidget(card(self.temps, title="Thermal sensors"))
        root.addWidget(
            card(
                muted(
                    "There is no pwm1 duty-cycle file on this HP, so Machina will not pretend you can set 37% fan. "
                    "If you need a curve, that has to come from a future firmware/WMI mapping — inventing one would "
                    "just slam max/auto and lie about it."
                ),
                title="Guardrail",
            )
        )
        root.addStretch()

    def apply_snapshot(self, snap: Snapshot) -> None:
        rpm = list(snap.fans.rpm) + [None, None]
        self.fan1.set_value("—" if rpm[0] is None else f"{rpm[0]:,} rpm", "CPU / left")
        self.fan2.set_value("—" if rpm[1] is None else f"{rpm[1]:,} rpm", "GPU / right")
        self.mode.set_value(snap.fans.mode_label, f"pwm1_enable={snap.fans.pwm_enable}")
        lines = []
        for point in snap.thermals:
            extra = ""
            if point.crit_c:
                extra = f"  (crit {point.crit_c:.0f} °C)"
            lines.append(f"{point.source:10}  {point.label:18}  {point.temp_c:5.1f} °C{extra}")
        self.temps.setText("\n".join(lines) if lines else "No thermal sensors.")
        self.btn_auto.setEnabled(snap.fans.mode != "auto")
        self.btn_max.setEnabled(snap.fans.mode != "max")
