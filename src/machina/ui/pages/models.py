from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
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


class ModelsPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: HostState | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Model telemetry")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(
            muted(
                "Ollama on this machine stores weights on Vault (`OLLAMA_MODELS`). "
                "Machina starts `ollama serve` as you — not the system unit, which runs as user ollama and cannot see Vault. "
                "llama.cpp is shown when `llama serve` is up. "
                "Sampling, think, and history are on the Parameters tab (`/set` / llama.cpp flags), including Max GPU layers. "
                "Unload from VRAM drops the resident runner. "
                "tok/s is the last generation rate from `ollama run` (or llama-server) in this machine's serve log — prompt in your terminal, Machina only reads the timing."
            )
        )

        grid = QGridLayout()
        self.kpi_ollama = Kpi("Ollama")
        self.kpi_loaded = Kpi("Loaded")
        self.kpi_vram = Kpi("Model VRAM")
        self.kpi_toks = Kpi("tok/s")
        self.kpi_llama = Kpi("llama.cpp")
        for i, w in enumerate((self.kpi_ollama, self.kpi_loaded, self.kpi_vram, self.kpi_toks, self.kpi_llama)):
            grid.addWidget(w, 0, i)
        root.addLayout(grid)

        btns = QHBoxLayout()
        start = QPushButton("Start Ollama")
        start.setObjectName("accent")
        start.clicked.connect(lambda: self.request_runtime.emit("model.start_ollama", {}))
        stop = QPushButton("Stop Ollama")
        stop.setObjectName("danger")
        stop.clicked.connect(lambda: self.request_runtime.emit("model.stop_ollama", {}))
        start_l = QPushButton("Start llama serve")
        start_l.clicked.connect(lambda: self.request_runtime.emit("model.start_llama", {}))
        stop_l = QPushButton("Stop llama serve")
        stop_l.setObjectName("danger")
        stop_l.clicked.connect(lambda: self.request_runtime.emit("model.stop_llama", {}))
        unload_vram = QPushButton("Unload from VRAM")
        unload_vram.setObjectName("danger")
        unload_vram.setToolTip("Unload the model currently occupying VRAM. No row selection needed.")
        unload_vram.clicked.connect(self._unload_resident)
        for b in (start, stop, start_l, stop_l, unload_vram):
            btns.addWidget(b)
        btns.addStretch()
        root.addLayout(btns)

        self.loaded = QTableWidget(0, 6)
        self.loaded.setHorizontalHeaderLabels(
            ["Loaded model", "Size", "Processor", "Context", "VRAM", "Expires"]
        )
        self.loaded.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.loaded.horizontalHeader().setStretchLastSection(True)
        unload = QPushButton("Unload selected")
        unload.setObjectName("danger")
        unload.clicked.connect(self._unload)
        root.addWidget(card(self.loaded, unload, title="Resident models (ollama ps)"))

        self.library = QTableWidget(0, 4)
        self.library.setHorizontalHeaderLabels(["Model", "Size", "Family", "Source"])
        self.library.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.library.horizontalHeader().setStretchLastSection(True)
        load = QPushButton("Load selected into VRAM")
        load.clicked.connect(self._load)
        root.addWidget(card(self.library, load, title="Model library"))
        self.note = muted("")
        root.addWidget(self.note)

    def apply_state(self, state: HostState) -> None:
        self._state = state
        hub = state.models
        if hub is None:
            return
        if not hub.ollama_installed:
            self.kpi_ollama.set_value("Missing", "not on PATH")
        elif hub.ollama_running:
            self.kpi_ollama.set_value("Serving", hub.ollama_version or "API up")
        else:
            self.kpi_ollama.set_value("Stopped", hub.ollama_error or "API down")
        self.kpi_loaded.set_value(str(len(hub.loaded)), "resident")
        vram = sum(m.size_vram_b or 0 for m in hub.loaded)
        self.kpi_vram.set_value(fmt_bytes(vram) if vram else "—", "size_vram from Ollama")
        if hub.gen_tok_s is not None:
            meta_bits = ["last gen"]
            if hub.gen_tokens:
                meta_bits.append(f"{hub.gen_tokens} tok")
            if hub.prompt_tok_s is not None:
                meta_bits.append(f"{hub.prompt_tok_s:.0f} prefill")
            self.kpi_toks.set_value(f"{hub.gen_tok_s:.1f}", " · ".join(meta_bits))
        else:
            self.kpi_toks.set_value("—", "from terminal")
        self.kpi_llama.set_value("Serving" if hub.llama_running else "Stopped", ", ".join(hub.llama_models) or hub.llama_models_dir or "")
        self.loaded.setRowCount(len(hub.loaded))
        for i, model in enumerate(hub.loaded):
            for c, val in enumerate(
                (
                    model.name,
                    fmt_bytes(model.size_b),
                    model.processor or "—",
                    str(model.context_length) if model.context_length is not None else "—",
                    fmt_bytes(model.size_vram_b),
                    model.expires or "—",
                )
            ):
                self.loaded.setItem(i, c, QTableWidgetItem(val))
        self.library.setRowCount(len(hub.models))
        for i, model in enumerate(hub.models):
            for c, val in enumerate((model.name, fmt_bytes(model.size_b), model.family or "—", model.source)):
                self.library.setItem(i, c, QTableWidgetItem(val))
        bits = [hub.note] if hub.note else []
        if hub.models_dir:
            bits.append(f"OLLAMA_MODELS={hub.models_dir}")
        if hub.llama_models_dir:
            bits.append(f"LLAMA_ARG_MODELS_DIR={hub.llama_models_dir}")
        gpu_procs = [p for p in state.processes if p.gpu_vram_mib and "ollama" in (p.name + p.cmdline).lower()]
        if gpu_procs:
            bits.append(f"GPU process: {gpu_procs[0].name} pid {gpu_procs[0].pid}  {gpu_procs[0].gpu_vram_mib:.0f} MiB")
        self.note.setText("  ·  ".join(bits))

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
