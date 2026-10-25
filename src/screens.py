"""
screens.py — tool screens for NetVizForx-CLI.

Each tool gets its own screen with a results table and log console.
All screens share the same layout: title bar, data table, log console, status bar.
"""

from __future__ import annotations

from queue import Empty, Queue
from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Label, RichLog

from src.workers import (
    BaseWorker, PingWorker, DnsWorker, PortScanWorker,
    WhoisWorker, GeoIpWorker, NetstatWorker,
)
from src.network import TracerouteWorker, Hop
from src.theme import PALETTE

# ---------------------------------------------------------------------------
# Shared CSS for all tool screens
# ---------------------------------------------------------------------------

TOOL_CSS = """
ToolScreen {
    background: #11111b;
}

#tool-title-bar {
    background: #1e1e2e;
    color: #89b4fa;
    text-align: center;
    height: 1;
    padding: 0 2;
}

#tool-data-pane {
    height: 1fr;
    border: solid #45475a;
    background: #181825;
}

#tool-data-label {
    background: #313244;
    color: #cba6f7;
    padding: 0 1;
    height: 1;
}

#tool-table {
    height: 1fr;
}

DataTable {
    background: #181825;
    color: #cdd6f4;
}

DataTable > .datatable--header {
    background: #313244;
    color: #cba6f7;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #45475a;
}

DataTable > .datatable--even-row {
    background: #1e1e2e;
}

#tool-log-pane {
    height: 10;
    border: solid #45475a;
    background: #11111b;
}

#tool-log-label {
    background: #313244;
    color: #a6e3a1;
    padding: 0 1;
    height: 1;
}

RichLog {
    background: #11111b;
    color: #cdd6f4;
    padding: 0 1;
}

#tool-status-bar {
    background: #1e1e2e;
    color: #6c7086;
    height: 1;
    padding: 0 2;
}
"""

# ---------------------------------------------------------------------------
# Base tool screen — shared layout + queue draining
# ---------------------------------------------------------------------------

from textual.screen import Screen


