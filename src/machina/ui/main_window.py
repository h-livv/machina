from __future__ import annotations

import sys
import time
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from machina.control import ApplyResult, apply_actions
from machina.guardrails import assess, load_guardrails, watchdog_plan
from machina.host import Engine
from machina.models import is_llama_source
from machina.paths import icon_path
from machina.runtime import RuntimeResult, dispatch
from machina.state import HostState
from machina.telemetry import Snapshot
from machina.ui.pages.cooling import CoolingPage
from machina.ui.pages.cpu import CpuPage
from machina.ui.pages.events import EventsPage
from machina.ui.pages.graphics import GraphicsPage
from machina.ui.pages.health import HealthPage
from machina.ui.pages.jobs import JobsPage
from machina.ui.pages.logs import LogsPage
from machina.ui.pages.models import ModelsPage
from machina.ui.pages.network import NetworkPage
from machina.ui.pages.overview import OverviewPage
from machina.ui.pages.parameters import ParametersPage
from machina.ui.pages.performance import PerformancePage
from machina.ui.pages.power import PowerPage
from machina.ui.pages.processes import ProcessesPage
from machina.ui.pages.projects import ProjectsPage
from machina.ui.pages.safety import SafetyPage
from machina.ui.pages.services import ServicesPage
from machina.ui.pages.storage import StoragePage
from machina.ui.theme import apply_theme
from machina.ui.widgets import ConfirmDialog


NAV: list[tuple[str | None, str | None, type | None]] = [
    (None, "Overview", OverviewPage),
    (None, "Performance", PerformancePage),
    (None, "CPU", CpuPage),
    (None, "Cooling", CoolingPage),
    (None, "Graphics", GraphicsPage),
    (None, "Power", PowerPage),
    (None, "Processes", ProcessesPage),
    (None, "Jobs", JobsPage),
    (None, "Services", ServicesPage),
    (None, "Models", ModelsPage),
    (None, "Parameters", ParametersPage),
    (None, "Storage", StoragePage),
    (None, "Health", HealthPage),
    (None, "Network", NetworkPage),
    ("MORE", None, None),
    (None, "Projects", ProjectsPage),
    (None, "Logs", LogsPage),
    (None, "Events", EventsPage),
    (None, "Safety", SafetyPage),
]


class Collector(QThread):
    updated = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.engine = Engine()

    def run(self) -> None:
        try:
            self.engine.tick()
        except Exception:
            pass
        self.msleep(300)
        while not self.isInterruptionRequested():
            try:
                state = self.engine.tick()
            except Exception as exc:  # noqa: BLE001
                state = exc
            self.updated.emit(state)
            self.msleep(1000)


class ApplyWorker(QThread):
    done = Signal(object)

    def __init__(self, actions: list[dict[str, Any]], reason: str) -> None:
        super().__init__()
        self.actions = actions
        self.reason = reason

    def run(self) -> None:
        try:
            self.done.emit(apply_actions(self.actions, self.reason))
        except Exception as exc:  # noqa: BLE001 — must emit so the UI can clear _busy
            self.done.emit(ApplyResult(False, False, False, str(exc), [], {}))


