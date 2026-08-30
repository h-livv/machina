from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from machina import audit
from machina.guardrails import SAFE_RESTORE, load_guardrails, save_guardrails, thresholds_ordered
from machina.telemetry import Snapshot
from machina.ui.pages import Page
from machina.ui.widgets import card, muted


class SafetyPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        cfg = load_guardrails()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Safety & log")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(
            muted(
                "Writes are allowlisted. The helper only touches known sysfs nodes and nvidia-smi --power-limit. "
                "KDE will prompt via polkit the first time a setting needs root."
            )
        )

        self.watchdog = QCheckBox("Thermal watchdog (auto max-fan / cool profile)")
        self.watchdog.setChecked(bool(cfg.get("watchdog_enabled", True)))
        self.confirm_med = QCheckBox("Confirm medium-risk changes")
        self.confirm_med.setChecked(bool(cfg.get("confirm_medium", True)))
        self.confirm_high = QCheckBox("Confirm high-risk changes (always recommended)")
        self.confirm_high.setChecked(bool(cfg.get("confirm_high", True)))
        self.confirm_high.setEnabled(False)

        temps = QHBoxLayout()
        self.warn = QSpinBox()
        self.trip = QSpinBox()
        self.crit = QSpinBox()
        for box, key, label in (
            (self.warn, "warn_temp_c", "Warn °C"),
            (self.trip, "trip_temp_c", "Trip °C"),
            (self.crit, "critical_temp_c", "Critical °C"),
        ):
            box.setRange(70, 105)
            box.setValue(int(cfg[key]))
            box.setPrefix(label + "  ")
            temps.addWidget(box)
        save = QPushButton("Save guardrails")
        save.setObjectName("accent")
        save.clicked.connect(self._save)
        restore = QPushButton("Restore safe defaults")
        restore.setObjectName("danger")
        restore.clicked.connect(lambda: self.request_actions.emit(list(SAFE_RESTORE), "restore_safe"))

        root.addWidget(card(self.watchdog, self.confirm_med, self.confirm_high, save, title="Guardrails"))
        from PySide6.QtWidgets import QWidget

        temp_host = QWidget()
        wrap = QVBoxLayout(temp_host)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addLayout(temps)
        wrap.addWidget(restore)
        root.addWidget(card(temp_host, title="Thermal thresholds & restore"))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["When", "Reason", "Result", "Detail"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(240)
        root.addWidget(card(self.table, title="Audit log"))
        self.refresh_log()

    def _save(self) -> None:
        warn, trip, crit = self.warn.value(), self.trip.value(), self.crit.value()
        if not thresholds_ordered(warn, trip, crit):
            QMessageBox.warning(
                self,
                "Invalid thresholds",
                "Warn °C must be less than Trip °C, which must be less than Critical °C.",
            )
            return
        cfg = load_guardrails()
        cfg.update(
            {
                "watchdog_enabled": self.watchdog.isChecked(),
                "confirm_medium": self.confirm_med.isChecked(),
                "confirm_high": True,
                "warn_temp_c": warn,
                "trip_temp_c": trip,
                "critical_temp_c": crit,
            }
        )
        save_guardrails(cfg)

    def refresh_log(self) -> None:
        rows = audit.read_recent(80)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            when = datetime.fromtimestamp(row.get("ts", 0)).strftime("%H:%M:%S")
            result = "ok" if row.get("ok") else ("cancelled" if row.get("cancelled") else "fail")
            detail = row.get("message", "")
            if row.get("actions"):
                ops = ",".join(a.get("op", "?") for a in row["actions"][:4])
                detail = f"{ops} · {detail}"
            values = [when, str(row.get("reason", "")), result, detail]
            for c, value in enumerate(values):
                self.table.setItem(i, c, QTableWidgetItem(value))

    def apply_snapshot(self, snap: Snapshot) -> None:
        return