class ToolScreen(Screen):
    """Base screen for all networking tool screens."""

    CSS = TOOL_CSS

    BINDINGS = [
        Binding("escape", "back", "Back to Menu"),
        Binding("q", "back", "Back"),
        Binding("r", "restart", "Restart"),
    ]

    # Columns: (label, key, width)
    COLUMNS: list[tuple[str, str, int]] = []
    TITLE: str = "Tool"

    status_msg: reactive[str] = reactive("Initializing…")
    done: reactive[bool] = reactive(False)

    def __init__(self, target: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.target = target
        self._event_queue: Queue = Queue()
        self._worker: Optional[BaseWorker] = None
        self._poll_timer = None

    # -- Layout -------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Label(self.get_title(), id="tool-title-bar")
        with Vertical(id="tool-data-pane"):
            yield Label(self.get_data_label(), id="tool-data-label")
            yield DataTable(id="tool-table", cursor_type="row", zebra_stripes=True)
        with Vertical(id="tool-log-pane"):
            yield Label(" Log Console", id="tool-log-label")
            yield RichLog(id="tool-log-console", highlight=True, markup=True, wrap=True)
        yield Label("  ESC: Back to Menu  |  R: Restart  |  Q: Back", id="tool-status-bar")

    def get_title(self) -> str:
        return f"  NetVizForx-CLI  ──  {self.TITLE}  ──  target: {self.target}"

    def get_data_label(self) -> str:
        return f" {self.TITLE} Results"

    # -- Lifecycle ----------------------------------------------------

    def on_mount(self) -> None:
        self._setup_table()
        self._start_tool()
        self._poll_timer = self.set_interval(1 / 20, self._drain_queue)

    def _setup_table(self) -> None:
        table: DataTable = self.query_one("#tool-table", DataTable)
        table.clear(columns=True)
        for col_label, col_key, col_width in self.COLUMNS:
            table.add_column(col_label, key=col_key, width=col_width)

    def _start_tool(self) -> None:
        if self._worker and self._worker.is_alive():
            self._worker.stop()
        self._event_queue = Queue()
        self._worker = self.create_worker()
        if self._worker:
            self._worker.start()

    def create_worker(self) -> Optional[BaseWorker]:
        """Override in subclasses to create the specific worker."""
        return None

    # -- Queue draining -----------------------------------------------

    def _drain_queue(self) -> None:
        while True:
            try:
                kind, payload = self._event_queue.get_nowait()
            except Empty:
                break

            if kind == "row":
                self._handle_row(payload)
            elif kind == "hop":
                self._handle_hop(payload)
            elif kind == "log":
                self._handle_log(payload)
            elif kind == "done":
                self._handle_done(payload)
            elif kind == "error":
                self._handle_error(payload)

    def _handle_row(self, row: dict) -> None:
        """Override in subclasses to add rows to the table."""
        pass

    def _handle_hop(self, hop) -> None:
        pass

    def _handle_log(self, msg: str) -> None:
        log: RichLog = self.query_one("#tool-log-console", RichLog)
        log.write(f"[{PALETTE['text']}]{msg}[/]")

    def _handle_done(self, msg: str) -> None:
        log: RichLog = self.query_one("#tool-log-console", RichLog)
        log.write(f"[{PALETTE['ok']}]✓ {msg}[/]")
        self.status_msg = msg[:80]
        self.done = True

    def _handle_error(self, msg: str) -> None:
        log: RichLog = self.query_one("#tool-log-console", RichLog)
        log.write(f"[{PALETTE['error']}]✗ ERROR: {msg}[/]")
        self.status_msg = f"Error: {msg[:60]}"

    # -- Actions ------------------------------------------------------

    def action_back(self) -> None:
        if self._worker:
            self._worker.stop()
        self.app.pop_screen()

    def action_restart(self) -> None:
        table: DataTable = self.query_one("#tool-table", DataTable)
        table.clear(columns=True)
        self._setup_table()
        log: RichLog = self.query_one("#tool-log-console", RichLog)
        log.clear()
        self.done = False
        self._start_tool()

    def watch_status_msg(self, msg: str) -> None:
        try:
            bar: Label = self.query_one("#tool-status-bar", Label)
            bar.update(f"  {msg}  |  ESC: Back  |  R: Restart")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Traceroute Screen
# ---------------------------------------------------------------------------

class TracerouteScreen(ToolScreen):
    TITLE = "Traceroute"
    COLUMNS = [
        ("Hop", "hop", 4),
        ("IP Address", "ip", 16),
        ("RTT", "rtt", 10),
        ("Country", "country", 16),
        ("City", "city", 14),
        ("ISP", "isp", 22),
        ("ASN", "asn", 20),
    ]

    def __init__(self, target: str, **kwargs) -> None:
        super().__init__(target=target, **kwargs)
        self._hops: dict[int, Hop] = {}

    def create_worker(self) -> Optional[BaseWorker]:
        return TracerouteWorker(self.target, self._event_queue)

    def _handle_hop(self, hop: Hop) -> None:
        self._hops[hop.number] = hop
        self._upsert_row(hop)

    def _upsert_row(self, hop: Hop) -> None:
        table: DataTable = self.query_one("#tool-table", DataTable)
        row_key = str(hop.number)
        is_dest = hop.is_destination
        hop_label = "DEST" if is_dest else str(hop.number)
        hop_style = "#f9e2af bold" if is_dest else PALETTE["hop_num"]

        hop_cell = Text(hop_label, style=hop_style)
        ip_style = "#f9e2af" if is_dest else (PALETTE["error"] if hop.timed_out else PALETTE["text"])
        ip_cell = Text(hop.ip or "* * *", style=ip_style)

        if is_dest and not hop.rtt_ms:
            rtt_cell = Text("Target", style="#f9e2af")
        elif hop.timed_out:
            rtt_cell = Text("* * *", style=PALETTE["error"])
        elif hop.avg_rtt is None:
            rtt_cell = Text("—", style=PALETTE["muted"])
        else:
            avg = hop.avg_rtt
            colour = PALETTE["ok"] if avg < 50 else PALETTE["warn"] if avg < 150 else PALETTE["error"]
            rtt_cell = Text(f"{avg:.1f} ms", style=colour)

        def _flag(code: str) -> str:
            if not code or len(code) != 2:
                return ""
            return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))

        ctry_cell = Text(f"{_flag(hop.country_code)} {hop.country}"[:16], style=PALETTE["country"])
        city_cell = Text(hop.city[:14], style=PALETTE["muted"])
        isp_cell = Text((hop.isp[:22] if hop.isp else "—"), style=PALETTE["isp"])
        asn_cell = Text((hop.asn[:20] if hop.asn else "—"), style=PALETTE["asn"])

        cells = (hop_cell, ip_cell, rtt_cell, ctry_cell, city_cell, isp_cell, asn_cell)
        try:
            table.update_cell(row_key, "hop", hop_cell, update_width=False)
            table.update_cell(row_key, "ip", ip_cell, update_width=False)
            table.update_cell(row_key, "rtt", rtt_cell, update_width=False)
            table.update_cell(row_key, "country", ctry_cell, update_width=False)
            table.update_cell(row_key, "city", city_cell, update_width=False)
            table.update_cell(row_key, "isp", isp_cell, update_width=False)
            table.update_cell(row_key, "asn", asn_cell, update_width=False)
        except Exception:
            table.add_row(*cells, key=row_key)


