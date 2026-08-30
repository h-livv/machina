from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from machina.ui.theme import ACCENT, BG_CARD, BORDER, DANGER, TEXT, TEXT_DIM, TEXT_MUTED, WARN


def card(
    *widgets: QWidget,
    title: str | None = None,
    subtitle: str | None = None,
    expand: bool = False,
    compact: bool = False,
) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    if compact:
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
    else:
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
    if title:
        label = QLabel(title)
        label.setObjectName("section")
        label.setStyleSheet("font-size: 15px;")
        layout.addWidget(label)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        layout.addWidget(sub)
    for i, widget in enumerate(widgets):
        stretch = 1 if expand and i == 0 else 0
        layout.addWidget(widget, stretch)
    if expand:
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return frame


def muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


class CircularGauge(QWidget):
    def __init__(self, caption: str, unit: str = "°C", maximum: float = 100, parent=None) -> None:
        super().__init__(parent)
        self.caption = caption
        self.unit = unit
        self.maximum = maximum
        self.value: float | None = None
        self.warn_at = 80.0
        self.danger_at = 90.0
        self.setMinimumSize(140, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, value: float | None, maximum: float | None = None) -> None:
        changed = False
        if maximum and maximum != self.maximum:
            self.maximum = maximum
            changed = True
        if value != self.value:
            self.value = value
            changed = True
        if changed:
            self.update()

    def _color(self) -> QColor:
        if self.value is None:
            return QColor(TEXT_MUTED)
        if self.value >= self.danger_at:
            return QColor(DANGER)
        if self.value >= self.warn_at:
            return QColor(WARN)
        return QColor(ACCENT)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height() - 22)
        rect_x = (self.width() - side) / 2 + 10
        rect_y = 8
        rect_s = side - 20
        start = 225 * 16
        span = -270 * 16
        track = QPen(QColor(BORDER), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.drawArc(int(rect_x), int(rect_y), int(rect_s), int(rect_s), start, span)
        ratio = 0.0 if self.value is None else max(0.0, min(1.0, self.value / self.maximum))
        painter.setPen(QPen(self._color(), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(int(rect_x), int(rect_y), int(rect_s), int(rect_s), start, int(span * ratio))
        painter.setPen(QColor(TEXT))
        font = QFont(self.font())
        font.setPointSize(16)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        text = "—" if self.value is None else f"{self.value:.0f}"
        painter.drawText(
            int(rect_x),
            int(rect_y),
            int(rect_s),
            int(rect_s) - 8,
            Qt.AlignmentFlag.AlignCenter,
            text,
        )
        painter.setPen(QColor(TEXT_DIM))
        font.setPointSize(9)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(0, self.height() - 20, self.width(), 18, Qt.AlignmentFlag.AlignHCenter, f"{self.caption}  {self.unit}")


class Sparkline(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.values: list[float] = []
        self.setMinimumHeight(72)
        self.setMaximumHeight(96)

    def set_values(self, values: list[float]) -> None:
        trimmed = values[-180:]
        if trimmed == self.values:
            return
        self.values = trimmed
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(BG_CARD))
        if len(self.values) < 2:
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Collecting…")
            return
        lo = min(self.values)
        hi = max(self.values)
        if hi - lo < 1:
            hi = lo + 1
        w, h = self.width(), self.height()
        pad = 8
        path = QPainterPath()
        fill = QPainterPath()
        for i, value in enumerate(self.values):
            x = pad + (w - 2 * pad) * i / (len(self.values) - 1)
            y = pad + (h - 2 * pad) * (1 - (value - lo) / (hi - lo))
            if i == 0:
                path.moveTo(x, y)
                fill.moveTo(x, h - pad)
                fill.lineTo(x, y)
            else:
                path.lineTo(x, y)
                fill.lineTo(x, y)
        fill.lineTo(pad + (w - 2 * pad), h - pad)
        fill.closeSubpath()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(46, 230, 166, 70))
        grad.setColorAt(1, QColor(46, 230, 166, 0))
        painter.fillPath(fill, QBrush(grad))
        painter.setPen(QPen(QColor(ACCENT), 2))
        painter.drawPath(path)


class ModeCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, title: str, blurb: str, parent=None) -> None:
        super().__init__(parent)
        self.key = key
        self.setObjectName("modeCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.blurb_lbl = QLabel(blurb)
        self.blurb_lbl.setObjectName("muted")
        self.blurb_lbl.setWordWrap(True)
        self.badge = QLabel("")
        self.badge.setStyleSheet(f"color: {ACCENT}; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.blurb_lbl)
        layout.addStretch()
        layout.addWidget(self.badge)
        self.setMinimumHeight(150)
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        flag = "true" if selected else "false"
        if self.property("selected") == flag:
            return
        self.setProperty("selected", flag)
        self.badge.setText("ACTIVE" if selected else "")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class Kpi(QFrame):
    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        self.value_lbl = QLabel("—")
        self.value_lbl.setObjectName("kpiValue")
        self.value_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.meta = QLabel(label)
        self.meta.setObjectName("muted")
        self.meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.meta.setWordWrap(False)
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.meta)

    def set_value(self, value: str, meta: str | None = None) -> None:
        if self.value_lbl.text() != value:
            self.value_lbl.setText(value)
        if meta is not None and self.meta.text() != meta:
            self.meta.setText(meta)


class SliderRow(QWidget):
    valueCommitted = Signal(int)

    def __init__(self, label: str, minimum: int, maximum: int, suffix: str = "", parent=None) -> None:
        super().__init__(parent)
        self.suffix = suffix
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        self.caption = QLabel(label)
        self.readout = QLabel("—")
        self.readout.setStyleSheet("font-weight: 600;")
        head.addWidget(self.caption)
        head.addStretch()
        head.addWidget(self.readout)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.valueChanged.connect(self._preview)
        self.slider.sliderReleased.connect(self._commit)
        layout.addLayout(head)
        layout.addWidget(self.slider)
        self._live = True

    def _preview(self, value: int) -> None:
        self.readout.setText(f"{value}{self.suffix}")

    def _commit(self) -> None:
        self.valueCommitted.emit(self.slider.value())

    def set_value_silent(self, value: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(value))
        self.slider.blockSignals(False)
        self._preview(int(value))


class ConfirmDialog(QDialog):
    def __init__(self, title: str, summary: str, bullets: list[str], risk: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        head = QLabel(title)
        head.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(head)
        layout.addWidget(muted(summary))
        for bullet in bullets:
            row = QLabel(f"•  {bullet}")
            row.setWordWrap(True)
            layout.addWidget(row)
        self.ack = QCheckBox("I understand this can increase heat, noise, or wear.")
        if risk == "high":
            layout.addWidget(self.ack)
        else:
            self.ack.setChecked(True)
            self.ack.hide()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _try_accept(self) -> None:
        if not self.ack.isChecked():
            return
        self.accept()


class CoreBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cores: list[tuple[str, float]] = []
        self.setMinimumHeight(120)

    def set_cores(self, cores: list[tuple[str, float]]) -> None:
        if cores == self.cores:
            return
        self.cores = cores
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.cores:
            return
        n = len(self.cores)
        gap = 6
        bar_w = max(8, (self.width() - gap * (n + 1)) / n)
        for i, (label, pct) in enumerate(self.cores):
            x = gap + i * (bar_w + gap)
            h = self.height() - 22
            filled = h * max(0.0, min(1.0, pct / 100.0))
            painter.setBrush(QColor(BORDER))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(x), 0, int(bar_w), int(h), 4, 4)
            color = QColor(ACCENT)
            if pct > 85:
                color = QColor(DANGER)
            elif pct > 65:
                color = QColor(WARN)
            painter.setBrush(color)
            painter.drawRoundedRect(int(x), int(h - filled), int(bar_w), int(filled), 4, 4)
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(int(x - 4), int(h + 2), int(bar_w + 8), 18, Qt.AlignmentFlag.AlignHCenter, label)
