"""
Local DNS filtering proxy for system-wide website blocking (macOS).

Runs a lightweight UDP DNS server on 127.0.0.1:53 that intercepts all
DNS queries system-wide. Blocked domains return 0.0.0.0; allowed queries
are forwarded to upstream DNS.

Architecture:
  - DNS proxy runs as a ROOT subprocess (port 53 requires privileges)
  - Reads blocklists from a shared state file (same pattern as extension_server)
  - Main process manages DNS system settings via networksetup

Safety guarantees (NO LOCKOUT):
  1. System DNS is set to ["127.0.0.1", "<upstream>"] — if proxy dies,
     macOS falls through to the upstream server automatically.
  2. DNS settings are only changed AFTER the proxy is confirmed listening.
  3. Original DNS settings are persisted to disk for crash recovery.
  4. On clean exit, original DNS is always restored.
"""

import json
import os
import shlex
import signal
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Shared state directory
_APP_DATA_DIR = Path.home() / "Library" / "Application Support" / "ProductivityTimer"
_DNS_STATE_FILE = _APP_DATA_DIR / "dns_proxy_state.json"
_DNS_ORIGINAL_FILE = _APP_DATA_DIR / "dns_original_settings.json"
_DNS_PID_FILE = _APP_DATA_DIR / "dns_proxy.pid"
_DNS_LOG_FILE = _APP_DATA_DIR / "dns_proxy.log"

# Upstream DNS servers (used for forwarding allowed queries)
UPSTREAM_DNS = ["1.1.1.1", "8.8.8.8"]
UPSTREAM_PORT = 53
UPSTREAM_TIMEOUT = 3  # seconds

# Proxy settings
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 53

# Domain heuristic keywords (from nsfw_detector.py)
_SUSPICIOUS_KEYWORDS = {
    "porn", "xxx", "sex", "hentai", "xvideo", "xnxx", "xhamster",
    "redtube", "youporn", "pornhub", "brazzers", "bangbros",
    "jav", "nhentai", "hanime", "rule34", "e621", "gelbooru",
    "danbooru", "fakku", "tsumino", "hitomi", "naughty",
    "onlyfans", "fansly", "chaturbate", "livejasmin", "stripchat",
    "cam4", "bongacams", "myfreecams", "spankbang", "eporner",
    "tnaflix", "tube8", "beeg", "motherless", "xvideos",
    "erotic", "nsfw", "lewd", "smut", "r18", "adult",
    "boob", "nude", "naked",
}

_SUSPICIOUS_PATTERNS = {
    "njav", "jav", "javhd", "javbus", "javlib", "javmost", "javfree",
}

# State reload interval (seconds) — how often the proxy re-reads the shared file
STATE_RELOAD_INTERVAL = 5


# ── DNS packet helpers ──────────────────────────────────────────────

def _parse_domain_from_query(data: bytes) -> Optional[str]:
    """Extract the queried domain name from a raw DNS query packet.

    DNS question format after the 12-byte header:
        QNAME: sequence of length-prefixed labels, terminated by 0x00
        QTYPE: 2 bytes
        QCLASS: 2 bytes

    Safe against malformed packets: validates label lengths, rejects
    compression pointers (not expected in questions), and checks bounds.
    """
    try:
        offset = 12  # skip header
        if offset >= len(data):
            return None
        labels = []
        while offset < len(data):
            length = data[offset]
            if length == 0:
                break
            # Compression pointer (>= 192) or reserved (64-191): unexpected in question
            if length >= 64:
                return None
            offset += 1
            if offset + length > len(data):
                return None  # truncated packet
            labels.append(data[offset:offset + length].decode("ascii", errors="replace"))
            offset += length
        return ".".join(labels).lower() if labels else None
    except Exception:
        return None


