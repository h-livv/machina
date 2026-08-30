from __future__ import annotations

from dataclasses import asdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from machina.gpu_layers import remembered_gpu_layers
from machina.model_params import ModelParams, from_show, history_enabled
from machina.models import is_freetoken_source, is_llama_source
from machina.state import HostState
from machina.ui.pages import Page
from machina.ui.widgets import muted


def _combo_label(name: str, source: str) -> str:
    if is_llama_source(source):
        return f"{name}  ·  llama.cpp"
    if is_freetoken_source(source):
        return f"{name}  ·  freetoken"
    return name


def _norm_source(source: str | None) -> str:
    if source == "disk":
        return "ollama"
    return source or "ollama"


class ParametersPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: HostState | None = None
        self._entries: list[tuple[str, str]] = []
        self._resident: tuple[str, str] | None = None
        self._hydrated = False
        self._gpu_refresh = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        title = QLabel("Model parameters")
        title.setObjectName("section")
        root.addWidget(title)

        panel = QFrame()
        panel.setObjectName("card")
        panel_l = QVBoxLayout(panel)
        panel_l.setContentsMargins(14, 12, 14, 12)
        panel_l.setSpacing(8)

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_index_changed)
        panel_l.addWidget(self.combo)
        self.status = muted("Select a model, or load one into VRAM.")
        panel_l.addWidget(self.status)

        self.num_predict = QSpinBox()
        self.num_predict.setRange(-1, 131072)
        self.num_predict.setSpecialValueText("infinite")
        self.top_k = QSpinBox()
        self.top_k.setRange(0, 200)
        self.top_p = QDoubleSpinBox()
        self.top_p.setRange(0.0, 1.0)
        self.top_p.setSingleStep(0.05)
        self.top_p.setDecimals(2)
        self.min_p = QDoubleSpinBox()
        self.min_p.setRange(0.0, 1.0)
        self.min_p.setSingleStep(0.05)
        self.min_p.setDecimals(2)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.05)
        self.temperature.setDecimals(2)
        self.num_ctx = QSpinBox()
        self.num_ctx.setRange(256, 262144)
        self.num_ctx.setSingleStep(256)
        self.num_gpu = QSpinBox()
        self.num_gpu.setRange(-1, 128)
        self.num_gpu.setSpecialValueText("auto")

        form = QGridLayout()
        form.setContentsMargins(0, 4, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        fields = (
            ("num_predict", self.num_predict),
            ("top_k", self.top_k),
            ("top_p", self.top_p),
            ("min_p", self.min_p),
            ("temperature", self.temperature),
            ("num_ctx", self.num_ctx),
            ("num_gpu", self.num_gpu),
        )
        for i, (label, widget) in enumerate(fields):
            row, col = divmod(i, 4)
            caption = QLabel(label)
            caption.setObjectName("muted")
            form.addWidget(caption, row * 2, col)
            form.addWidget(widget, row * 2 + 1, col)
        panel_l.addLayout(form)

        toggles = QHBoxLayout()
        toggles.setContentsMargins(0, 0, 0, 0)
        self.think = QCheckBox("Think")
        self.history = QCheckBox("History")
        self.history.setChecked(history_enabled())
        toggles.addWidget(self.think)
        toggles.addWidget(self.history)
        toggles.addStretch()
        panel_l.addLayout(toggles)

        apply_btn = QPushButton("Apply to runner")
        apply_btn.setObjectName("accent")
        apply_btn.clicked.connect(lambda: self._submit(write=False))
        write_btn = QPushButton("Save into model")
        write_btn.clicked.connect(lambda: self._submit(write=True))
        max_gpu = QPushButton("Max GPU layers")
        max_gpu.setToolTip("Uses the saved layer count after the first search. Shift+click to measure again.")
        max_gpu.clicked.connect(self._load_max_gpu)
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 4, 0, 0)
        btns.addWidget(apply_btn)
        btns.addWidget(write_btn)
        btns.addWidget(max_gpu)
        btns.addStretch()
        panel_l.addLayout(btns)

        root.addWidget(panel)
        root.addStretch()
        self._apply_defaults(ModelParams())

    def _current(self) -> tuple[str, str]:
        data = self.combo.currentData()
        if isinstance(data, (tuple, list)) and len(data) == 2:
            return str(data[0]), str(data[1])
        name = self.combo.currentText().strip()
        return name, "ollama"

    def apply_state(self, state: HostState) -> None:
        self._state = state
        hub = state.models
        if hub is None:
            return
        entries: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for model in list(hub.loaded) + list(hub.models):
            name = (model.name or "").strip()
            if not name:
                continue
            if is_freetoken_source(model.source):
                continue
            key = (name, _norm_source(model.source))
            if key in seen:
                continue
            seen.add(key)
            entries.append(key)
        resident: tuple[str, str] | None = None
        if hub.loaded:
            first = next((m for m in hub.loaded if not is_freetoken_source(m.source)), hub.loaded[0])
            if is_freetoken_source(first.source):
                resident = None
            else:
                resident = (first.name, _norm_source(first.source))
        self._set_status(resident)
        if self._gpu_refresh:
            self._sync_gpu_spin()
        prev = self._current()
        entries_changed = entries != self._entries
        want = resident if resident and resident in entries else None
        if not entries_changed and resident == self._resident and (want is None or prev == want):
            return
        self._entries = entries
        self._resident = resident
        self.combo.blockSignals(True)
        if entries_changed:
            self.combo.clear()
            for item_name, item_source in entries:
                self.combo.addItem(_combo_label(item_name, item_source), (item_name, item_source))
        target = want or (prev if prev in entries else None)
        if target is not None:
            self.combo.setCurrentIndex(entries.index(target))
        self.combo.blockSignals(False)
        current = self._current()
        if not current[0]:
            return
        if not self._hydrated or current != prev:
            self._fill(*current)
            self._hydrated = True

    def _set_status(self, resident: tuple[str, str] | None) -> None:
        name, source = self._current()
        think = "think on" if self.think.isChecked() else "think off"
        if resident:
            shown = resident[0].split("/")[-1]
            kind = "llama.cpp" if is_llama_source(resident[1]) else "ollama"
            self.status.setText(f"In VRAM: {shown}  ·  {kind}  ·  {think}")
        elif name:
            kind = "llama.cpp" if is_llama_source(source) else "ollama"
            self.status.setText(f"{name}  ·  {kind}  ·  not in VRAM  ·  {think}")
        else:
            self.status.setText("Select a model, or load one into VRAM.")

    def _sync_gpu_spin(self) -> None:
        name, source = self._current()
        if not name or self.num_gpu.hasFocus():
            return
        cache_source = "llama.cpp" if is_llama_source(source) else "ollama"
        cached = remembered_gpu_layers(cache_source, name)
        if not cached:
            return
        self.num_gpu.setValue(cached[0])
        self._gpu_refresh = False

    def _on_index_changed(self, _index: int) -> None:
        name, source = self._current()
        if name:
            self._fill(name, source)

    def _apply_defaults(self, params: ModelParams) -> None:
        self.num_predict.setValue(params.num_predict if params.num_predict is not None else -1)
        self.top_k.setValue(params.top_k if params.top_k is not None else 40)
        self.top_p.setValue(params.top_p if params.top_p is not None else 0.9)
        self.min_p.setValue(params.min_p if params.min_p is not None else 0.0)
        self.temperature.setValue(params.temperature if params.temperature is not None else 0.8)
        self.num_ctx.setValue(params.num_ctx if params.num_ctx is not None else 4096)
        gpu = params.num_gpu if params.num_gpu is not None else -1
        self.num_gpu.setValue(gpu)
        self.think.setChecked(bool(params.think) if params.think is not None else True)

    def _fill(self, name: str, source: str = "ollama") -> None:
        params = from_show(name, source)
        if params.num_gpu is None:
            cache_source = "llama.cpp" if is_llama_source(source) else "ollama"
            cached = remembered_gpu_layers(cache_source, name)
            if cached:
                params.num_gpu = cached[0]
        self._apply_defaults(params)
        self.history.setChecked(history_enabled())
        self._set_status(self._resident)

    def _collect(self) -> ModelParams:
        gpu = self.num_gpu.value()
        return ModelParams(
            num_predict=self.num_predict.value(),
            top_k=self.top_k.value(),
            top_p=float(self.top_p.value()),
            min_p=float(self.min_p.value()),
            num_ctx=self.num_ctx.value(),
            temperature=float(self.temperature.value()),
            num_gpu=None if gpu < 0 else gpu,
            think=self.think.isChecked(),
        )

    def _submit(self, *, write: bool) -> None:
        name, source = self._current()
        if not name:
            return
        kind = "model.write_params" if write else "model.apply_params"
        self.request_runtime.emit(
            kind,
            {
                "name": name,
                "source": source,
                "history": self.history.isChecked(),
                "params": asdict(self._collect()),
            },
        )

    def _load_max_gpu(self) -> None:
        name, source = self._current()
        if not name and self._resident:
            name, source = self._resident
        if not name:
            return
        force = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        cache_source = "llama.cpp" if is_llama_source(source) else "ollama"
        reuse = (not force) and remembered_gpu_layers(cache_source, name) is not None
        self._gpu_refresh = True
        self.request_runtime.emit(
            "model.load_max_gpu",
            {"name": name, "source": source, "force": force, "reuse": reuse},
        )
