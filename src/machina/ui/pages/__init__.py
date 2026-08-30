from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from machina.telemetry import Snapshot


class Page(QWidget):
    request_actions = Signal(list, str)
    request_runtime = Signal(str, dict)

    def apply_snapshot(self, snap: Snapshot) -> None:
        return

    def apply_state(self, state) -> None:  # noqa: ANN001
        self.apply_snapshot(state.snap)