# ---------------------------------------------------------------------------
# Ping Screen
# ---------------------------------------------------------------------------

class PingScreen(ToolScreen):
    TITLE = "Ping"
    COLUMNS = [
        ("Seq", "seq", 6),
        ("RTT (ms)", "rtt", 12),
        ("Status", "status", 10),
    ]

    def __init__(self, target: str, **kwargs) -> None:
        super().__init__(target=target, **kwargs)
        self._seq = 0

    def create_worker(self) -> Optional[BaseWorker]:
        return PingWorker(self.target, self._event_queue)

    def _handle_row(self, row: dict) -> None:
        self._seq += 1
        table: DataTable = self.query_one("#tool-table", DataTable)
        rtt = row.get("rtt", 0)
        colour = PALETTE["ok"] if rtt < 50 else PALETTE["warn"] if rtt < 150 else PALETTE["error"]
        cells = (
            Text(str(self._seq), style=PALETTE["hop_num"]),
            Text(f"{rtt:.1f}", style=colour),
            Text("Reply", style=PALETTE["ok"]),
        )
        table.add_row(*cells, key=str(self._seq))


# ---------------------------------------------------------------------------
# DNS Lookup Screen
# ---------------------------------------------------------------------------

class DnsScreen(ToolScreen):
    TITLE = "DNS Lookup"
    COLUMNS = [
        ("Record Type", "type", 12),
        ("Value", "value", 60),
    ]

    def create_worker(self) -> Optional[BaseWorker]:
        return DnsWorker(self.target, self._event_queue)

    def _handle_row(self, row: dict) -> None:
        table: DataTable = self.query_one("#tool-table", DataTable)
        rtype = row.get("type", "—")
        value = row.get("value", "—")
        cells = (
            Text(rtype, style=PALETTE["hop_num"]),
            Text(value[:60], style=PALETTE["text"]),
        )
        table.add_row(*cells, key=f"{rtype}-{value}-{id(row)}")


# ---------------------------------------------------------------------------
# Port Scan Screen
# ---------------------------------------------------------------------------