def _build_blocked_response(query: bytes) -> bytes:
    """Build a DNS response that resolves to 0.0.0.0 (A) or :: (AAAA).

    We copy the query header, flip the QR bit (response), set answer count
    to 1, copy the question section, and append a null-address record.
    Handles both A and AAAA query types correctly.
    """
    if len(query) < 12:
        return query

    # Parse the question section to find its end (with safety checks)
    offset = 12
    while offset < len(query):
        length = query[offset]
        if length == 0:
            break
        if length >= 64:
            # Compression pointer or reserved — can't safely parse
            return query
        if offset + 1 + length >= len(query):
            return query  # truncated
        offset += length + 1
    offset += 1  # skip null terminator
    if offset + 4 > len(query):
        return query  # truncated
    # Read QTYPE before advancing past it
    qtype = struct.unpack("!H", query[offset:offset + 2])[0]
    offset += 4  # skip QTYPE + QCLASS
    question_end = offset

    # Build response header
    txn_id = query[:2]
    flags = struct.pack("!H", 0x8580)  # QR=1, AA=1, RD=1, RA=1
    qdcount = struct.pack("!H", 1)
    ancount = struct.pack("!H", 1)
    nscount = struct.pack("!H", 0)
    arcount = struct.pack("!H", 0)

    header = txn_id + flags + qdcount + ancount + nscount + arcount

    # Copy question section from original query
    question = query[12:question_end]

    # Build answer section — match query type
    # Name pointer to question name (0xC00C = pointer to offset 12)
    answer = struct.pack("!H", 0xC00C)
    if qtype == 28:  # AAAA
        answer += struct.pack("!H", 28)     # TYPE AAAA
        answer += struct.pack("!H", 1)      # CLASS IN
        answer += struct.pack("!I", 60)     # TTL 60 seconds
        answer += struct.pack("!H", 16)     # RDLENGTH 16 bytes
        answer += b'\x00' * 16             # :: (all zeros IPv6)
    else:  # A (type 1) or fallback
        answer += struct.pack("!H", 1)      # TYPE A
        answer += struct.pack("!H", 1)      # CLASS IN
        answer += struct.pack("!I", 60)     # TTL 60 seconds
        answer += struct.pack("!H", 4)      # RDLENGTH 4 bytes
        answer += socket.inet_aton("0.0.0.0")  # RDATA

    return header + question + answer


def _get_query_type(data: bytes) -> Optional[int]:
    """Extract QTYPE from a DNS query packet (with safe bounds checking)."""
    try:
        offset = 12
        while offset < len(data):
            length = data[offset]
            if length == 0:
                break
            if length >= 64:
                return None  # compression pointer or reserved
            if offset + 1 + length > len(data):
                return None  # truncated
            offset += length + 1
        offset += 1  # null terminator
        if offset + 2 <= len(data):
            return struct.unpack("!H", data[offset:offset + 2])[0]
    except Exception:
        pass
    return None


# ── Domain heuristics ───────────────────────────────────────────────

def _domain_looks_suspicious(domain: str) -> bool:
    """Check if domain name contains known adult keywords."""
    parts = domain.lower().rsplit(".", 1)[0]  # strip TLD
    for pattern in _SUSPICIOUS_PATTERNS:
        if pattern in parts:
            return True
    for kw in _SUSPICIOUS_KEYWORDS:
        if kw in parts:
            return True
    return False


# ── Shared state ────────────────────────────────────────────────────

