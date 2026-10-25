"""
workers.py — networking tool workers for NetVizForx-CLI.

Each worker runs in a background thread and posts events to a Queue:
  ("row",   dict)   — a data row to display in a table
  ("log",   str)    — a log message
  ("done",  str)    — tool finished
  ("error", str)    — fatal error

All workers are cross-platform (Linux / macOS / Windows).
"""

from __future__ import annotations

import platform
import re
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from queue import Queue
from typing import Optional

import requests

from src.network import Hop, TracerouteWorker, fetch_ip_metadata

# ---------------------------------------------------------------------------
# Base worker
# ---------------------------------------------------------------------------

class BaseWorker:
    """Base class for all tool workers."""

    def __init__(self, event_queue: Queue) -> None:
        self.event_queue = event_queue
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name=type(self).__name__)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _post(self, kind: str, payload) -> None:
        self.event_queue.put((kind, payload))

    def _run(self) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Ping worker — cross-platform ICMP ping
# ---------------------------------------------------------------------------

@dataclass
class PingResult:
    target: str = ""
    ip: str = ""
    packets_sent: int = 0
    packets_recv: int = 0
    loss_pct: float = 0.0
    min_ms: float = 0.0
    avg_ms: float = 0.0
    max_ms: float = 0.0
    mdev_ms: float = 0.0
    rtt_samples: list[float] = field(default_factory=list)
    is_alive: bool = False
    error: str = ""

class PingWorker(BaseWorker):
    """Cross-platform ping worker."""

    def __init__(self, target: str, event_queue: Queue, count: int = 10) -> None:
        super().__init__(event_queue)
        self.target = target
        self.count = count

    def _build_cmd(self) -> list[str]:
        is_win = sys.platform == "win32"
        if is_win:
            return ["ping", "-n", str(self.count), "-w", "2000", self.target]
        return ["ping", "-c", str(self.count), "-i", "0.5", "-W", "2", self.target]

    def _parse_line(self, line: str) -> Optional[dict]:
        # Linux/macOS: "64 bytes from ...: icmp_seq=1 ttl=64 time=12.3 ms"
        m = re.search(r"time=([\d.]+)\s*ms", line)
        if m:
            return {"rtt": float(m.group(1))}
        # Windows: "Reply from 1.1.1.1: bytes=32 time=12ms TTL=57"
        m = re.search(r"time[=<]([\d.]+)\s*ms", line, re.IGNORECASE)
        if m:
            return {"rtt": float(m.group(1))}
        return None

    def _parse_summary(self, output: str) -> PingResult:
        result = PingResult(target=self.target)
        result.packets_sent = self.count

        # Linux/macOS summary
        m = re.search(r"(\d+)\s+packets transmitted.*?(\d+)\s+received", output, re.DOTALL)
        if m:
            result.packets_sent = int(m.group(1))
            result.packets_recv = int(m.group(2))
            result.is_alive = result.packets_recv > 0
            result.loss_pct = round((1 - result.packets_recv / max(result.packets_sent, 1)) * 100, 1)

            stats = re.search(r"min/avg/max/(?:mdev|stddev)\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", output)
            if stats:
                result.min_ms = float(stats.group(1))
                result.avg_ms = float(stats.group(2))
                result.max_ms = float(stats.group(3))
                result.mdev_ms = float(stats.group(4))
            return result

        # Windows summary
        m = re.search(r"Sent\s*=\s*(\d+).*?Received\s*=\s*(\d+).*?Lost\s*=\s*(\d+)", output, re.DOTALL | re.IGNORECASE)
        if m:
            result.packets_sent = int(m.group(1))
            result.packets_recv = int(m.group(2))
            result.is_alive = result.packets_recv > 0
            result.loss_pct = round((1 - result.packets_recv / max(result.packets_sent, 1)) * 100, 1)
            stats = re.search(r"Minimum\s*=\s*([\d.]+)\s*ms.*?Maximum\s*=\s*([\d.]+)\s*ms.*?Average\s*=\s*([\d.]+)\s*ms", output, re.DOTALL | re.IGNORECASE)
            if stats:
                result.min_ms = float(stats.group(1))
                result.max_ms = float(stats.group(2))
                result.avg_ms = float(stats.group(3))
            return result

        return result

    def _run(self) -> None:
        try:
            ip = socket.gethostbyname(self.target)
            self._post("log", f"Resolved {self.target} → {ip}")
        except socket.gaierror as exc:
            self._post("error", f"DNS resolution failed for '{self.target}': {exc}")
            return

        cmd = self._build_cmd()
        self._post("log", f"Running: {' '.join(cmd)}")

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except FileNotFoundError:
            self._post("error", "ping command not found on this system.")
            return

        full_output: list[str] = []
        for raw_line in proc.stdout:  # type: ignore[union-attr]
            if self._stop_event.is_set():
                proc.terminate()
                break
            line = raw_line.rstrip()
            if not line:
                continue
            full_output.append(line)
            self._post("log", line)
            parsed = self._parse_line(line)
            if parsed:
                self._post("row", parsed)

        proc.wait()
        output_text = "\n".join(full_output)
        result = self._parse_summary(output_text)
        result.ip = ip

        if self._stop_event.is_set():
            self._post("done", "Ping cancelled by user.")
        else:
            if result.is_alive:
                self._post("done", f"Ping complete — {result.packets_recv}/{result.packets_sent} received, {result.loss_pct}% loss, avg {result.avg_ms:.1f} ms")
            else:
                self._post("done", f"Ping complete — host unreachable ({result.loss_pct}% loss)")


