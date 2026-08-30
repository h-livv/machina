from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from machina.state import HostState
from machina.ui.pages import Page
from machina.ui.widgets import muted


class ProjectsPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: HostState | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Projects")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(
            muted(
                "Tasks come from each repo’s real entry points (README, CMake binaries, pyproject scripts, justfile if present). "
                "just is not installed on this machine, so Machina does not invent just recipes."
            )
        )
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Task", "Command"])
        self.tree.setColumnWidth(0, 340)
        self.tree.itemDoubleClicked.connect(lambda *_: self._run())
        root.addWidget(self.tree, 1)
        row = QHBoxLayout()
        run = QPushButton("Run")
        run.setObjectName("accent")
        run.clicked.connect(self._run)
        open_dir = QPushButton("Open folder")
        open_dir.clicked.connect(self._open)
        row.addWidget(run)
        row.addWidget(open_dir)
        row.addStretch()
        root.addLayout(row)
        self.hint = muted("Select a task. Output is captured under ~/.local/share/machina/jobs/ and listed on Jobs.")
        root.addWidget(self.hint)

    def apply_state(self, state: HostState) -> None:
        if self._state and [p.path for p in self._state.projects] == [p.path for p in state.projects]:
            self._state = state
            return
        self._state = state
        self.tree.clear()
        for project in state.projects:
            top = QTreeWidgetItem([project.name, project.note or project.path])
            top.setData(0, Qt.ItemDataRole.UserRole, {"project": project.name, "path": project.path})
            groups: dict[str, QTreeWidgetItem] = {}
            for task in project.tasks:
                parent = groups.get(task.group)
                if parent is None:
                    parent = QTreeWidgetItem([task.group, ""])
                    top.addChild(parent)
                    groups[task.group] = parent
                child = QTreeWidgetItem([task.title, " ".join(task.argv)])
                child.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {"project": project.name, "task_id": task.id, "path": project.path, "note": task.note},
                )
                parent.addChild(child)
            self.tree.addTopLevelItem(top)
        if self.tree.topLevelItemCount() and self.tree.topLevelItemCount() <= 8:
            for i in range(self.tree.topLevelItemCount()):
                self.tree.topLevelItem(i).setExpanded(False)

    def _selected(self) -> dict | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _run(self) -> None:
        data = self._selected()
        if not data or "task_id" not in data:
            return
        self.request_runtime.emit("job.launch", {"project": data["project"], "task_id": data["task_id"]})

    def _open(self) -> None:
        data = self._selected()
        if not data or not data.get("path"):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(data["path"]))

    def select_project(self, name: str) -> None:
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            if data.get("project") == name:
                self.tree.setCurrentItem(item)
                item.setExpanded(True)
                break
