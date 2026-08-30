from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from machina.state import HostState
from machina.ui.pages import Page
from machina.ui.widgets import Kpi, card, muted
from machina.util import fmt_bytes


class NetworkPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Network")
        title.setObjectName("section")
        root.addWidget(title)
        root.addWidget(muted("Link state, Wi-Fi, traffic, and the ports that matter for models and dev servers."))

        grid = QGridLayout()
        self.uplink = Kpi("Default route")
        self.vpn = Kpi("VPN")
        self.flows = Kpi("TCP established")
        self.dl = Kpi("Downloads")
        for i, w in enumerate((self.uplink, self.vpn, self.flows, self.dl)):
            grid.addWidget(w, 0, i)
        root.addLayout(grid)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Iface", "Kind", "State", "Address", "SSID", "Rx", "Tx"])
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(card(self.table, title="Interfaces"))
        self.listen = muted("")
        root.addWidget(self.listen)

    def apply_state(self, state: HostState) -> None:
        net = state.network
        if net is None:
            return
        self.uplink.set_value(net.default_route or "—", "from /proc/net/route")
        self.vpn.set_value(net.vpn or "None", "tun/wg/nmcli")
        self.flows.set_value("—" if net.established is None else str(net.established), "ESTABLISHED on IPv4 TCP")
        self.dl.set_value(str(len(net.downloads)) if net.downloads else "None", ", ".join(net.downloads) or "no curl/wget/hf/ollama pull")
        self.table.setRowCount(len(net.ifaces))
        for i, iface in enumerate(net.ifaces):
            values = [
                iface.name,
                iface.kind,
                iface.state,
                iface.ipv4 or "—",
                iface.wifi_ssid or (f"sig {iface.wifi_signal}" if iface.wifi_signal else "—"),
                _rate(iface.rx_bps),
                _rate(iface.tx_bps),
            ]
            for c, val in enumerate(values):
                self.table.setItem(i, c, QTableWidgetItem(val))
        listen = ", ".join(net.listening) if net.listening else "no watched ports"
        self.listen.setText(f"Listening (dev/model ports): {listen}")


def _rate(bps: float | None) -> str:
    if bps is None:
        return "—"
    return fmt_bytes(bps) + "/s"
