<div align="center">
<pre>
 _   _      _ __     ___     _____                     ____ _     ___ 
| \ | | ___| |\ \   / (_)___|  ___|__  _ ____  __     / ___| |   |_ _|
|  \| |/ _ \ __\ \ / /| |_  / |_ / _ \| '__\ \/ /____| |   | |    | | 
| |\  |  __/ |_ \ V / | |/ /|  _| (_) | |   &gt;  &lt;_____| |___| |___ | | 
|_| \_|\___|\__| \_/  |_/___|_|  \___/|_|  /_/\_\     \____|_____|___|
</pre>
</div>

<h3 align="center">Network diagnostics, reimagined for the terminal.</h3>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.9%2B-89b4fa?style=for-the-badge&amp;logo=python&amp;logoColor=white" alt="Python 3.9+"></a>
  <a href="https://textual.textualize.io/"><img src="https://img.shields.io/badge/Textual-0.74.0-cba6f7?style=for-the-badge" alt="Textual 0.74.0"></a>
  <a href="#cross-platform-support"><img src="https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-a6e3a1?style=for-the-badge" alt="Linux, macOS, Windows"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-f9e2af?style=for-the-badge" alt="MIT License"></a>
  <a href="#contributing"><img src="https://img.shields.io/badge/PRs-Welcome-f38ba8?style=for-the-badge" alt="PRs welcome"></a>
</p>

<p align="center">
  <b>Traceroute · Ping · DNS · Port Scan · Whois · GeoIP · Netstat</b><br>
  Seven essential network tools. One keyboard-driven interface. Zero browser tabs.
</p>

---

**NetVizForx-CLI** is a menu-driven, cross-platform network toolkit that lives entirely in your terminal. Trace routes with live GeoIP enrichment, probe latency, resolve DNS, scan common ports, inspect domain ownership, look up ASN data, and audit active connections — without memorizing a drawer full of flags.