# ---------------------------------------------------------------------------
# DNS Lookup worker — cross-platform via dnspython
# ---------------------------------------------------------------------------

class DnsWorker(BaseWorker):
    """DNS lookup worker using dnspython (no system dig/nslookup needed)."""

    def __init__(self, target: str, event_queue: Queue, record_type: str = "A") -> None:
        super().__init__(event_queue)
        self.target = target
        self.record_type = record_type.upper()

    def _run(self) -> None:
        try:
            import dns.resolver
            import dns.exception
        except ImportError:
            self._post("error", "dnspython not installed. Run: pip install dnspython")
            return

        self._post("log", f"DNS lookup for {self.target} — record type: {self.record_type}")

        record_types = [self.record_type] if self.record_type != "ALL" else ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]

        for rtype in record_types:
            if self._stop_event.is_set():
                break
            try:
                resolver = dns.resolver.Resolver()
                resolver.lifetime = 5
                answers = resolver.resolve(self.target, rtype)
                for rdata in answers:
                    if self._stop_event.is_set():
                        break
                    value = str(rdata)
                    self._post("row", {"type": rtype, "value": value})
                    self._post("log", f"  {rtype}: {value}")
            except dns.resolver.NoAnswer:
                self._post("log", f"  {rtype}: No answer")
            except dns.resolver.NXDOMAIN:
                self._post("log", f"  {rtype}: NXDOMAIN (domain does not exist)")
            except dns.resolver.NoNameservers:
                self._post("log", f"  {rtype}: No nameservers responded")
            except dns.exception.Timeout:
                self._post("log", f"  {rtype}: Timeout")
            except Exception as exc:
                self._post("log", f"  {rtype}: Error — {exc}")

        if self._stop_event.is_set():
            self._post("done", "DNS lookup cancelled by user.")
        else:
            self._post("done", f"DNS lookup complete for {self.target}")


# ---------------------------------------------------------------------------
# Port Scanner worker — pure Python socket connect (no nmap needed)
# ---------------------------------------------------------------------------

