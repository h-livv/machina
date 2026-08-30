from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout

from machina.guardrails import PROFILE_BUNDLES
from machina.telemetry import Snapshot
from machina.ui.pages import Page
from machina.ui.widgets import ModeCard, card, muted


class PerformancePage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Performance")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(
            muted(
                "These cards write HP’s ACPI platform profile plus the matching Intel P-state "
                "governor and energy preference. That is the Linux equivalent of Omen’s performance slider."
            )
        )

        grid = QGridLayout()
        self.cards: dict[str, ModeCard] = {}
        for i, (key, spec) in enumerate(PROFILE_BUNDLES.items()):
            widget = ModeCard(key, spec["title"], spec["blurb"])
            widget.clicked.connect(self._apply_bundle)
            self.cards[key] = widget
            grid.addWidget(widget, i // 2, i % 2)
        root.addLayout(grid)

        self.status = muted("Current profile: —")
        root.addWidget(self.status)
        root.addWidget(
            card(
                muted(
                    "Cool / Quiet / Balanced / Performance are firmware policies. They change boost behavior, "
                    "embedded-controller fan targets, and power. Machina also syncs CPU EPP so the OS does not "
                    "fight the firmware. GPU power and RAPL stay on the Graphics and Power pages so a mode click "
                    "cannot slam the GPU to 75 W by accident."
                ),
                title="What this actually changes",
            )
        )
        root.addStretch()

    def _apply_bundle(self, key: str) -> None:
        spec = PROFILE_BUNDLES[key]
        self.request_actions.emit(list(spec["actions"]), f"performance:{key}")

    def apply_snapshot(self, snap: Snapshot) -> None:
        current = snap.profile.current or ""
        for key, widget in self.cards.items():
            widget.set_selected(key == current)
        bits = [
            f"HP profile: {current or 'unavailable'}",
            f"governor: {snap.cpu.governor or '—'}",
            f"EPP: {snap.cpu.epp or '—'}",
            f"turbo: {'on' if snap.cpu.turbo_enabled else 'off' if snap.cpu.turbo_enabled is False else '—'}",
        ]
        if snap.battery.present and snap.battery.ac_online is False:
            bits.append("on battery — Performance will ask for extra confirmation")
        self.status.setText("  ·  ".join(bits))
