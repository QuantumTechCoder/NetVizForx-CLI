"""
network.py — traceroute engine with async BGP/GeoIP enrichment.

Uses subprocess to invoke the system traceroute (no raw-socket root needed),
then enriches each hop with ip-api.com metadata in a background thread pool.
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from queue import Queue
from typing import Callable, Optional

import requests

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Hop:
    number: int
    ip: Optional[str] = None
    hostname: Optional[str] = None
    rtt_ms: list[float] = field(default_factory=list)
    country: str = "—"
    country_code: str = ""
    region: str = "—"
    city: str = "—"
    isp: str = "—"
    asn: str = "—"
    org: str = "—"
    timed_out: bool = False
    enriched: bool = False
    is_destination: bool = False  # synthetic destination hop

    @property
    def avg_rtt(self) -> Optional[float]:
        if not self.rtt_ms:
            return None
        return sum(self.rtt_ms) / len(self.rtt_ms)

    @property
    def rtt_display(self) -> str:
        if self.timed_out:
            return "* * *"
        if self.avg_rtt is None:
            return "—"
        return f"{self.avg_rtt:.1f} ms"


# ---------------------------------------------------------------------------
# GeoIP / BGP lookup (ip-api.com — free, no auth, 45 req/min limit)
# ---------------------------------------------------------------------------

_geo_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

_PRIVATE_RANGES = (
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
    "172.30.", "172.31.", "192.168.", "127.", "::1", "fe80",
)

def _is_private(ip: str) -> bool:
    return any(ip.startswith(r) for r in _PRIVATE_RANGES)


def fetch_ip_metadata(ip: str) -> dict:
    """Return geo/ASN metadata for an IP, using an in-process cache."""
    if not ip or _is_private(ip):
        return {
            "country": "Private",
            "countryCode": "",
            "regionName": "—",
            "city": "—",
            "isp": "Private / RFC1918",
            "as": "—",
            "org": "—",
        }

    with _cache_lock:
        if ip in _geo_cache:
            return _geo_cache[ip]

    try:
        fields = "country,countryCode,regionName,city,isp,as,org,status,message"
        resp = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": fields},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "fail":
            data = {
                "country": "Unknown",
                "countryCode": "",
                "regionName": "—",
                "city": "—",
                "isp": "—",
                "as": "—",
                "org": "—",
            }
    except Exception:
        data = {
            "country": "Error",
            "countryCode": "",
            "regionName": "—",
            "city": "—",
            "isp": "—",
            "as": "—",
            "org": "—",
        }

    with _cache_lock:
        _geo_cache[ip] = data

    return data


# ---------------------------------------------------------------------------
# Traceroute parser
# ---------------------------------------------------------------------------

# Matches lines like:
#   1  192.168.1.1 (192.168.1.1)  2.345 ms  2.100 ms  1.987 ms
#   3  * * *
#   5  ae-2.r02.lsanca07.us.bb.gin.ntt.net (129.250.5.186)  11.2 ms  11.1 ms  10.9 ms
_HOP_RE = re.compile(
    r"^\s*(\d+)\s+"                       # hop number
    r"(?:"
    r"(\S+)\s+\((\d+\.\d+\.\d+\.\d+)\)"  # hostname (ip)
    r"|(\d+\.\d+\.\d+\.\d+)"             # bare ip
    r"|\*"                                # timeout
    r")"
    r"(.*?)$",
    re.MULTILINE,
)

_RTT_RE = re.compile(r"([\d.]+)\s*ms")


def _parse_traceroute_line(line: str) -> Optional[Hop]:
    """Parse a single traceroute output line into a Hop, or None."""
    line = line.strip()
    if not line:
        return None

    # Detect pure timeout line: "N  * * *"
    timeout_match = re.match(r"^\s*(\d+)\s+(\*\s*)+$", line)
    if timeout_match:
        hop = Hop(number=int(timeout_match.group(1)), timed_out=True)
        return hop

    m = _HOP_RE.match(line)
    if not m:
        return None

    hop_num = int(m.group(1))
    hostname = m.group(2)
    ip_from_parens = m.group(3)
    bare_ip = m.group(4)
    rest = m.group(5) or ""

    ip = ip_from_parens or bare_ip
    if not ip:
        # Could be partial timeout with some probes answering
        # Try to find an IP anywhere in the line
        ip_search = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
        if ip_search:
            ip = ip_search.group(1)
        else:
            hop = Hop(number=hop_num, timed_out=True)
            return hop

    rtts = [float(x) for x in _RTT_RE.findall(rest)]
    timed_out = not rtts and "*" in line

    hop = Hop(
        number=hop_num,
        ip=ip,
        hostname=hostname if hostname and hostname != ip else ip,
        rtt_ms=rtts,
        timed_out=timed_out and not rtts,
    )
    return hop


def _build_traceroute_cmd(target: str, max_hops: int = 30) -> list[str]:
    if sys.platform == "win32":
        return ["tracert", "-d", "-h", str(max_hops), target]
    else:
        # -n = no DNS reverse lookup (we do our own), -m = max hops, -w = wait ms
        return ["traceroute", "-n", "-m", str(max_hops), "-w", "2", target]


# ---------------------------------------------------------------------------
# TracerouteWorker — runs in a background thread, posts events via a Queue
# ---------------------------------------------------------------------------

class TracerouteWorker:
    """
    Runs traceroute in a subprocess, parses output line-by-line,
    enriches hops with BGP/GeoIP data, and posts updates through
    an event queue consumed by the TUI.

    Event types posted to the queue:
      ("hop",    Hop)          — new or updated hop
      ("log",    str)          — diagnostic log message
      ("done",   str)          — traceroute finished, carries final message
      ("error",  str)          — fatal error message
    """

    def __init__(
        self,
        target: str,
        event_queue: Queue,
        max_hops: int = 30,
    ) -> None:
        self.target = target
        self.event_queue = event_queue
        self.max_hops = max_hops
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="geo")
        self.hops: dict[int, Hop] = {}

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="traceroute-worker"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    def _post(self, kind: str, payload) -> None:
        self.event_queue.put((kind, payload))

    def _enrich_hop(self, hop: Hop) -> None:
        """Fetch metadata for a hop's IP and re-post an updated hop event."""
        if not hop.ip or hop.timed_out or _is_private(hop.ip):
            if _is_private(hop.ip or ""):
                hop.country = "Private"
                hop.isp = "RFC1918"
                hop.asn = "—"
                hop.enriched = True
                self._post("hop", hop)
            return

        meta = fetch_ip_metadata(hop.ip)
        hop.country = meta.get("country", "—") or "—"
        hop.country_code = meta.get("countryCode", "") or ""
        hop.region = meta.get("regionName", "—") or "—"
        hop.city = meta.get("city", "—") or "—"
        hop.isp = meta.get("isp", "—") or "—"
        hop.asn = meta.get("as", "—") or "—"
        hop.org = meta.get("org", "—") or "—"
        hop.enriched = True
        self._post("hop", hop)

    # Sentinel key used for the synthetic destination row before real hop arrives
    _DEST_KEY = 9999

    def _run(self) -> None:
        # Resolve target first so we can log the resolved IP
        resolved_ip = ""
        try:
            resolved_ip = socket.gethostbyname(self.target)
            self._post("log", f"Resolved {self.target} → {resolved_ip}")
        except socket.gaierror as exc:
            self._post("error", f"DNS resolution failed for '{self.target}': {exc}")
            return

        # --- Inject synthetic destination hop immediately ---
        # This ensures Google's (or any target's) IP and GeoIP info always appear
        # in the table, even if traceroute never gets a reply from the destination.
        dest_hop = Hop(
            number=self._DEST_KEY,
            ip=resolved_ip,
            hostname=self.target,
            is_destination=True,
        )
        self.hops[self._DEST_KEY] = dest_hop
        self._post("hop", dest_hop)
        self._post("log", f"Destination: {self.target} ({resolved_ip}) — fetching info…")
        # Enrich destination in background immediately
        dest_future = self._executor.submit(self._enrich_hop, dest_hop)

        cmd = _build_traceroute_cmd(self.target, self.max_hops)
        self._post("log", f"Running: {' '.join(cmd)}")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            self._post(
                "error",
                "traceroute not found. Install it: apt install traceroute / brew install traceroute",
            )
            return

        pending_futures = [dest_future]

        for raw_line in proc.stdout:  # type: ignore[union-attr]
            if self._stop_event.is_set():
                proc.terminate()
                break

            line = raw_line.rstrip()
            if not line:
                continue

            # Skip header lines
            if re.match(r"^traceroute\s+to", line, re.IGNORECASE):
                self._post("log", line)
                continue
            if re.match(r"^Tracing\s+route\s+to", line, re.IGNORECASE):
                self._post("log", line)
                continue

            hop = _parse_traceroute_line(line)
            if hop is None:
                self._post("log", f"[raw] {line}")
                continue

            # If traceroute actually reaches the destination, promote the synthetic
            # hop to a real one: copy the enrichment data we already fetched and
            # replace the sentinel key with the real hop number.
            if hop.ip and hop.ip == resolved_ip and not hop.timed_out:
                real_dest = dest_hop  # reference already has enrichment
                real_dest.number = hop.number
                real_dest.rtt_ms = hop.rtt_ms
                real_dest.is_destination = True
                # Remove sentinel row from our dict, add under real hop number
                self.hops.pop(self._DEST_KEY, None)
                self.hops[hop.number] = real_dest
                self._post("hop", real_dest)
                self._post("log", f"Hop {hop.number} (DEST): {hop.ip}  {real_dest.rtt_display}")
                continue

            self.hops[hop.number] = hop
            self._post("hop", hop)

            if hop.timed_out:
                self._post("log", f"Hop {hop.number}: Request timed out (* * *)")
            else:
                rtt_str = hop.rtt_display
                self._post("log", f"Hop {hop.number}: {hop.ip}  {rtt_str}")
                if hop.ip:
                    fut = self._executor.submit(self._enrich_hop, hop)
                    pending_futures.append(fut)

        proc.wait()

        # Wait for all enrichment tasks (including destination)
        for fut in as_completed(pending_futures, timeout=15):
            try:
                fut.result()
            except Exception:
                pass

        # Count real hops only (exclude sentinel if still present)
        real_hop_count = sum(1 for k in self.hops if k != self._DEST_KEY)

        if self._stop_event.is_set():
            self._post("log", "Traceroute cancelled by user.")
        else:
            self._post("done", f"Traceroute to {self.target} ({resolved_ip}) complete — {real_hop_count} hops")
            self._post("log", f"Traceroute complete. {real_hop_count} hops recorded.")