Built on [Textual](https://textual.textualize.io/) and [Rich](https://github.com/Textualize/rich), it pairs a slick Catppuccin Mocha interface with background workers that keep every screen responsive while results stream in.

## Contents

- [Why NetVizForx-CLI?](#why-netvizforx-cli)
- [The toolbox](#the-toolbox)
- [Quick start](#quick-start)
- [Usage](#usage)
- [Keyboard controls](#keyboard-controls)
- [Preview](#preview)
- [Under the hood](#under-the-hood)
- [Cross-platform support](#cross-platform-support)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Notes & limits](#notes--limits)
- [Contributing](#contributing)
- [License](#license)

## Why NetVizForx-CLI?

Most network toolkits make you juggle a dozen commands, flags, and output formats. NetVizForx-CLI puts seven diagnostics behind a single, consistent interface:

- **One screen, zero context switching** — every tool shares the same results table, log console, and status bar.
- **Live results, not batch dumps** — background workers stream rows into the UI as they arrive.
- **Geo-aware traceroute** — every hop is enriched with country, city, ISP, and ASN data in parallel.
- **No `nmap`, no `dig`** — port scanning uses pure Python sockets; DNS runs on `dnspython`.
- **Beautiful by default** — Catppuccin Mocha palette, color-coded latency, and a pyfiglet-powered banner.
- **Hassle-free setup** — `main.py` installs its own pinned dependencies on first launch.

## The toolbox

| | Tool | What it does |
|---|------|--------------|
| <kbd>1</kbd> | **Traceroute** | Traces the path to a host, enriching each hop with GeoIP, ISP, and ASN data. The destination is always shown — even when it never answers. |
| <kbd>2</kbd> | **Ping** | Sends 10 ICMP echoes and streams per-packet RTTs, then reports packet loss and min/avg/max latency. |
| <kbd>3</kbd> | **DNS Lookup** | Resolves records with `dnspython`; the engine supports A, AAAA, MX, NS, TXT, CNAME, and SOA records (A by default). |
| <kbd>4</kbd> | **Port Scan** | TCP-connect scans 24 common ports with banner grabbing and open / filtered / closed classification. |
| <kbd>5</kbd> | **Whois** | Pulls domain registration and ownership data via `python-whois`, with a system `whois` fallback. |
| <kbd>6</kbd> | **GeoIP / IP Info** | Resolves any IP or domain to country, region, city, ISP, ASN, and organization. |
| <kbd>7</kbd> | **Netstat** | Lists active TCP/UDP connections with local/foreign addresses and owning PID/program. |
| <kbd>Q</kbd> | **Quit** | Exits cleanly from anywhere. |

## Quick start

```bash
# From the project root — that's it
python main.py
```

> **First launch?** NetVizForx-CLI checks for its pinned dependencies and installs anything missing automatically. No manual `pip install` required.

Prefer to manage packages yourself?

```bash
python -m pip install -r requirements.txt
python main.py
```

**Requirements:** Python 3.9+ and a modern terminal. For the best experience, use Windows Terminal, iTerm2, or any 256-color terminal.

## Usage

```bash
python main.py                  # Launch the interactive menu
python main.py google.com       # Pre-fill a target for every tool
python main.py 1.1.1.1          # IP addresses work too
```

Every tool that needs a target asks for one and pre-fills the value from the command line, so you can review or edit it before pressing <kbd>Enter</kbd>.

## Keyboard controls

| Context | Key | Action |
|---------|-----|--------|
| Menu | <kbd>1</kbd> – <kbd>7</kbd> | Open a tool |
| Menu | <kbd>Q</kbd> | Quit |
| Target prompt | <kbd>Enter</kbd> | Run the tool with the entered target |
| Target prompt | <kbd>Esc</kbd> | Back to the menu |
| Tool screen | <kbd>Esc</kbd> / <kbd>Q</kbd> | Back to the menu |
| Tool screen | <kbd>R</kbd> | Restart the current tool |
| Anywhere | <kbd>Ctrl</kbd> + <kbd>C</kbd> | Quit |

## Preview

```text
╭──────────────────────────────────────────────────────────────────────────╮
│                                                                          │
│  NetVizForx-CLI  ·  Main Menu                                            │
│                                                                          │
│   [1]  Traceroute         Trace the network path to a host               │
│   [2]  Ping               Send ICMP echo requests to check reachability  │
│   [3]  DNS Lookup         Query DNS records via dnspython                │
│   [4]  Port Scan          Scan common TCP ports with banner grabbing     │
│   [5]  Whois              Domain registration & ownership info           │
│   [6]  GeoIP / IP Info    Geographic & ASN data for any IP/domain        │
│   [7]  Netstat            List active network connections                │
│   [q]  Quit               Exit NetVizForx-CLI                            │
│                                                                          │
│   Type a number to select a tool  ·  Q to quit                           │
╰──────────────────────────────────────────────────────────────────────────╯
```

Each tool opens its own screen with a color-coded results table on top and a streaming log console below. Press <kbd>R</kbd> to rerun against the same target, or <kbd>Esc</kbd> to pick another tool.

## Under the hood

```text
                 ┌─────────────────────────────────┐
                 │          Textual TUI            │
                 │  MenuScreen ──▶ ToolScreen      │
                 │      DataTable  +  RichLog      │
                 └────────────────┬────────────────┘
                                  │  drains Queue @ 20 Hz
                                  ▼
                 ┌─────────────────────────────────┐
                 │       Background Workers        │
                 │  traceroute · ping · dns        │
                 │  scan · whois · geoip · netstat │
                 └────────────────┬────────────────┘
                                  │
               system binaries · TCP sockets · ip-api.com
                                  ▼
                 ┌─────────────────────────────────┐
                 │           The Network           │
                 └─────────────────────────────────┘
```

Every worker runs in a daemon thread and communicates through a thread-safe queue using four event types:

```python
("row",   {...})   # append a result row
("log",   "...")   # append a line to the log console
("done",  "...")   # mark the run complete
("error", "...")   # surface a red error message
```

A few details worth knowing:

- **Non-blocking by design** — the UI drains the queue 20 times per second, so long scans never freeze the interface.
- **Parallel GeoIP enrichment** — traceroute hops are resolved concurrently by an 8-thread pool, backed by an in-process cache.
- **Destination guaranteed** — traceroute injects a synthetic destination hop immediately, so the target's IP and geo data appear even if it drops probes.
- **Latency at a glance** — RTTs are colored green under 50 ms, peach under 150 ms, and red beyond that.
- **Honest port states** — an accepted connection is banner-checked and classified as `OPEN` or `FILTERED`; refused connections are `CLOSED`.

## Cross-platform support

| Tool | Linux | macOS | Windows | Backend |
|------|:-----:|:-----:|:-------:|---------|
| Traceroute | ✓ | ✓ | ✓ | `traceroute` / built-in `tracert` |
| Ping | ✓ | ✓ | ✓ | System `ping` with platform-specific flags |
| DNS Lookup | ✓ | ✓ | ✓ | `dnspython` — no system `dig` or `nslookup` |
| Port Scan | ✓ | ✓ | ✓ | Pure Python TCP sockets — no `nmap` |
| Whois | ✓ | ✓ | ✓ | `python-whois`, falling back to system `whois` |
| GeoIP / IP Info | ✓ | ✓ | ✓ | [ip-api.com](https://ip-api.com/) — free, no API key |
| Netstat | ✓ | ✓ | ✓ | System `netstat` with platform-specific flags |

No raw sockets and no root privileges required from the app itself — it delegates low-level work to the operating system's own tools.

## Project structure

```text
NetVizForx-CLI/
├── main.py              # Entry point + automatic dependency bootstrap
├── requirements.txt     # Pinned dependencies
├── src/
│   ├── ui.py            # Textual app, menu screen, target prompt
│   ├── screens.py       # Seven tool screens (table + log layout)
│   ├── workers.py       # Background workers for six tools
│   ├── network.py       # Traceroute engine, GeoIP enrichment, cache
│   └── theme.py         # Catppuccin Mocha color palette
└── LICENSE              # MIT
```

## Tech stack

| Layer | Powered by |
|-------|------------|
| Terminal UI | Textual 0.74.0 |
| Styling & logs | Rich 13.9.4 |
| DNS | dnspython 2.7.0 |
| Whois | python-whois 0.9.4 |
| HTTP / GeoIP | requests 2.32.3 + ip-api.com |
| Banner art | pyfiglet 1.0.2 |

## Notes & limits

- **GeoIP rate limits** — the free ip-api.com tier allows roughly 45 requests per minute. Results are cached in-process, so repeated hops are only looked up once.
- **Traceroute binary** — install it if your system lacks it: `apt install traceroute` (Debian/Ubuntu), `brew install traceroute` (macOS), or use the built-in `tracert` on Windows.
- **Port scan scope** — a fast TCP-connect check across 24 common ports with a 1-second timeout. It is not a full-range or stealth scanner.
- **Whois fallback** — if `python-whois` cannot complete a lookup and no system `whois` is available, install one or expect an error.
- **Accuracy** — geolocation and ASN data are approximate and provider-dependent.
- **Use responsibly** — only scan or probe systems you own or have explicit permission to test.

## Contributing

Ideas, fixes, and new tools are welcome.

1. Fork the repository.
2. Create a branch: `git checkout -b feature/cool-idea`
3. Commit your changes: `git commit -m "Add cool idea"`
4. Push and open a pull request.

A few ideas if you are looking for a starting point:

- Custom port ranges and scan profiles
- A DNS record-type picker
- Export results to JSON or CSV
- Additional color themes
- Stronger IPv6 support across tools

## License

Released under the [MIT License](LICENSE). Copyright © 2026 QuantumTechCoder.

<div align="center">
<br>
<sub>Built for the terminal · Powered by Textual + Rich</sub>
</div>