class PortScanWorker(BaseWorker):
    """TCP connect port scanner using raw sockets — no nmap required."""

    COMMON_PORTS = {
        20: "FTP-Data", 21: "FTP", 22: "SSH", 23: "Telnet",
        25: "SMTP", 53: "DNS", 80: "HTTP", 110: "POP3",
        143: "IMAP", 443: "HTTPS", 445: "SMB", 587: "SMTP-TLS",
        993: "IMAPS", 995: "POP3S", 1433: "MSSQL", 1521: "Oracle",
        3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
        5900: "VNC", 6379: "Redis", 8080: "HTTP-Proxy",
        8443: "HTTPS-Alt", 9200: "Elasticsearch",
    }

    def __init__(self, target: str, event_queue: Queue, ports: Optional[list[int]] = None, timeout: float = 1.0) -> None:
        super().__init__(event_queue)
        self.target = target
        self.ports = ports or sorted(self.COMMON_PORTS.keys())
        self.timeout = timeout

    def _run(self) -> None:
        try:
            ip = socket.gethostbyname(self.target)
            self._post("log", f"Resolved {self.target} → {ip}")
        except socket.gaierror as exc:
            self._post("error", f"DNS resolution failed for '{self.target}': {exc}")
            return

        self._post("log", f"Scanning {len(self.ports)} ports on {self.target} ({ip})…")

        open_count = 0
        closed_count = 0
        filtered_count = 0
        for port in self.ports:
            if self._stop_event.is_set():
                break

            service = self.COMMON_PORTS.get(port, "Unknown")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((ip, port))
            sock.close()

            if result == 0:
                # Connection accepted — now verify the port actually responds.
                # Try a banner grab; if the service ignores all reads or times out
                # without delivering any data, classify as "filtered" rather than
                # a flat "open".
                banner = ""
                banner_ok = False
                try:
                    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock2.settimeout(2)
                    sock2.connect((ip, port))
                    if port in (80, 8080, 8443):
                        sock2.sendall(b"GET / HTTP/1.0\r\nHost: " + self.target.encode() + b"\r\n\r\n")
                    banner_data = sock2.recv(128)
                    sock2.close()
                    if banner_data:
                        banner = banner_data.decode("utf-8", errors="replace").split("\n")[0].strip()[:60]
                        banner_ok = True
                except socket.timeout:
                    pass
                except Exception:
                    pass

                if banner_ok:
                    open_count += 1
                    self._post("row", {
                        "port": port, "state": "open", "service": service, "banner": banner
                    })
                    self._post("log", f"  Port {port:>5}  OPEN   {service}  {banner}")
                else:
                    filtered_count += 1
                    self._post("row", {
                        "port": port, "state": "filtered", "service": service, "banner": ""
                    })
                    self._post("log", f"  Port {port:>5}  FILTERED   {service}  (no service response)")
            else:
                closed_count += 1
                self._post("row", {
                    "port": port, "state": "closed", "service": service, "banner": ""
                })

        if self._stop_event.is_set():
            self._post("done", "Port scan cancelled by user.")
        else:
            self._post("done", f"Port scan complete — {open_count} open, {filtered_count} filtered, {closed_count} closed out of {len(self.ports)} ports")


# ---------------------------------------------------------------------------
# Whois worker — uses python-whois or falls back to system whois
# ---------------------------------------------------------------------------