class RuntimeWorker(QThread):
    done = Signal(object)

    def __init__(self, kind: str, payload: dict[str, Any]) -> None:
        super().__init__()
        self.kind = kind
        self.payload = payload

    def run(self) -> None:
        self.done.emit(dispatch(self.kind, self.payload))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Machina")
        self.resize(1380, 860)
        self.setMinimumSize(1100, 720)
        icon = icon_path()
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self._snap: Snapshot | None = None
        self._state: HostState | None = None
        self._apply_worker: ApplyWorker | None = None
        self._runtime_worker: RuntimeWorker | None = None
        self._watchdog_until = 0.0
        self._busy = False
        self._apply_reason = ""
        self._hot_streak = 0
        self._started = time.time()
        self.page_by_name: dict[str, Any] = {}

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 18, 12, 12)
        side.setSpacing(4)
        brand = QLabel("MACHINA")
        brand.setObjectName("brand")
        sub = QLabel("Local control plane")
        sub.setObjectName("brandSub")
        side.addWidget(brand)
        side.addWidget(sub)
        side.addSpacing(8)

        self.stack = QStackedWidget()
        self.pages: list[tuple[str, Any]] = []
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        nav_index = 0
        for section, name, cls in NAV:
            if section:
                label = QLabel(section)
                label.setObjectName("navSection")
                side.addWidget(label)
                continue
            assert name and cls
            page = cls()
            btn = QPushButton(name)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setChecked(nav_index == 0)
            self.nav_group.addButton(btn, nav_index)
            side.addWidget(btn)
            page.request_actions.connect(self.handle_actions)
            page.request_runtime.connect(self.handle_runtime)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            if name in {"Overview", "Parameters", "Models"}:
                scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            if name == "Models":
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
            self.pages.append((name, page))
            self.page_by_name[name] = page
            nav_index += 1
        self.nav_group.idClicked.connect(self.stack.setCurrentIndex)
        self.stack.currentChanged.connect(self._on_page)
        side.addStretch()
        self.side_status = QLabel("Reading sensors…")
        self.side_status.setObjectName("brandSub")
        self.side_status.setWordWrap(True)
        side.addWidget(self.side_status)

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_scroll.setFixedWidth(232)
        side_scroll.setWidget(sidebar)

        main = QWidget()
        main_l = QVBoxLayout(main)
        main_l.setContentsMargins(24, 18, 24, 18)
        main_l.setSpacing(12)

        self.banner = QFrame()
        self.banner.setObjectName("banner")
        self.banner.setProperty("level", "ok")
        banner_l = QHBoxLayout(self.banner)
        self.banner_text = QLabel("Telemetry is local. Nothing is uploaded.")
        self.banner_text.setWordWrap(True)
        self.banner.hide()
        banner_l.addWidget(self.banner_text)
        main_l.addWidget(self.banner)

        pills = QHBoxLayout()
        self.pill_status, self.pill_status_lbl = self._make_pill("Status")
        self.pill_profile, self.pill_profile_lbl = self._make_pill("Profile")
        self.pill_fans, self.pill_fans_lbl = self._make_pill("Fans")
        self.pill_power, self.pill_power_lbl = self._make_pill("Power")
        for frame in (self.pill_status, self.pill_profile, self.pill_fans, self.pill_power):
            pills.addWidget(frame)
        pills.addStretch()
        self.busy_lbl = QLabel("")
        pills.addWidget(self.busy_lbl)
        main_l.addLayout(pills)
        main_l.addWidget(self.stack, 1)

        layout.addWidget(side_scroll)
        layout.addWidget(main, 1)

        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage("Machina  ·  allowlisted writes  ·  pkexec only for privileged sysfs / systemctl / foreign pids")

        self.collector = Collector()
        self.collector.updated.connect(self.on_state)
        self.collector.start()

    @staticmethod
    def _make_pill(prefix: str) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setObjectName("card")
        frame.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 8, 14, 8)
        label = QLabel(f"{prefix}  —")
        label.setStyleSheet("color:#9AA8B7;")
        layout.addWidget(label)
        return frame, label

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self.collector.requestInterruption()
        self.collector.wait(1500)
        super().closeEvent(event)

    def _show_banner(self, text: str, level: str) -> None:
        self.banner_text.setText(text)
        self.banner.setProperty("level", level)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner.setVisible(bool(text))

    def _show_page(self, name: str) -> None:
        for i, (page_name, _) in enumerate(self.pages):
            if page_name == name:
                self.stack.setCurrentIndex(i)
                return

    def _on_page(self, index: int) -> None:
        button = self.nav_group.button(index)
        if button is not None:
            button.setChecked(True)
        if self._state is not None:
            self._apply_visible(self._state)

    def _apply_visible(self, state: HostState) -> None:
        if not self.isVisible() or self.isMinimized():
            return
        idx = self.stack.currentIndex()
        if idx < 0 or idx >= len(self.pages):
            return
        name, page = self.pages[idx]
        try:
            page.apply_state(state)
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"{name} update failed: {exc}")

    @Slot(object)
    def on_state(self, state: object) -> None:
        if isinstance(state, Exception):
            self.statusBar().showMessage(f"Sensor error: {state}")
            return
        assert isinstance(state, HostState)
        self._state = state
        self._snap = state.snap
        snap = state.snap
        self._apply_visible(state)
        summary = state.summary
        status_txt = f"Status  {summary.status if summary else '—'}"
        if self.pill_status_lbl.text() != status_txt:
            self.pill_status_lbl.setText(status_txt)
        profile = (snap.profile.current or "—").title()
        fans = snap.fans.mode_label
        if snap.fans.rpm:
            fans = f"{fans}  ·  {max(snap.fans.rpm):,} rpm"
        ac = "AC" if snap.battery.ac_online else ("Battery" if snap.battery.present else "Power")
        if snap.battery.present and snap.battery.percent is not None:
            ac = f"{ac}  {snap.battery.percent}%"
        profile_txt = f"Profile  {profile}"
        fans_txt = f"Fans  {fans}"
        if self.pill_profile_lbl.text() != profile_txt:
            self.pill_profile_lbl.setText(profile_txt)
        if self.pill_fans_lbl.text() != fans_txt:
            self.pill_fans_lbl.setText(fans_txt)
        if self.pill_power_lbl.text() != ac:
            self.pill_power_lbl.setText(ac)
        line = summary.status if summary else snap.host.product
        side = f"{line}\n{snap.host.product}"
        if self.side_status.text() != side:
            self.side_status.setText(side)

        cfg = load_guardrails()
        plan = watchdog_plan(snap, cfg)
        if plan and plan["level"] in {"trip", "critical"}:
            self._hot_streak += 1
        else:
            self._hot_streak = 0
        warmed_up = (time.time() - self._started) >= 4.0
        cpu_t = snap.cpu.package_temp_c
        gpu_t = getattr(snap.gpu, "temp_c", None)
        if cfg.get("watchdog_enabled", True) and cpu_t is None and gpu_t is None:
            self._show_banner("Watchdog idle: no package/GPU temperature.", "warn")
        elif plan and plan["level"] == "warn":
            self._show_banner(plan["message"], "warn")
        elif (
            plan
            and plan["actions"]
            and warmed_up
            and self._hot_streak >= 3
            and time.time() >= self._watchdog_until
            and not self._busy
        ):
            self._show_banner(plan["message"], "critical")
            self._run_apply(plan["actions"], f"watchdog:{plan['level']}", skip_confirm=True)
        elif not plan:
            if self.banner.property("level") != "ok":
                self.banner.hide()

    @Slot(list, str)
    def handle_actions(self, actions: list, reason: str) -> None:
        self._run_apply(actions, reason, skip_confirm=False)

    @Slot(str, dict)
    def handle_runtime(self, kind: str, payload: dict) -> None:
        if kind == "storage.refresh":
            self.collector.engine.storage.request()
            self.statusBar().showMessage("Directory size scan started in the background.")
            return
        if kind == "ui.jump_project":
            self._show_page("Projects")
            page = self.page_by_name.get("Projects")
            if isinstance(page, ProjectsPage):
                page.select_project(str(payload.get("project") or ""))
            return
        risk, title, bullets = _runtime_risk(kind, payload)
        cfg = load_guardrails()
        if risk == "blocked":
            QMessageBox.warning(self, "Blocked", bullets[0] if bullets else title)
            return
        need = (risk == "high" and cfg.get("confirm_high", True)) or (
            risk == "medium" and cfg.get("confirm_medium", True)
        )
        if need:
            dialog = ConfirmDialog(title, "This is a process, service, or model control — not a firmware write.", bullets, risk, self)
            if dialog.exec() != dialog.DialogCode.Accepted:
                return
        if self._busy:
            self.statusBar().showMessage("Another change is still applying…")
            return
        self._busy = True
        if kind == "model.load_max_gpu":
            if payload.get("reuse") and not payload.get("force"):
                self.busy_lbl.setText("Loading remembered GPU layers…")
                self.statusBar().showMessage("Using the saved max layer count for this model.")
            else:
                self.busy_lbl.setText("Probing max GPU layers…")
                self.statusBar().showMessage("Raising num_gpu / -ngl until the LLM is fully on GPU (or VRAM is full). This can take a few minutes.")
        elif kind == "model.apply_params":
            self.busy_lbl.setText("Applying parameters…")
            if is_llama_source(str(payload.get("source") or "")):
                self.statusBar().showMessage("Restarting llama serve with -c / -ngl / samplers, then loading the GGUF.")
            else:
                self.statusBar().showMessage("Reloading the runner with /set options. num_ctx / num_gpu can take a minute.")
        elif kind == "model.write_params":
            self.busy_lbl.setText("Writing model…")
            if is_llama_source(str(payload.get("source") or "")):
                self.statusBar().showMessage("Writing llama.cpp models-preset, then restarting serve.")
            else:
                self.statusBar().showMessage("ollama create with the selected /set parameters.")
        else:
            self.busy_lbl.setText("Working…")
        worker = RuntimeWorker(kind, dict(payload))
        self._runtime_worker = worker
        worker.done.connect(self._on_runtime)
        worker.start()

    def _run_apply(self, actions: list, reason: str, skip_confirm: bool) -> None:
        if self._busy:
            self.statusBar().showMessage("Another change is still applying…")
            return
        cfg = load_guardrails()
        on_battery = bool(self._snap and self._snap.battery.present and self._snap.battery.ac_online is False)
        assessment = assess(list(actions), cfg, on_battery=on_battery)
        if assessment.risk == "blocked":
            QMessageBox.warning(self, "Blocked", assessment.blocked_reason or assessment.summary)
            return
        need_confirm = (not skip_confirm) and (
            (assessment.risk == "high" and cfg.get("confirm_high", True))
            or (assessment.risk == "medium" and cfg.get("confirm_medium", True))
        )
        self._busy = True
        if need_confirm:
            dialog = ConfirmDialog(assessment.title, assessment.summary, assessment.bullets, assessment.risk, self)
            if dialog.exec() != dialog.DialogCode.Accepted:
                self._busy = False
                return
        self.busy_lbl.setText("Applying…")
        self._apply_reason = reason
        worker = ApplyWorker(list(actions), reason)
        self._apply_worker = worker
        worker.done.connect(self._on_applied)
        worker.start()

    @Slot(object)
    def _on_applied(self, result: object) -> None:
        self._busy = False
        self.busy_lbl.setText("")
        reason = self._apply_reason
        self._apply_reason = ""
        assert isinstance(result, ApplyResult)
        if result.ok and str(reason).startswith("watchdog:"):
            cfg = load_guardrails()
            self._watchdog_until = time.time() + float(cfg.get("watchdog_cooldown_s", 45))
        if result.cancelled:
            self.statusBar().showMessage(result.message)
            return
        if result.ok:
            self.statusBar().showMessage(result.message)
            self._show_banner(result.message, "ok")
        else:
            QMessageBox.warning(self, "Apply failed", result.message)
            self.statusBar().showMessage(result.message)
        safety = self.page_by_name.get("Safety")
        if isinstance(safety, SafetyPage):
            safety.refresh_log()

    @Slot(object)
    def _on_runtime(self, result: object) -> None:
        self._busy = False
        self.busy_lbl.setText("")
        assert isinstance(result, RuntimeResult)
        if result.cancelled:
            self.statusBar().showMessage("Authorization cancelled — nothing changed.")
            return
        if result.ok:
            self.statusBar().showMessage(result.message)
        else:
            QMessageBox.warning(self, "Action failed", result.message)
            self.statusBar().showMessage(result.message)


