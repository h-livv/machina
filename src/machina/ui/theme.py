from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BG = "#0B0E13"
BG_ELEVATED = "#10151C"
BG_CARD = "#161C25"
BG_CARD_HOVER = "#1C2430"
BG_INPUT = "#0F141B"
BORDER = "#2A3340"
BORDER_STRONG = "#3A4656"
TEXT = "#E8EEF6"
TEXT_DIM = "#9AA8B7"
TEXT_MUTED = "#6E7C8C"
ACCENT = "#2EE6A6"
ACCENT_DIM = "#1A8F6C"
WARN = "#F5C14A"
DANGER = "#FF6B6B"
INFO = "#6EA8FF"
COOL = "#7AD7FF"
PERF = "#FF7A9A"

QSS = f"""
QMainWindow, QWidget#root {{
    background: {BG};
    color: {TEXT};
    font-size: 13px;
}}
QWidget#sidebar {{
    background: {BG_ELEVATED};
    border-right: 1px solid {BORDER};
}}
QLabel#brand {{
    color: {ACCENT};
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#brandSub {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QLabel#section {{
    color: {TEXT};
    font-size: 18px;
    font-weight: 600;
}}
QLabel#muted, QLabel[muted="true"] {{
    color: {TEXT_DIM};
}}
QLabel#kpiValue {{
    font-size: 28px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#kpiUnit {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
QPushButton {{
    background: {BG_CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 14px;
}}
QPushButton:hover {{
    background: {BG_CARD_HOVER};
    border-color: {BORDER_STRONG};
}}
QPushButton:pressed {{
    background: #121820;
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    background: #12171e;
}}
QPushButton#accent {{
    background: {ACCENT};
    color: #06281d;
    border: none;
    font-weight: 600;
}}
QPushButton#accent:hover {{
    background: #55f0bc;
}}
QPushButton#danger {{
    background: #3a1a1e;
    color: {DANGER};
    border: 1px solid #5a2a32;
}}
QPushButton#nav {{
    text-align: left;
    padding: 10px 14px;
    border: 1px solid transparent;
    background: transparent;
    border-radius: 10px;
    color: {TEXT_DIM};
    font-size: 13px;
}}
QPushButton#nav:hover {{
    background: {BG_CARD};
    color: {TEXT};
}}
QPushButton#nav:checked {{
    background: {BG_CARD};
    color: {ACCENT};
    border: 1px solid {BORDER};
    font-weight: 600;
}}
QFrame#card {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#modeCard {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
QFrame#modeCard[selected="true"] {{
    border: 1px solid {ACCENT};
    background: #12241f;
}}
QFrame#banner {{
    background: #2a2314;
    border: 1px solid #5a4a22;
    border-radius: 12px;
}}
QFrame#banner[level="critical"] {{
    background: #2a1418;
    border: 1px solid #5a2a32;
}}
QFrame#banner[level="ok"] {{
    background: #12241f;
    border: 1px solid #1A8F6C;
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: {BG_INPUT};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: {ACCENT};
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_DIM};
    border-radius: 3px;
}}
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    color: {TEXT};
    min-height: 28px;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QCheckBox {{
    color: {TEXT};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER_STRONG};
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 4px;
    min-height: 32px;
}}
QTableWidget {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
    gridline-color: {BORDER};
    color: {TEXT};
}}
QHeaderView::section {{
    background: {BG_ELEVATED};
    color: {TEXT_DIM};
    border: none;
    padding: 8px;
}}
QProgressBar {{
    background: {BG_INPUT};
    border: none;
    border-radius: 5px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 5px;
}}
QLabel#navSection {{
    color: {TEXT_MUTED};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
    padding: 14px 8px 4px 8px;
}}
QLabel#statusOk {{
    color: {ACCENT};
    font-size: 22px;
    font-weight: 700;
}}
QLabel#statusWarn {{
    color: {WARN};
    font-size: 22px;
    font-weight: 700;
}}
QLabel#statusBad {{
    color: {DANGER};
    font-size: 22px;
    font-weight: 700;
}}
QLabel#statusUnknown {{
    color: {TEXT_DIM};
    font-size: 22px;
    font-weight: 700;
}}
QPlainTextEdit, QTextEdit {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px;
    font-family: "JetBrains Mono", "Noto Sans Mono", monospace;
    font-size: 12px;
}}
QTreeWidget {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
    color: {TEXT};
    alternate-background-color: {BG_ELEVATED};
}}
QTreeWidget::item {{
    padding: 4px;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {BG_CARD};
}}
QTabBar::tab {{
    background: {BG_ELEVATED};
    color: {TEXT_DIM};
    padding: 8px 14px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
}}
QTabBar::tab:selected {{
    background: {BG_CARD};
    color: {ACCENT};
}}
QSplitter::handle {{
    background: {BORDER};
    width: 2px;
}}
QListWidget {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
    color: {TEXT};
}}
QListWidget::item {{
    padding: 8px;
}}
QListWidget::item:selected {{
    background: {BG_CARD_HOVER};
    color: {ACCENT};
}}
QToolTip {{
    background: {BG_ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 6px 8px;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont("Noto Sans", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(BG_INPUT))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_CARD))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(BG_CARD))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#06281d"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_ELEVATED))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
