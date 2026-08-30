from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from machina.state import HostState
from machina.ui.pages import Page
from machina.ui.widgets import muted
from machina.util import fmt_bytes, fmt_duration
import time


class JobsPage(Page):
    jump_project = None  # set by main window if needed

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: HostState | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Jobs")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(muted("Launched tasks plus long-running project processes discovered from /proc."))

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Name", "Project", "PID", "Status", "CPU", "RAM", "VRAM", "Elapsed"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        row = QHBoxLayout()
        for label, sig in (("Pause", "stop"), ("Resume", "cont"), ("Terminate", "term")):
            btn = QPushButton(label)
            if sig == "term":
                btn.setObjectName("danger")
            btn.clicked.connect(lambda _, s=sig: self._signal(s))
            row.addWidget(btn)
        log = QPushButton("Open output")
        log.clicked.connect(self._open_log)
        cmd = QPushButton("Reveal command")
        cmd.clicked.connect(self._reveal)
        jump = QPushButton("Jump to project")
        jump.clicked.connect(self._jump)
        for b in (log, cmd, jump):
            row.addWidget(b)
        row.addStretch()
        root.addLayout(row)

    def apply_state(self, state: HostState) -> None:
        self._state = state
        jobs = [j for j in state.jobs if j.status not in {"exited"} or (j.ended_at and time.time() - j.ended_at < 120)]
        selected = self._selected_id()
        self.table.setRowCount(len(jobs))
        now = time.time()
        for i, job in enumerate(jobs):
            elapsed = (job.ended_at or now) - job.started_at
            values = [
                job.name,
                job.project or "",
                "" if job.pid is None else str(job.pid),
                job.status,
                "" if job.cpu is None else f"{job.cpu:.0f}%",
                fmt_bytes(job.rss_b) if job.rss_b else "—",
                f"{job.gpu_vram_mib:.0f} MiB" if job.gpu_vram_mib else "—",
                fmt_duration(elapsed),
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, job.id)
                self.table.setItem(i, c, item)
        if selected:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected:
                    self.table.selectRow(row)
                    break

    def _selected_id(self) -> str | None:
        items = self.table.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def _job(self):
        job_id = self._selected_id()
        if not job_id or not self._state:
            return None
        return next((j for j in self._state.jobs if j.id == job_id), None)

    def _signal(self, sig: str) -> None:
        job = self._job()
        if job is None:
            return
        self.request_runtime.emit("job.signal", {"job_id": job.id, "signal": sig, "name": job.name})

    def _open_log(self) -> None:
        job = self._job()
        if job is None:
            return
        target = job.log_path
        if not target:
            QMessageBox.information(self, "No log", "No output path was discovered for this process.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def _reveal(self) -> None:
        job = self._job()
        if job is None:
            return
        QMessageBox.information(self, job.name, job.command + (f"\n\ncwd: {job.cwd}" if job.cwd else ""))

    def _jump(self) -> None:
        job = self._job()
        if job is None or not job.project:
            return
        self.request_runtime.emit("ui.jump_project", {"project": job.project})