def _runtime_risk(kind: str, payload: dict[str, Any]) -> tuple[str, str, list[str]]:
    if kind == "process.signal":
        sig = str(payload.get("signal", "term"))
        pid = payload.get("pid")
        name = payload.get("name") or ""
        cmd = str(payload.get("cmdline") or "")[:200]
        if sig == "kill":
            return "high", "Kill process", [f"SIGKILL {name} pid {pid}", cmd]
        if sig == "term":
            return "medium", "Terminate process", [f"SIGTERM {name} pid {pid}", cmd]
        return "medium", "Signal process", [f"SIG{sig.upper()} {name} pid {pid}"]
    if kind == "job.signal":
        sig = str(payload.get("signal", "term"))
        name = payload.get("name") or payload.get("job_id")
        if sig in {"kill", "term"}:
            return "medium" if sig == "term" else "high", "Stop job", [f"SIG{sig.upper()} {name}"]
        return "low", "Signal job", [f"SIG{sig.upper()} {name}"]
    if kind == "service":
        verb = str(payload.get("verb"))
        unit = str(payload.get("unit"))
        if verb in {"enable", "disable"}:
            return "high", "Change unit enablement", [f"systemctl {verb} {unit}"]
        if verb in {"stop", "restart"}:
            return "medium", "Change service", [f"systemctl {verb} {unit}"]
        return "low", "Start service", [f"systemctl start {unit}"]
    if kind == "model.write_params":
        name = str(payload.get("name") or "")
        if is_llama_source(str(payload.get("source") or "")):
            return "low", "Write llama.cpp preset", [name, "~/.config/machina/llama-preset.ini"]
        return "medium", "Write model parameters", [name, "ollama create FROM this tag"]
    if kind in {"model.stop_ollama", "model.stop_llama", "model.unload", "model.unload_resident"}:
        return "medium", "Stop model server", [kind, str(payload.get("name") or "")]
    if kind == "model.start_freetoken":
        return "low", "Start FreeToken UI", ["~/opt/freetoken-desktop AppImage"]
    return "low", "Runtime action", [kind]


def run_app() -> int:
    from PySide6.QtGui import QGuiApplication

    sys.argv[0] = "machina"
    QGuiApplication.setDesktopFileName("machina")
    app = QApplication(sys.argv)
    app.setApplicationName("machina")
    app.setApplicationDisplayName("Machina")
    app.setOrganizationName("Machina")
    app.setDesktopFileName("machina")
    icon = icon_path()
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    compress = getattr(Qt.ApplicationAttribute, "AA_CompressHighFrequencyEvents", None)
    if compress is not None:
        app.setAttribute(compress, True)
    for effect in ("UI_AnimateCombo", "UI_AnimateTooltip", "UI_AnimateMenu"):
        flag = getattr(Qt.UIEffect, effect, None)
        if flag is not None:
            app.setEffectEnabled(flag, False)
    apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()