class WhoisWorker(BaseWorker):
    """Whois lookup worker."""

    def __init__(self, target: str, event_queue: Queue) -> None:
        super().__init__(event_queue)
        self.target = target

    def _run(self) -> None:
        self._post("log", f"Whois lookup for {self.target}…")

        # Try python-whois library first
        try:
            import whois
            data = whois.whois(self.target)
            fields = [
                ("Domain", data.domain_name),
                ("Registrar", data.registrar),
                ("Created", data.creation_date),
                ("Expires", data.expiration_date),
                ("Updated", data.updated_date),
                ("Name Servers", data.name_servers),
                ("Status", data.status),
                ("Registrant", data.registrant),
                ("Admin Email", data.admins),
                ("Tech Email", data.techs),
                ("Org", data.org),
                ("Country", data.country),
            ]
            for label, value in fields:
                if value:
                    val_str = str(value)
                    if len(val_str) > 80:
                        val_str = val_str[:77] + "…"
                    self._post("row", {"field": label, "value": val_str})
                    self._post("log", f"  {label}: {val_str}")
            self._post("done", f"Whois lookup complete for {self.target}")
            return
        except ImportError:
            self._post("log", "python-whois not installed, falling back to system whois…")
        except Exception as exc:
            self._post("log", f"python-whois error: {exc}, trying system whois…")

        # Fall back to system whois command
        try:
            proc = subprocess.Popen(
                ["whois", self.target],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except FileNotFoundError:
            self._post("error", "whois command not found. Install it: apt install whois / brew install whois")
            return

        for raw_line in proc.stdout:  # type: ignore[union-attr]
            if self._stop_event.is_set():
                proc.terminate()
                break
            line = raw_line.rstrip()
            if not line:
                continue
            # Parse "key: value" lines
            m = re.match(r"^([\w\s.-]+):\s*(.+)$", line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                if len(val) > 80:
                    val = val[:77] + "…"
                self._post("row", {"field": key, "value": val})
            self._post("log", line)

        proc.wait()
        if self._stop_event.is_set():
            self._post("done", "Whois lookup cancelled by user.")
        else:
            self._post("done", f"Whois lookup complete for {self.target}")


# ---------------------------------------------------------------------------
# GeoIP / IP Info worker — uses ip-api.com
# ---------------------------------------------------------------------------

class GeoIpWorker(BaseWorker):
    """GeoIP + ASN info for a target IP or domain."""

    def __init__(self, target: str, event_queue: Queue) -> None:
        super().__init__(event_queue)
        self.target = target

    def _run(self) -> None:
        try:
            ip = socket.gethostbyname(self.target)
            self._post("log", f"Resolved {self.target} → {ip}")
        except socket.gaierror as exc:
            self._post("error", f"DNS resolution failed for '{self.target}': {exc}")
            return

        self._post("log", f"Fetching GeoIP data for {ip}…")

        meta = fetch_ip_metadata(ip)
        fields = [
            ("IP", ip),
            ("Country", meta.get("country", "—")),
            ("Country Code", meta.get("countryCode", "—")),
            ("Region", meta.get("regionName", "—")),
            ("City", meta.get("city", "—")),
            ("ISP", meta.get("isp", "—")),
            ("ASN", meta.get("as", "—")),
            ("Org", meta.get("org", "—")),
        ]
        for label, value in fields:
            val_str = str(value)
            if len(val_str) > 80:
                val_str = val_str[:77] + "…"
            self._post("row", {"field": label, "value": val_str})
            self._post("log", f"  {label}: {val_str}")

        self._post("done", f"GeoIP lookup complete for {self.target} ({ip})")


# ---------------------------------------------------------------------------
# Netstat worker — cross-platform active connections
# ---------------------------------------------------------------------------

class NetstatWorker(BaseWorker):
    """Cross-platform network connections listing."""

    def __init__(self, event_queue: Queue) -> None:
        super().__init__(event_queue)

    def _build_cmd(self) -> list[str]:
        if sys.platform == "win32":
            return ["netstat", "-ano"]
        return ["netstat", "-tunp"]

    def _run(self) -> None:
        cmd = self._build_cmd()
        self._post("log", f"Running: {' '.join(cmd)}")

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except FileNotFoundError:
            self._post("error", "netstat command not found on this system.")
            return

        for raw_line in proc.stdout:  # type: ignore[union-attr]
            if self._stop_event.is_set():
                proc.terminate()
                break
            line = raw_line.rstrip()
            if not line:
                continue

            # Parse Linux netstat: Proto Recv-Q Send-Q Local Address Foreign Address State PID/Program
            parts = line.split()
            if len(parts) >= 5 and parts[0] in ("tcp", "tcp6", "udp", "udp6"):
                proto = parts[0]
                local = parts[3] if len(parts) > 3 else "—"
                foreign = parts[4] if len(parts) > 4 else "—"
                state = parts[5] if len(parts) > 5 else "—"
                pid_prog = parts[6] if len(parts) > 6 else "—"
                self._post("row", {
                    "proto": proto, "local": local,
                    "foreign": foreign, "state": state, "pid": pid_prog,
                })
            elif sys.platform == "win32" and len(parts) >= 4 and parts[0].upper() in ("TCP", "UDP"):
                proto = parts[0]
                local = parts[1]
                foreign = parts[2]
                state = parts[3] if len(parts) > 3 else "—"
                pid = parts[4] if len(parts) > 4 else "—"
                self._post("row", {
                    "proto": proto, "local": local,
                    "foreign": foreign, "state": state, "pid": pid,
                })

            self._post("log", line)

        proc.wait()
        if self._stop_event.is_set():
            self._post("done", "Netstat cancelled by user.")
        else:
            self._post("done", "Netstat complete.")
