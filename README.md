# NetVizForx-CLI

A cross-platform (Linux / macOS / Windows) terminal-based network toolkit suite with a menu-driven interface.

## Tools Included

1. **Traceroute** — Trace the network path to a host with GeoIP enrichment
2. **Ping** — Send ICMP echo requests to check reachability and latency
3. **DNS Lookup** — Query DNS records (A, AAAA, MX, NS, TXT, CNAME, SOA)
4. **Port Scan** — Scan common TCP ports for open services with banner grabbing
5. **Whois** — Domain registration and ownership information
6. **GeoIP / IP Info** — Geographic location and ASN data for any IP or domain
7. **Netstat** — List active network connections on your machine

## Usage

```bash
python main.py                 # Launch with menu, prompted for target per tool
python main.py google.com      # Pre-fill target for all tools
python main.py 1.1.1.1
```

## Navigation

- Type a number to select a tool
- Press **ESC** or **Q** to go back to the menu from any tool
- Press **R** to restart the current tool
- Press **Q** from the menu to quit

## Requirements

```bash
pip install -r requirements.txt
```

## Cross-Platform Notes

- **Traceroute**: Uses `traceroute` (Linux/macOS) or `tracert` (Windows)
- **Ping**: Uses system `ping` with platform-appropriate flags
- **DNS Lookup**: Uses `dnspython` — no system `dig` or `nslookup` needed
- **Port Scan**: Pure Python TCP connect — no `nmap` required
- **Whois**: Uses `python-whois` library, falls back to system `whois` command
- **GeoIP**: Uses ip-api.com (free, no auth required)
- **Netstat**: Uses system `netstat` command
