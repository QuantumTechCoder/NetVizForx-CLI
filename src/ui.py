"""
ui.py — Textual TUI for NetVizForx-CLI.

Main app with a tool-selection menu. Each tool opens its own screen
(defined in screens.py) with results table + log console. Press ESC
or Q to go back to the menu and pick another tool.

Each tool that needs a target will always prompt for one — the target
is never carried over between tools.
"""

from __future__ import annotations

import platform
import sys
from typing import Optional

import pyfiglet
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Label, RichLog, Input

from src.screens import (
    TracerouteScreen, PingScreen, DnsScreen,
    PortScanScreen, WhoisScreen, GeoIpScreen, NetstatScreen,
)
from src.theme import PALETTE

# ---------------------------------------------------------------------------
# ASCII Art banner — generated in real-time with pyfiglet
# ---------------------------------------------------------------------------

def _make_banner() -> str:
    return pyfiglet.figlet_format("NetVizForx-CLI", font="ansi_shadow")

# ---------------------------------------------------------------------------
# Menu items
# ---------------------------------------------------------------------------

MENU_ITEMS = [
    {"key": "1", "name": "Traceroute",     "desc": "Trace the network path to a host",          "needs_target": True},
    {"key": "2", "name": "Ping",           "desc": "Send ICMP echo requests to check reachability", "needs_target": True},
    {"key": "3", "name": "DNS Lookup",     "desc": "Query DNS records (A, AAAA, MX, NS, TXT…)", "needs_target": True},
    {"key": "4", "name": "Port Scan",      "desc": "Scan common TCP ports for open services",  "needs_target": True},
    {"key": "5", "name": "Whois",          "desc": "Domain registration & ownership info",     "needs_target": True},
    {"key": "6", "name": "GeoIP / IP Info","desc": "Geographic & ASN info for an IP/domain",    "needs_target": True},
    {"key": "7", "name": "Netstat",        "desc": "List active network connections",           "needs_target": False},
    {"key": "q", "name": "Quit",           "desc": "Exit NetVizForx-CLI",                        "needs_target": False},
]

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

MENU_CSS = """
Screen {
    background: #11111b;
}

#menu-title {
    background: #1e1e2e;
    color: #89b4fa;
    text-align: center;
    height: auto;
    max-height: 10;
    padding: 1 2;
}

#menu-subtitle {
    color: #6c7086;
    text-align: center;
    height: 1;
    padding: 0 2;
}

#menu-list {
    height: auto;
    max-height: 16;
    border: solid #45475a;
    background: #181825;
    margin: 1 4;
    padding: 1 2;
}

#menu-list > Label {
    height: 1;
    color: #cdd6f4;
}

#menu-list > Label:hover {
    background: #313244;
}

#menu-footer {
    color: #6c7086;
    text-align: center;
    height: 1;
    padding: 0 2;
}

#menu-os-info {
    color: #45475a;
    text-align: center;
    height: 1;
    padding: 0 2;
}
"""

# ---------------------------------------------------------------------------
# Menu Screen
# ---------------------------------------------------------------------------

from textual.screen import Screen


class MenuScreen(Screen):
    """Main menu — pick a tool by number."""

    CSS = MENU_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, target: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.target = target

    def compose(self) -> ComposeResult:
        yield Label(_make_banner(), id="menu-title")
        if self.target:
            yield Label(f"  Default target: {self.target}  (press Enter to use it, or type a new one)", id="menu-subtitle")
        else:
            yield Label("  You'll be prompted for a target each time you select a tool", id="menu-subtitle")
        with Vertical(id="menu-list"):
            for item in MENU_ITEMS:
                yield Label(
                    f"  [{item['key']}] {item['name']:<18s} — {item['desc']}",
                    id=f"menu-item-{item['key']}",
                )
        yield Label("  Type a number and press Enter, or press Q to quit", id="menu-footer")
        os_name = f"{platform.system()} {platform.release()} ({platform.machine()})"
        yield Label(f"  Running on: {os_name}", id="menu-os-info")

    def on_key(self, event) -> None:
        for item in MENU_ITEMS:
            if event.key == item["key"] or event.character == item["key"]:
                self._select(item)
                event.prevent_default()
                return
        if event.key == "q" or event.character == "q":
            self.app.exit()

    def _select(self, item: dict) -> None:
        if item["name"] == "Quit":
            self.app.exit()
            return

        if item["needs_target"]:
            self._prompt_target(item)
            return

        self._launch(item, "")

    def _prompt_target(self, item: dict) -> None:
        self.app.push_screen(TargetInputScreen(menu_item=item, default_target=self.target))

    def _launch(self, item: dict, target: str) -> None:
        name = item["name"]
        if name == "Traceroute":
            self.app.push_screen(TracerouteScreen(target=target))
        elif name == "Ping":
            self.app.push_screen(PingScreen(target=target))
        elif name == "DNS Lookup":
            self.app.push_screen(DnsScreen(target=target))
        elif name == "Port Scan":
            self.app.push_screen(PortScanScreen(target=target))
        elif name == "Whois":
            self.app.push_screen(WhoisScreen(target=target))
        elif name == "GeoIP / IP Info":
            self.app.push_screen(GeoIpScreen(target=target))
        elif name == "Netstat":
            self.app.push_screen(NetstatScreen())


# ---------------------------------------------------------------------------
# Target Input Screen
# ---------------------------------------------------------------------------

class TargetInputScreen(Screen):
    """Prompts the user for a target host/IP, then launches the selected tool."""

    CSS = """
    TargetInputScreen {
        background: #11111b;
        align: center middle;
    }

    #target-input-box {
        width: 64;
        height: auto;
        border: solid #89b4fa;
        background: #181825;
        padding: 1 2;
    }

    #target-input-label {
        color: #89b4fa;
        height: 1;
        margin: 0 0 1 0;
    }

    #target-input-field {
        margin: 0 0 1 0;
    }

    #target-input-hint {
        color: #6c7086;
        height: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "back", "Back to Menu"),
    ]

    def __init__(self, menu_item: dict, default_target: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.menu_item = menu_item
        self.default_target = default_target

    def compose(self) -> ComposeResult:
        with Vertical(id="target-input-box"):
            yield Label(f"  Enter target for {self.menu_item['name']}", id="target-input-label")
            yield Input(
                value=self.default_target,
                placeholder="e.g. google.com, 1.1.1.1, github.com",
                id="target-input-field",
            )
            yield Label("  Press Enter to start  |  ESC to go back", id="target-input-hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        target = event.value.strip()
        if not target:
            return
        self.app.pop_screen()
        self.app.screen._launch(self.menu_item, target)

    def action_back(self) -> None:
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class NetVizForxApp(App):
    """NetVizForx-CLI — multi-tool networking suite."""

    CSS = MENU_CSS

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, target: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.initial_target = target

    def on_mount(self) -> None:
        self.push_screen(MenuScreen(target=self.initial_target))

    def action_quit(self) -> None:
        self.exit()
