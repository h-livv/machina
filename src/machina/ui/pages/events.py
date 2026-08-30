from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from machina.state import HostState
from machina.ui.pages import Page
from machina.ui.widgets import card, muted


class EventsPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Events")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(muted("Only state changes that matter: thermals, models, jobs, services, disk pressure, telemetry loss."))

        self.timeline = muted("Waiting for correlated samples…")
        root.addWidget(card(self.timeline, title="Correlated timeline"))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["When", "Level", "Title", "Detail"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

    def apply_state(self, state: HostState) -> None:
        if state.timeline:
            lines = []
            for item in list(state.timeline)[-16:]:
                when = datetime.fromtimestamp(item.ts).strftime("%H:%M:%S")
                lines.append(f"{when}   {item.title}\n          {item.detail}")
            self.timeline.setText("\n".join(reversed(lines)))
        self.table.setRowCount(len(state.events))
        for i, event in enumerate(state.events):
            when = datetime.fromtimestamp(event.ts).strftime("%H:%M:%S")
            for c, val in enumerate((when, event.level, event.title, event.detail)):
                self.table.setItem(i, c, QTableWidgetItem(val))
