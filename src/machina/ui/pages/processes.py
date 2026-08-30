from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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


COLS = ("Name", "PID", "CPU %", "RAM", "GPU", "VRAM", "User", "Project", "Time")


class ProcessesPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: HostState | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Processes")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(muted("Replaces routine btop / nvidia-smi process checks. Terminate only affects the selected pid."))

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter name, command, project…")
        self.search.textChanged.connect(self._render)
        self.mine = QCheckBox("Mine only")
        self.mine.setChecked(True)
        self.mine.stateChanged.connect(self._render)
        self.hide_kernel = QCheckBox("Hide kernel threads")
        self.hide_kernel.setChecked(True)
        self.hide_kernel.stateChanged.connect(self._render)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.mine)
        tools.addWidget(self.hide_kernel)
        root.addLayout(tools)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._show_cmd)
        self.table.setMinimumHeight(360)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        cmd_btn = QPushButton("Command line")
        cmd_btn.clicked.connect(self._show_cmd)
        term = QPushButton("Terminate")
        term.setObjectName("danger")
        term.clicked.connect(lambda: self._signal("term"))
        kill = QPushButton("Kill")
        kill.setObjectName("danger")
        kill.clicked.connect(lambda: self._signal("kill"))
        pause = QPushButton("Pause")
        pause.clicked.connect(lambda: self._signal("stop"))
        cont = QPushButton("Resume")
        cont.clicked.connect(lambda: self._signal("cont"))
        for btn in (cmd_btn, pause, cont, term, kill):
            actions.addWidget(btn)
        actions.addStretch()
        root.addLayout(actions)
        self.hint = muted("Select a process. Kernel, compositor, and pid 1 cannot be signalled.")
        root.addWidget(self.hint)

    def apply_state(self, state: HostState) -> None:
        selected = self._selected_pid()
        scroll = self.table.verticalScrollBar().value()
        self._state = state
        self._render()
        if selected is not None:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 1)
                if item and item.text() == str(selected):
                    self.table.selectRow(row)
                    break
        self.table.verticalScrollBar().setValue(scroll)

    def _rows(self):
        if not self._state:
            return []
        q = self.search.text().lower().strip()
        rows = []
        for proc in self._state.processes:
            if self.mine.isChecked() and not proc.own:
                continue
            if self.hide_kernel.isChecked() and not proc.cmdline:
                continue
            hay = f"{proc.name} {proc.cmdline} {proc.project or ''} {proc.user} {proc.pid}"
            if q and q not in hay.lower():
                continue
            rows.append(proc)
        rows.sort(key=lambda p: p.cpu or 0, reverse=True)
        return rows[:400]

    def _render(self) -> None:
        rows = self._rows()
        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        if self.table.rowCount() != len(rows):
            self.table.setRowCount(len(rows))
        for i, proc in enumerate(rows):
            gpu = f"{proc.gpu_sm:.0f}%" if proc.gpu_sm is not None else ("yes" if proc.gpu_vram_mib else "—")
            vram = f"{proc.gpu_vram_mib:.0f} MiB" if proc.gpu_vram_mib is not None else "—"
            values = [
                proc.name,
                str(proc.pid),
                "" if proc.cpu is None else f"{proc.cpu:.1f}",
                fmt_bytes(proc.rss_b),
                gpu,
                vram,
                proc.user,
                proc.project or "",
                fmt_duration(proc.elapsed_s),
            ]
            for c, value in enumerate(values):
                item = self.table.item(i, c)
                if item is None:
                    item = QTableWidgetItem(value)
                    if c in {1, 2}:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(i, c, item)
                elif item.text() != value:
                    item.setText(value)
                item.setData(Qt.ItemDataRole.UserRole, proc.pid)
        self.table.setUpdatesEnabled(True)
        self.table.setSortingEnabled(True)

    def _selected_pid(self) -> int | None:
        items = self.table.selectedItems()
        if not items:
            return None
        try:
            return int(self.table.item(items[0].row(), 1).text())
        except (AttributeError, ValueError):
            return None

    def _selected_proc(self):
        pid = self._selected_pid()
        if pid is None or not self._state:
            return None
        return next((p for p in self._state.processes if p.pid == pid), None)

    def _show_cmd(self) -> None:
        proc = self._selected_proc()
        if proc is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle(f"{proc.name}  pid {proc.pid}")
        box.setText(proc.cmdline or proc.name)
        extra = []
        if proc.cwd:
            extra.append(f"cwd: {proc.cwd}")
        extra.append(f"ppid: {proc.ppid} ({proc.parent_name or '?'})")
        if proc.project:
            extra.append(f"project: {proc.project}")
        box.setInformativeText("\n".join(extra))
        box.exec()

    def _signal(self, sig: str) -> None:
        proc = self._selected_proc()
        if proc is None:
            return
        self.request_runtime.emit(
            "process.signal",
            {"pid": proc.pid, "signal": sig, "name": proc.name, "cmdline": proc.cmdline},
        )
