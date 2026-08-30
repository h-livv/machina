from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from machina.state import HostState
from machina.ui.pages import Page
from machina.ui.widgets import Kpi, card, muted
from machina.util import fmt_bytes


class StoragePage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Storage")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(muted("Machina never deletes files. Refresh walks a small set of project and media directories."))

        grid = QGridLayout()
        self.root_kpi = Kpi("System disk")
        self.vault = Kpi("Removable / Vault")
        self.scan = Kpi("Last scan")
        for i, w in enumerate((self.root_kpi, self.vault, self.scan)):
            grid.addWidget(w, 0, i)
        root.addLayout(grid)

        refresh = QPushButton("Refresh directory sizes")
        refresh.setObjectName("accent")
        refresh.clicked.connect(lambda: self.request_runtime.emit("storage.refresh", {}))
        root.addWidget(refresh)

        self.mounts = QTableWidget(0, 6)
        self.mounts.setHorizontalHeaderLabels(["Mount", "FS", "Used", "Free", "Total", "Removable"])
        self.mounts.horizontalHeader().setStretchLastSection(True)
        root.addWidget(card(self.mounts, title="Mounts"))

        self.largest = QTableWidget(0, 4)
        self.largest.setHorizontalHeaderLabels(["Path", "Size", "Change", "Project"])
        self.largest.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.largest.horizontalHeader().setStretchLastSection(True)
        root.addWidget(card(self.largest, title="Largest watched directories"))

        self.growing = QTableWidget(0, 3)
        self.growing.setHorizontalHeaderLabels(["Growing", "Δ", "Project"])
        self.growing.horizontalHeader().setStretchLastSection(True)
        root.addWidget(card(self.growing, title="Recently growing"))
        self.note = muted("")
        root.addWidget(self.note)

    def apply_state(self, state: HostState) -> None:
        store = state.storage
        if store is None:
            return
        sys_m = next((m for m in store.mounts if m.target in {"/", "/home"}), None)
        if sys_m and sys_m.total_b:
            pct = 100.0 * sys_m.used_b / sys_m.total_b
            self.root_kpi.set_value(f"{pct:.0f}%", f"{fmt_bytes(sys_m.used_b)} / {fmt_bytes(sys_m.total_b)}  {sys_m.fstype}")
        vault = next((m for m in store.mounts if "Vault" in m.target or m.removable), None)
        if vault and vault.total_b:
            pct = 100.0 * vault.used_b / vault.total_b
            self.vault.set_value(f"{pct:.0f}%", f"{vault.target}  {fmt_bytes(vault.used_b)} / {fmt_bytes(vault.total_b)}")
        else:
            self.vault.set_value("Unmounted", "No removable filesystem right now")
        if store.scanning:
            self.scan.set_value("Scanning…", "du in background")
        elif store.scanned_at:
            self.scan.set_value(datetime.fromtimestamp(store.scanned_at).strftime("%H:%M:%S"), "background du")
        else:
            self.scan.set_value("Never", "Click refresh")

        self.mounts.setRowCount(len(store.mounts))
        for i, m in enumerate(store.mounts):
            values = [
                m.target,
                m.fstype,
                fmt_bytes(m.used_b),
                fmt_bytes(m.free_b),
                fmt_bytes(m.total_b),
                "yes" if m.removable else "",
            ]
            for c, val in enumerate(values):
                self.mounts.setItem(i, c, QTableWidgetItem(val))

        self.largest.setRowCount(len(store.largest))
        for i, row in enumerate(store.largest):
            delta = fmt_bytes(row.delta_b) if row.delta_b is not None else "—"
            if row.delta_b and row.delta_b > 0:
                delta = "+" + delta
            for c, val in enumerate((row.path, fmt_bytes(row.bytes), delta, row.project or "")):
                self.largest.setItem(i, c, QTableWidgetItem(val))

        self.growing.setRowCount(len(store.growing))
        for i, row in enumerate(store.growing):
            for c, val in enumerate((row.path, "+" + fmt_bytes(row.delta_b or 0), row.project or "")):
                self.growing.setItem(i, c, QTableWidgetItem(val))

        bits = []
        if store.nvme_model:
            bits.append(f"NVMe {store.nvme_model} fw {store.nvme_fw or '?'}")
        if store.smart:
            bits.append(store.smart)
        if store.note:
            bits.append(store.note)
        unmounted = [b.name for b in store.blocks if b.hotplug]
        if unmounted:
            bits.append("Block devices: " + ", ".join(unmounted))
        self.note.setText("  ·  ".join(bits))
