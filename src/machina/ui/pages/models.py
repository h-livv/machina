from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QGridLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from machina.paths import models_ui_path
from machina.state import HostState
from machina.ui.pages import Page
from machina.ui.widgets import Kpi, card, muted
from machina.util import fmt_bytes

_HELP = (
    "Ollama on this machine stores weights on Vault (`OLLAMA_MODELS`). "
    "Machina starts `ollama serve` as you — not the system unit, which runs as user ollama and cannot see Vault. "
    "llama.cpp is shown when `llama serve` is up. "
    "FreeToken: Start FreeToken UI launches `~/opt/freetoken-desktop*.appimage`; unload stops the engine via the desktop daemon. "
    "Sampling, think, and history are on the Parameters tab (`/set` / llama.cpp flags), including Max GPU layers — not FreeToken. "
    "Unload from VRAM drops the resident runner (Ollama, llama.cpp, or FreeToken). "
    "tok/s is the last generation rate from `ollama run` (or llama-server) in this machine's serve log — prompt in your terminal, Machina only reads the timing."
)

_LOADED_SIDES = (64, 88, 64, 64, 72)
_LIBRARY_SIDES = (64, 72, 64)


def _tune_table(table: QTableWidget, side_widths: tuple[int, ...]) -> None:
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setTextElideMode(Qt.TextElideMode.ElideNone)
    table.setWordWrap(False)
    policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    policy.setHorizontalStretch(1)
    table.setSizePolicy(policy)
    table.setMinimumWidth(0)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(26)
    header = table.horizontalHeader()
    header.setMinimumSectionSize(48)
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for i, width in enumerate(side_widths, start=1):
        header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(i, width)
    header.setToolTip("Drag a column edge to resize. The name column keeps the leftover width.")


def _cell(text: str, *, tip: str | None = None) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if tip:
        item.setToolTip(tip)
    return item


def _read_ui() -> dict:
    path = models_ui_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _apply_side_widths(table: QTableWidget, widths: list) -> None:
    header = table.horizontalHeader()
    header.blockSignals(True)
    for i, raw in enumerate(widths):
        if i == 0 or i >= table.columnCount():
            continue
        try:
            width = int(raw)
        except (TypeError, ValueError):
            continue
        if width >= header.minimumSectionSize():
            table.setColumnWidth(i, width)
    header.blockSignals(False)


class ModelsPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: HostState | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        title = QLabel("Model telemetry")
        title.setObjectName("section")
        root.addWidget(title)
        blurb = muted(
            "Vault Ollama, llama.cpp, and FreeToken. Parameters tab for /set. Unload from VRAM frees the engine."
        )
        blurb.setWordWrap(True)
        blurb.setToolTip(_HELP)
        blurb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        root.addWidget(blurb)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.kpi_ollama = Kpi("Ollama")
        self.kpi_loaded = Kpi("Loaded")
        self.kpi_vram = Kpi("Model VRAM")
        self.kpi_toks = Kpi("tok/s")
        self.kpi_llama = Kpi("llama.cpp")
        self.kpi_freetoken = Kpi("FreeToken")
        for i, w in enumerate(
            (self.kpi_ollama, self.kpi_loaded, self.kpi_vram, self.kpi_toks, self.kpi_llama, self.kpi_freetoken)
        ):
            w.layout().setContentsMargins(10, 8, 10, 8)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            grid.addWidget(w, 0, i)
        root.addLayout(grid)

        btns = QGridLayout()
        btns.setSpacing(8)
        start = QPushButton("Start Ollama")
        start.setObjectName("accent")
        start.clicked.connect(lambda: self.request_runtime.emit("model.start_ollama", {}))
        stop = QPushButton("Stop Ollama")
        stop.setObjectName("danger")
        stop.clicked.connect(lambda: self.request_runtime.emit("model.stop_ollama", {}))
        start_l = QPushButton("Start llama")
        start_l.clicked.connect(lambda: self.request_runtime.emit("model.start_llama", {}))
        stop_l = QPushButton("Stop llama")
        stop_l.setObjectName("danger")
        stop_l.clicked.connect(lambda: self.request_runtime.emit("model.stop_llama", {}))
        start_ft = QPushButton("Start FreeToken UI")
        start_ft.clicked.connect(lambda: self.request_runtime.emit("model.start_freetoken", {}))
        unload_vram = QPushButton("Unload from VRAM")
        unload_vram.setObjectName("danger")
        unload_vram.setToolTip("Unload the model currently occupying VRAM. No row selection needed.")
        unload_vram.clicked.connect(self._unload_resident)
        for col, pair in enumerate(((start, stop), (start_l, stop_l), (start_ft, unload_vram))):
            for row, b in enumerate(pair):
                b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btns.addWidget(b, row, col)
        root.addLayout(btns)

        self.loaded = QTableWidget(0, 6)
        self.loaded.setHorizontalHeaderLabels(
            ["Loaded model", "Size", "Processor", "Context", "VRAM", "Expires"]
        )
        _tune_table(self.loaded, _LOADED_SIDES)
        unload = QPushButton("Unload selected")
        unload.setObjectName("danger")
        unload.clicked.connect(self._unload)

        self.library = QTableWidget(0, 4)
        self.library.setHorizontalHeaderLabels(["Model", "Size", "Family", "Source"])
        _tune_table(self.library, _LIBRARY_SIDES)
        load = QPushButton("Load selected into VRAM")
        load.clicked.connect(self._load)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(8)
        self.split.addWidget(card(self.loaded, unload, title="Resident models", expand=True, compact=True))
        self.split.addWidget(card(self.library, load, title="Model library", expand=True, compact=True))
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 2)
        self.split.setToolTip("Drag this divider to give the library more room for names.")
        root.addWidget(self.split, 1)
        self.note = muted("")
        self.note.setWordWrap(True)
        self.note.setMaximumHeight(36)
        self.note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.note)

        self._ui_ready = False
        self._save_ui_timer = QTimer(self)
        self._save_ui_timer.setSingleShot(True)
        self._save_ui_timer.setInterval(400)
        self._save_ui_timer.timeout.connect(self._save_ui)
        self.loaded.horizontalHeader().sectionResized.connect(self._schedule_save_ui)
        self.library.horizontalHeader().sectionResized.connect(self._schedule_save_ui)
        self.split.splitterMoved.connect(self._schedule_save_ui)
        QTimer.singleShot(0, self._restore_ui)

    def apply_state(self, state: HostState) -> None:
        self._state = state
        hub = state.models
        if hub is None:
            return
        if not hub.ollama_installed:
            self.kpi_ollama.set_value("Missing", "not on PATH")
            self.kpi_ollama.setToolTip("")
        elif hub.ollama_running:
            self.kpi_ollama.set_value("Serving", hub.ollama_version or "API up")
            self.kpi_ollama.setToolTip(hub.ollama_version or "")
        else:
            self.kpi_ollama.set_value("Stopped", "API down")
            self.kpi_ollama.setToolTip(hub.ollama_error or "Ollama API is not reachable")
        self.kpi_loaded.set_value(str(len(hub.loaded)), "resident")
        vram = sum(m.size_vram_b or 0 for m in hub.loaded)
        self.kpi_vram.set_value(fmt_bytes(vram) if vram else "—", "from ollama ps")
        if hub.gen_tok_s is not None:
            meta_bits = ["last gen"]
            if hub.gen_tokens:
                meta_bits.append(f"{hub.gen_tokens} tok")
            if hub.prompt_tok_s is not None:
                meta_bits.append(f"{hub.prompt_tok_s:.0f} prefill")
            self.kpi_toks.set_value(f"{hub.gen_tok_s:.1f}", " · ".join(meta_bits))
        else:
            self.kpi_toks.set_value("—", "from terminal")
        llama_n = len(hub.llama_models)
        if hub.llama_running:
            llama_meta = f"{llama_n} listed" if llama_n else "API up"
        elif llama_n:
            llama_meta = f"{llama_n} on disk"
        else:
            llama_meta = "stopped"
        self.kpi_llama.set_value("Serving" if hub.llama_running else "Stopped", llama_meta)
        self.kpi_llama.setToolTip("\n".join(hub.llama_models[:40]) if hub.llama_models else (hub.llama_models_dir or ""))
        if hub.freetoken_engine:
            self.kpi_freetoken.set_value("Engine", hub.freetoken_model or hub.freetoken_version or "running")
        elif hub.freetoken_ui:
            self.kpi_freetoken.set_value("UI", hub.freetoken_version or "desktop")
        elif hub.freetoken_running:
            last = f"last {hub.freetoken_model}" if hub.freetoken_model else "engine idle"
            self.kpi_freetoken.set_value("Daemon", last)
        elif hub.freetoken_installed:
            self.kpi_freetoken.set_value("Stopped", "AppImage on disk")
        else:
            self.kpi_freetoken.set_value("Missing", "no AppImage")
        self.kpi_freetoken.setToolTip(hub.freetoken_error or hub.freetoken_model or "")
        self.loaded.setRowCount(len(hub.loaded))
        for i, model in enumerate(hub.loaded):
            vals = (
                model.name,
                fmt_bytes(model.size_b),
                model.processor or "—",
                str(model.context_length) if model.context_length is not None else "—",
                fmt_bytes(model.size_vram_b),
                model.expires or "—",
            )
            for c, val in enumerate(vals):
                self.loaded.setItem(i, c, _cell(val, tip=model.name if c == 0 else None))
        self.library.setRowCount(len(hub.models))
        for i, model in enumerate(hub.models):
            vals = (model.name, fmt_bytes(model.size_b), model.family or "—", model.source)
            for c, val in enumerate(vals):
                self.library.setItem(i, c, _cell(val, tip=model.name if c == 0 else None))
        bits = [hub.note] if hub.note else []
        if hub.models_dir:
            bits.append(f"OLLAMA_MODELS={hub.models_dir}")
        if hub.llama_models_dir:
            bits.append(f"LLAMA_ARG_MODELS_DIR={hub.llama_models_dir}")
        if hub.freetoken_models_dir:
            bits.append(f"FreeToken={hub.freetoken_models_dir}")
        if hub.freetoken_version:
            bits.append(f"ft {hub.freetoken_version}")
        needles = ("ollama", "llama", "freetoken")
        gpu_procs = [
            p
            for p in state.processes
            if p.gpu_vram_mib and any(n in (p.name + p.cmdline).lower() for n in needles)
        ]
        if gpu_procs:
            bits.append(f"GPU process: {gpu_procs[0].name} pid {gpu_procs[0].pid}  {gpu_procs[0].gpu_vram_mib:.0f} MiB")
        self.note.setText("  ·  ".join(bits))

    def _schedule_save_ui(self, *_args: object) -> None:
        if self._ui_ready:
            self._save_ui_timer.start()

    def _restore_ui(self) -> None:
        data = _read_ui()
        loaded = data.get("loaded")
        library = data.get("library")
        splitter = data.get("splitter")
        if isinstance(loaded, list):
            _apply_side_widths(self.loaded, loaded)
        if isinstance(library, list):
            _apply_side_widths(self.library, library)
        if isinstance(splitter, list) and len(splitter) >= 2:
            try:
                sizes = [int(splitter[0]), int(splitter[1])]
            except (TypeError, ValueError):
                sizes = []
            if sizes and all(n > 0 for n in sizes):
                self.split.setSizes(sizes)
        self._ui_ready = True

    def _save_ui(self) -> None:
        payload = {
            "splitter": self.split.sizes(),
            "loaded": [self.loaded.columnWidth(i) for i in range(self.loaded.columnCount())],
            "library": [self.library.columnWidth(i) for i in range(self.library.columnCount())],
        }
        path = models_ui_path()
        try:
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError:
            return

    def _selected_name(self, table: QTableWidget) -> str | None:
        items = table.selectedItems()
        if not items:
            return None
        item = table.item(items[0].row(), 0)
        return item.text() if item else None

    def _selected_library(self) -> tuple[str, str] | None:
        name = self._selected_name(self.library)
        if not name:
            return None
        row = self.library.selectedItems()[0].row()
        source_item = self.library.item(row, 3)
        source = source_item.text() if source_item else "ollama"
        return name, source

    def _selected_loaded(self) -> tuple[str, str] | None:
        name = self._selected_name(self.loaded)
        if not name:
            return None
        source = "ollama"
        if self._state and self._state.models:
            for model in self._state.models.loaded:
                if model.name == name:
                    source = model.source
                    break
        return name, source

    def _load(self) -> None:
        selected = self._selected_library()
        if selected:
            name, source = selected
            self.request_runtime.emit("model.load", {"name": name, "source": source})

    def _unload(self) -> None:
        selected = self._selected_loaded()
        if selected:
            name, source = selected
            self.request_runtime.emit("model.unload", {"name": name, "source": source})
            return
        loaded = self._state.models.loaded if self._state and self._state.models else []
        if len(loaded) == 1:
            self.request_runtime.emit(
                "model.unload", {"name": loaded[0].name, "source": loaded[0].source}
            )
            return
        if loaded:
            self.request_runtime.emit("model.unload_resident", {})

    def _unload_resident(self) -> None:
        self.request_runtime.emit("model.unload_resident", {})