def _read_proxy_state() -> dict:
    """Read shared state written by the main process."""
    try:
        if _DNS_STATE_FILE.exists():
            return json.loads(_DNS_STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


# ── DNS proxy subprocess ───────────────────────────────────────────

def _run_dns_proxy() -> None:
    """Entry point for the DNS proxy subprocess (runs as root)."""
    # Suppress crash reporter
    try:
        import resource as res
        res.setrlimit(res.RLIMIT_CORE, (0, 0))
        signal.signal(signal.SIGABRT, signal.SIG_IGN)
    except Exception:
        pass

    # Write PID file
    _APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _DNS_PID_FILE.write_text(str(os.getpid()))

    # Set up logging to file
    log_file = open(_DNS_LOG_FILE, "a")

    def log(msg: str) -> None:
        line = f"[DNS] {msg}"
        print(line, flush=True)
        try:
            log_file.write(line + "\n")
            log_file.flush()
        except Exception:
            pass

    # Bind UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass  # SO_REUSEPORT not available on all platforms
    try:
        sock.bind((PROXY_HOST, PROXY_PORT))
    except PermissionError:
        log(f"Cannot bind to port {PROXY_PORT} — root privileges required")
        log_file.close()
        return
    except OSError as e:
        log(f"Cannot bind to port {PROXY_PORT}: {e}")
        log_file.close()
        return

    sock.settimeout(1.0)  # allow periodic state reloads
    log(f"DNS proxy listening on {PROXY_HOST}:{PROXY_PORT}")

    # Load initial state
    blocked_sites: Set[str] = set()
    always_blocked_sites: Set[str] = set()
    heuristic_enabled = True
    is_session_blocking = False
    last_state_load = 0.0
    block_count = 0

    def reload_state() -> None:
        nonlocal blocked_sites, always_blocked_sites, heuristic_enabled
        nonlocal is_session_blocking, last_state_load
        state = _read_proxy_state()
        blocked_sites = set(s.lower() for s in state.get("blocked_sites", []))
        always_blocked_sites = set(s.lower() for s in state.get("always_blocked_sites", []))
        heuristic_enabled = state.get("heuristic_enabled", True)
        is_session_blocking = state.get("is_session_blocking", False)
        last_state_load = time.time()

    reload_state()

    def _matches_blocklist(domain: str, blocklist: Set[str]) -> bool:
        """Check if domain or any parent domain is in the blocklist.

        Handles subdomains: cdn.pornhub.com matches pornhub.com.
        """
        d = domain
        while d:
            if d in blocklist:
                return True
            parts = d.split(".", 1)
            if len(parts) < 2:
                break
            d = parts[1]
        return False

    def should_block(domain: str) -> Tuple[bool, str]:
        """Check if a domain should be blocked.

        Returns (should_block, reason).
        """
        d = domain.lower().rstrip(".")

        # Always-blocked (adult sites) — includes subdomain matching
        if _matches_blocklist(d, always_blocked_sites):
            return True, "always_blocked"

        # Session-blocked (only during work sessions) — includes subdomain matching
        if is_session_blocking and _matches_blocklist(d, blocked_sites):
            return True, "session_blocked"

        # Domain-name heuristics (catch unknown NSFW sites)
        if heuristic_enabled and _domain_looks_suspicious(d):
            return True, "heuristic"

        return False, ""

    def forward_query(data: bytes) -> Optional[bytes]:
        """Forward a DNS query to upstream and return the response."""
        for upstream in UPSTREAM_DNS:
            try:
                fwd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                fwd_sock.settimeout(UPSTREAM_TIMEOUT)
                fwd_sock.sendto(data, (upstream, UPSTREAM_PORT))
                response, _ = fwd_sock.recvfrom(4096)
                fwd_sock.close()
                return response
            except (socket.timeout, OSError):
                try:
                    fwd_sock.close()
                except Exception:
                    pass
                continue
        return None

    # Handle graceful shutdown
    running = True

    def shutdown_handler(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    log(f"Ready. Blocking {len(always_blocked_sites)} adult sites, "
        f"{len(blocked_sites)} session sites, heuristic={'on' if heuristic_enabled else 'off'}")

    while running:
        # Reload state periodically
        if time.time() - last_state_load > STATE_RELOAD_INTERVAL:
            reload_state()

        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            continue

        domain = _parse_domain_from_query(data)
        if domain is None:
            # Can't parse — forward as-is
            response = forward_query(data)
            if response:
                sock.sendto(response, addr)
            continue

        # Only block A and AAAA queries (types 1 and 28)
        qtype = _get_query_type(data)
        if qtype not in (1, 28, None):
            response = forward_query(data)
            if response:
                sock.sendto(response, addr)
            continue

        blocked, reason = should_block(domain)
        if blocked:
            block_count += 1
            if block_count <= 50 or block_count % 100 == 0:
                log(f"BLOCKED ({reason}): {domain} [#{block_count}]")
            response = _build_blocked_response(data)
            sock.sendto(response, addr)
        else:
            response = forward_query(data)
            if response:
                sock.sendto(response, addr)

    log("DNS proxy shutting down")
    sock.close()
    log_file.close()
    try:
        _DNS_PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ── DNS configuration manager (runs in main process) ───────────────

def _run_with_admin(command: str) -> subprocess.CompletedProcess:
    """Run a shell command with administrator privileges using osascript."""
    escaped = command.replace("\\", "\\\\").replace('"', '\\"')
    return subprocess.run(
        [
            "osascript", "-e",
            f'do shell script "{escaped}" with administrator privileges',
        ],
        capture_output=True,
        text=True,
    )


def _get_network_services() -> List[str]:
    """Get all active network service names."""
    try:
        result = subprocess.run(
            ["networksetup", "-listallnetworkservices"],
            capture_output=True, text=True,
        )
        services = []
        for line in result.stdout.strip().split("\n")[1:]:
            line = line.strip()
            if line and not line.startswith("*"):
                services.append(line)
        return services
    except Exception:
        return []


def _get_current_dns(service: str) -> List[str]:
    """Get current DNS servers for a network service."""
    try:
        result = subprocess.run(
            ["networksetup", "-getdnsservers", service],
            capture_output=True, text=True,
        )
        output = result.stdout.strip()
        if "There aren't any DNS Servers" in output:
            return []  # using DHCP defaults
        return [line.strip() for line in output.split("\n") if line.strip()]
    except Exception:
        return []


class DNSConfigManager:
    """Manages system DNS settings with safety guarantees."""

    def __init__(self):
        self._original_dns: Dict[str, List[str]] = {}

    def save_original_dns(self) -> None:
        """Save current DNS settings to disk for crash recovery."""
        services = _get_network_services()
        original = {}
        for service in services:
            dns = _get_current_dns(service)
            original[service] = dns

        self._original_dns = original
        _APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        _DNS_ORIGINAL_FILE.write_text(json.dumps(original, indent=2))
        print(f"[DNS] Saved original DNS for {len(original)} services")

    def set_proxy_dns(self) -> bool:
        """Set system DNS to use our proxy with a fallback.

        Sets DNS to ["127.0.0.1", "8.8.8.8"] for all services.
        The fallback ensures internet works even if proxy is down.
        """
        services = _get_network_services()
        if not services:
            print("[DNS] No network services found")
            return False

        success = False
        for service in services:
            current = _get_current_dns(service)
            # Skip if already set to our proxy
            if current and current[0] == PROXY_HOST:
                success = True
                continue

            result = _run_with_admin(
                f'networksetup -setdnsservers {shlex.quote(service)} {PROXY_HOST} 8.8.8.8'
            )
            if result.returncode == 0:
                print(f"[DNS] Set DNS for '{service}' -> [{PROXY_HOST}, 8.8.8.8]")
                success = True
            else:
                print(f"[DNS] Failed to set DNS for '{service}': {result.stderr.strip()}")

        return success

    def restore_original_dns(self) -> bool:
        """Restore original DNS settings from saved file."""
        # Try in-memory first, then disk
        original = self._original_dns
        if not original:
            try:
                if _DNS_ORIGINAL_FILE.exists():
                    original = json.loads(_DNS_ORIGINAL_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        if not original:
            # Fallback: just clear DNS (revert to DHCP)
            print("[DNS] No saved DNS settings — reverting to DHCP defaults")
            return self._clear_dns_all_services()

        success = False
        for service, dns_servers in original.items():
            svc = shlex.quote(service)
            if dns_servers:
                servers_str = " ".join(shlex.quote(s) for s in dns_servers)
                result = _run_with_admin(
                    f'networksetup -setdnsservers {svc} {servers_str}'
                )
            else:
                # Was using DHCP defaults — clear custom DNS
                result = _run_with_admin(
                    f'networksetup -setdnsservers {svc} empty'
                )

            if result.returncode == 0:
                print(f"[DNS] Restored DNS for '{service}'")
                success = True
            else:
                print(f"[DNS] Failed to restore DNS for '{service}': {result.stderr.strip()}")

        # Clean up saved file
        try:
            _DNS_ORIGINAL_FILE.unlink(missing_ok=True)
        except Exception:
            pass

        return success

    def _clear_dns_all_services(self) -> bool:
        """Clear custom DNS for all services (revert to DHCP)."""
        services = _get_network_services()
        success = False
        for service in services:
            result = _run_with_admin(
                f'networksetup -setdnsservers {shlex.quote(service)} empty'
            )
            if result.returncode == 0:
                success = True
        return success


# ── Main-process controller ─────────────────────────────────────────

class DNSProxy:
    """
    Manages the DNS proxy subprocess and system DNS configuration.

    Lifecycle:
      1. start() — launches proxy subprocess, waits for it to bind, sets DNS
      2. update_state() — writes new blocklists to shared state file
      3. stop() — restores DNS, kills proxy subprocess
    """

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._running = False
        self._dns_config = DNSConfigManager()

        # Cached state to write to shared file
        self._state = {
            "blocked_sites": [],
            "always_blocked_sites": [],
            "heuristic_enabled": True,
            "is_session_blocking": False,
        }
        self._state_dirty = True

    def start(self) -> bool:
        """Start the DNS proxy and configure system DNS.

        Returns True if proxy is running and DNS is configured.
        """
        if self._running:
            return True

        _APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Step 1: Save original DNS settings BEFORE changing anything
        self._dns_config.save_original_dns()

        # Step 2: Write initial state for proxy to read
        self._flush_state()

        # Step 3: Kill any stale proxy process
        self._kill_stale_proxy()

        # Step 4: Launch proxy subprocess with root privileges
        proxy_script = str(Path(__file__).resolve())
        launch_cmd = (
            f'{sys.executable} "{proxy_script}" --run-proxy '
            f'> /dev/null 2>&1 & echo $!'
        )

        try:
            result = _run_with_admin(launch_cmd)
            if result.returncode != 0:
                print(f"[DNS] Failed to launch proxy: {result.stderr.strip()}")
                return False
        except Exception as e:
            print(f"[DNS] Failed to launch proxy: {e}")
            return False

        # Step 5: Wait for proxy to start listening (verify it works)
        if not self._wait_for_proxy(timeout=5.0):
            print("[DNS] Proxy did not start in time — aborting")
            self._kill_stale_proxy()
            return False

        # Step 6: NOW set system DNS (proxy is confirmed working)
        if not self._dns_config.set_proxy_dns():
            print("[DNS] Failed to configure system DNS — aborting")
            self._kill_stale_proxy()
            return False

        self._running = True
        print("[DNS] Proxy started and system DNS configured")
        return True

    def stop(self) -> None:
        """Stop the DNS proxy and restore original DNS settings."""
        if not self._running:
            return

        self._running = False

        # Step 1: Restore DNS FIRST (so internet works immediately)
        self._dns_config.restore_original_dns()

        # Step 2: Kill proxy subprocess
        self._kill_stale_proxy()

        # Clean up state file
        try:
            _DNS_STATE_FILE.unlink(missing_ok=True)
        except Exception:
            pass

        print("[DNS] Proxy stopped and DNS restored")

    def is_running(self) -> bool:
        """Check if proxy is running."""
        return self._running

    def set_blocked_sites(self, sites: Set[str]) -> None:
        """Update session-blocked sites."""
        self._state["blocked_sites"] = sorted(sites)
        self._state_dirty = True

    def set_always_blocked_sites(self, sites: Set[str]) -> None:
        """Update always-blocked (adult) sites."""
        self._state["always_blocked_sites"] = sorted(sites)
        self._state_dirty = True

    def set_session_blocking(self, active: bool) -> None:
        """Set whether session-based blocking is active."""
        self._state["is_session_blocking"] = active
        self._state_dirty = True

    def set_heuristic_enabled(self, enabled: bool) -> None:
        """Enable/disable domain-name heuristic blocking."""
        self._state["heuristic_enabled"] = enabled
        self._state_dirty = True

    def add_always_blocked_site(self, domain: str) -> None:
        """Add a single domain to always-blocked list."""
        sites = set(self._state.get("always_blocked_sites", []))
        domain = domain.lower().strip()
        if domain and domain not in sites:
            sites.add(domain)
            self._state["always_blocked_sites"] = sorted(sites)
            self._state_dirty = True

    def flush_state(self) -> None:
        """Write state to disk if dirty. Call periodically from main thread."""
        if self._state_dirty:
            self._flush_state()

    def _flush_state(self) -> None:
        """Write current state to shared file (atomic via temp+rename)."""
        try:
            tmp = _DNS_STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state))
            tmp.rename(_DNS_STATE_FILE)
            self._state_dirty = False
        except OSError as e:
            print(f"[DNS] Failed to write state: {e}")

    def _wait_for_proxy(self, timeout: float = 5.0) -> bool:
        """Wait for the proxy to start responding to DNS queries."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                # Send a test DNS query for "test.local"
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(1.0)
                # Minimal DNS query for "test.local" (type A, class IN)
                query = (
                    b'\x12\x34'      # transaction ID
                    b'\x01\x00'      # flags: standard query, RD=1
                    b'\x00\x01'      # 1 question
                    b'\x00\x00'      # 0 answers
                    b'\x00\x00'      # 0 authority
                    b'\x00\x00'      # 0 additional
                    b'\x04test'      # "test"
                    b'\x05local'     # "local"
                    b'\x00'          # end of name
                    b'\x00\x01'      # type A
                    b'\x00\x01'      # class IN
                )
                sock.sendto(query, (PROXY_HOST, PROXY_PORT))
                sock.recvfrom(4096)
                sock.close()
                return True
            except (socket.timeout, OSError):
                try:
                    sock.close()
                except Exception:
                    pass
                time.sleep(0.5)
        return False

    def _kill_stale_proxy(self) -> None:
        """Kill any existing DNS proxy process (safely — never kills mDNSResponder)."""
        # Try PID file first — this is the safest method
        try:
            if _DNS_PID_FILE.exists():
                pid = int(_DNS_PID_FILE.read_text().strip())
                # Verify it's actually our proxy before killing
                try:
                    import psutil
                    proc = psutil.Process(pid)
                    cmdline = " ".join(proc.cmdline())
                    if "dns_proxy" in cmdline and "--run-proxy" in cmdline:
                        _run_with_admin(f"kill {pid}")
                        time.sleep(0.3)
                except (ImportError, Exception):
                    # psutil not available — trust PID file
                    _run_with_admin(f"kill {pid}")
                    time.sleep(0.3)
        except Exception:
            pass

        # Scan port 53 but ONLY kill processes matching our proxy
        try:
            import psutil
            result = subprocess.run(
                ["lsof", "-ti", f":{PROXY_PORT}"],
                capture_output=True, text=True,
            )
            my_pid = os.getpid()
            for line in result.stdout.strip().splitlines():
                try:
                    pid = int(line.strip())
                    if pid == my_pid:
                        continue
                    proc = psutil.Process(pid)
                    cmdline = " ".join(proc.cmdline())
                    # Only kill if it's our dns_proxy script
                    if "dns_proxy" in cmdline and "--run-proxy" in cmdline:
                        _run_with_admin(f"kill {pid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
                    pass
        except ImportError:
            pass  # psutil not available — rely on PID file only
        except Exception:
            pass

        try:
            _DNS_PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass


# ── Static recovery function (for process guard) ───────────────────

def restore_dns_settings() -> bool:
    """Restore original DNS settings from saved file.

    Called by the process guard or emergency recovery when the main app
    crashes without cleaning up DNS settings.
    """
    mgr = DNSConfigManager()
    return mgr.restore_original_dns()


# ── Subprocess entry point ──────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-proxy", action="store_true",
                        help="Run the DNS proxy server")
    args = parser.parse_args()

    if args.run_proxy:
        _run_dns_proxy()