class PortScanScreen(ToolScreen):
    TITLE = "Port Scan"
    COLUMNS = [
        ("Port", "port", 8),
        ("State", "state", 10),
        ("Service", "service", 18),
        ("Banner", "banner", 50),
    ]

    def create_worker(self) -> Optional[BaseWorker]:
        return PortScanWorker(self.target, self._event_queue)

    def _handle_row(self, row: dict) -> None:
        table: DataTable = self.query_one("#tool-table", DataTable)
        port = row.get("port", "—")
        state = row.get("state", "—")
        service = row.get("service", "—")
        banner = row.get("banner", "")
        state_style = (
            PALETTE["ok"] if state == "open"
            else PALETTE["warn"] if state == "filtered"
            else PALETTE["muted"]
        )
        cells = (
            Text(str(port), style=PALETTE["hop_num"]),
            Text(state.upper(), style=state_style),
            Text(service, style=PALETTE["isp"]),
            Text(banner[:50], style=PALETTE["text"]),
        )
        table.add_row(*cells, key=str(port))


# ---------------------------------------------------------------------------
# Whois Screen
# ---------------------------------------------------------------------------

class WhoisScreen(ToolScreen):
    TITLE = "Whois"
    COLUMNS = [
        ("Field", "field", 20),
        ("Value", "value", 60),
    ]

    def create_worker(self) -> Optional[BaseWorker]:
        return WhoisWorker(self.target, self._event_queue)

    def _handle_row(self, row: dict) -> None:
        table: DataTable = self.query_one("#tool-table", DataTable)
        field_name = row.get("field", "—")
        value = row.get("value", "—")
        cells = (
            Text(field_name[:20], style=PALETTE["hop_num"]),
            Text(value[:60], style=PALETTE["text"]),
        )
        table.add_row(*cells, key=f"{field_name}-{id(row)}")


# ---------------------------------------------------------------------------
# GeoIP Screen
# ---------------------------------------------------------------------------

class GeoIpScreen(ToolScreen):
    TITLE = "GeoIP / IP Info"
    COLUMNS = [
        ("Field", "field", 20),
        ("Value", "value", 60),
    ]

    def create_worker(self) -> Optional[BaseWorker]:
        return GeoIpWorker(self.target, self._event_queue)

    def _handle_row(self, row: dict) -> None:
        table: DataTable = self.query_one("#tool-table", DataTable)
        field_name = row.get("field", "—")
        value = row.get("value", "—")
        cells = (
            Text(field_name[:20], style=PALETTE["hop_num"]),
            Text(value[:60], style=PALETTE["country"]),
        )
        table.add_row(*cells, key=f"{field_name}-{id(row)}")


# ---------------------------------------------------------------------------
# Netstat Screen
# ---------------------------------------------------------------------------

class NetstatScreen(ToolScreen):
    TITLE = "Netstat (Active Connections)"
    COLUMNS = [
        ("Proto", "proto", 8),
        ("Local Address", "local", 28),
        ("Foreign Address", "foreign", 28),
        ("State", "state", 14),
        ("PID/Program", "pid", 20),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(target="localhost", **kwargs)

    def get_title(self) -> str:
        return f"  NetVizForx-CLI  ──  {self.TITLE}"

    def create_worker(self) -> Optional[BaseWorker]:
        return NetstatWorker(self._event_queue)

    def _handle_row(self, row: dict) -> None:
        table: DataTable = self.query_one("#tool-table", DataTable)
        proto = row.get("proto", "—")
        local = row.get("local", "—")
        foreign = row.get("foreign", "—")
        state = row.get("state", "—")
        pid = row.get("pid", "—")
        state_style = PALETTE["ok"] if state.lower() in ("listen", "established") else PALETTE["muted"]
        cells = (
            Text(proto, style=PALETTE["hop_num"]),
            Text(local[:28], style=PALETTE["text"]),
            Text(foreign[:28], style=PALETTE["text"]),
            Text(state, style=state_style),
            Text(str(pid)[:20], style=PALETTE["isp"]),
        )
        table.add_row(*cells, key=f"{proto}-{local}-{foreign}-{id(row)}")
