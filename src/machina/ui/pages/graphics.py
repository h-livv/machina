from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout

from machina.guardrails import load_guardrails
from machina.telemetry import Snapshot
from machina.ui.pages import Page
from machina.ui.widgets import Kpi, SliderRow, card, muted


class GraphicsPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._applying = False
        cfg = load_guardrails()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Graphics")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(muted("NVIDIA RTX 4050 Max-Q plus Intel Raptor Lake UHD. Power limit is the main safe lever."))

        grid = QGridLayout()
        self.name = Kpi("GPU")
        self.temp = Kpi("Temperature")
        self.util = Kpi("Utilization")
        self.clocks = Kpi("Clocks")
        self.mem = Kpi("VRAM")
        self.pstate = Kpi("P-state")
        for i, w in enumerate((self.name, self.temp, self.util, self.clocks, self.mem, self.pstate)):
            grid.addWidget(w, i // 3, i % 3)
        root.addLayout(grid)

        self.slider = SliderRow(
            "NVIDIA power limit",
            int(cfg["nvidia_min_w"]),
            int(cfg["nvidia_max_w"]),
            " W",
        )
        self.slider.valueCommitted.connect(self._set_pl)
        hint = muted(
            f"HP’s advertised default on this chassis is {cfg['nvidia_oem_default_w']:.0f} W. "
            f"Above {cfg['nvidia_warn_above_w']:.0f} W needs confirmation. "
            f"Above {cfg['nvidia_danger_above_w']:.0f} W is treated as high risk. "
            "The hardware max is 75 W; Machina will not write below 30 W."
        )
        root.addWidget(card(self.slider, hint, title="Power cap"))

        row_btns = []
        for label, watts in (("Silent 45 W", 45), ("OEM 60 W", 60), ("Boost 70 W", 70)):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, w=watts: self._set_pl(w))
            row_btns.append(btn)
        from PySide6.QtWidgets import QHBoxLayout

        buttons = QHBoxLayout()
        for btn in row_btns:
            buttons.addWidget(btn)
        buttons.addStretch()
        root.addLayout(buttons)

        self.igpu = muted("iGPU: —")
        root.addWidget(self.igpu)
        self.warn = muted("")
        root.addWidget(self.warn)
        root.addStretch()

    def _set_pl(self, watts: int) -> None:
        self.request_actions.emit([{"op": "set_gpu_power_limit", "watts": int(watts)}], "gpu:power")

    def apply_snapshot(self, snap: Snapshot) -> None:
        gpu = snap.gpu
        if not gpu.present:
            self.name.set_value("Not found", "nvidia-smi missing")
            return
        if gpu.error:
            self.name.set_value("Error", gpu.error)
            return
        self.name.set_value(gpu.name or "NVIDIA", gpu.driver or "")
        self.temp.set_value("—" if gpu.temp_c is None else f"{gpu.temp_c:.0f} °C", "GPU")
        self.util.set_value("—" if gpu.util is None else f"{gpu.util:.0f} %", "compute")
        clocks = "—"
        if gpu.clock_graphics_mhz is not None:
            clocks = f"{gpu.clock_graphics_mhz:.0f} / {gpu.clock_memory_mhz or 0:.0f} MHz"
        self.clocks.set_value(clocks, "core / memory")
        if gpu.mem_used_mib is not None and gpu.mem_total_mib:
            self.mem.set_value(f"{gpu.mem_used_mib:.0f} / {gpu.mem_total_mib:.0f} MiB", "framebuffer")
        self.pstate.set_value(gpu.pstate or "—", "performance state")
        if gpu.power_limit_w is not None and not self.slider.slider.isSliderDown():
            self.slider.set_value_silent(int(round(gpu.power_limit_w)))
        ig = snap.igpu
        if ig.present:
            self.igpu.setText(
                f"Intel iGPU  {ig.cur_mhz:.0f} MHz  (range {ig.min_mhz:.0f}–{ig.boost_mhz or ig.max_mhz:.0f})"
            )
        flags = []
        if gpu.thermal_slowdown:
            flags.append("software thermal slowdown")
        if gpu.hw_thermal_slowdown:
            flags.append("hardware thermal slowdown")
        self.warn.setText("Throttle: " + ", ".join(flags) if flags else "")
