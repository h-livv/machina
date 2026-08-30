from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from machina.state import HostState
from machina.ui.pages import Page
from machina.ui.widgets import muted


class ServicesPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: HostState | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Services")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(
            muted(
                "Only units that matter for this laptop’s compute/GPU/model workflow. "
                "Add more in ~/.config/machina/services.json — system verbs still go through the allowlisted helper."
            )
        )
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Unit", "Scope", "Active", "Enabled", "Why", "Detail"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)
        row = QHBoxLayout()
        for verb in ("start", "stop", "restart", "enable", "disable"):
            btn = QPushButton(verb.title())
            if verb in {"stop", "disable"}:
                btn.setObjectName("danger")
            btn.clicked.connect(lambda _, v=verb: self._verb(v))
            row.addWidget(btn)
        row.addStretch()
        root.addLayout(row)

    def apply_state(self, state: HostState) -> None:
        self._state = state
        self.table.setRowCount(len(state.services))
        for i, svc in enumerate(state.services):
            values = [svc.unit, svc.scope, f"{svc.active}/{svc.sub}", svc.enabled or "—", svc.why, svc.description]
            for c, val in enumerate(values):
                self.table.setItem(i, c, QTableWidgetItem(val))

    def _verb(self, verb: str) -> None:
        if not self._state:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self._state.services):
            return
        svc = self._state.services[row]
        self.request_runtime.emit("service", {"unit": svc.unit, "scope": svc.scope, "verb": verb})
