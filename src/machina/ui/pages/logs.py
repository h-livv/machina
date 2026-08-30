from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
)

from machina.logs import list_sources, read_source
from machina.state import HostState
from machina.ui.pages import Page
from machina.ui.widgets import muted


class LogsPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: HostState | None = None
        self._sources = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Logs")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(muted("Machina, Ollama, allowlisted systemd units, and job output — not the entire journal."))

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Text search")
        self.severity = QComboBox()
        self.severity.addItems(["", "info", "warn", "error"])
        self.severity.setItemText(0, "any severity")
        refresh = QPushButton("Reload")
        refresh.clicked.connect(self._reload)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.severity)
        tools.addWidget(refresh)
        root.addLayout(tools)

        split = QSplitter()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(lambda _: self._reload())
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        split.addWidget(self.list)
        split.addWidget(self.view)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        root.addWidget(split, 1)
        self.search.returnPressed.connect(self._reload)
        self.severity.currentIndexChanged.connect(lambda _: self._reload())

    def apply_state(self, state: HostState) -> None:
        prev_id = None
        row = self.list.currentRow()
        if 0 <= row < len(self._sources):
            prev_id = self._sources[row].id
        self._state = state
        self._sources = list_sources(state.jobs)
        self.list.blockSignals(True)
        self.list.clear()
        for src in self._sources:
            item = QListWidgetItem(src.title)
            item.setToolTip(src.note or src.path or src.unit or "")
            self.list.addItem(item)
        self.list.blockSignals(False)
        if prev_id:
            for i, src in enumerate(self._sources):
                if src.id == prev_id:
                    self.list.setCurrentRow(i)
                    break
        elif self._sources and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        if self.isVisible():
            self._reload()

    def _reload(self) -> None:
        row = self.list.currentRow()
        if row < 0 or row >= len(self._sources):
            return
        src = self._sources[row]
        sev = self.severity.currentText()
        if sev == "any severity":
            sev = ""
        lines = read_source(src, limit=300, query=self.search.text().strip(), severity=sev)
        self.view.setPlainText("\n".join(l.text for l in lines) or f"(empty — {src.note or src.kind})")
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
