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

# Shared state directory.  When launched by the system launchd
# daemon (root), the plist sets PRODUCTIVITY_TIMER_DATA_DIR so the
# daemon points at the user's home dir instead of /var/root.
_data_dir_env = os.environ.get("PRODUCTIVITY_TIMER_DATA_DIR")
_APP_DATA_DIR = (
    Path(_data_dir_env)
    if _data_dir_env
    else Path.home() / "Library" / "Application Support" / "ProductivityTimer"
)
_DNS_STATE_FILE = _APP_DATA_DIR / "dns_proxy_state.json"
_DNS_ORIGINAL_FILE = _APP_DATA_DIR / "dns_original_settings.json"
_DNS_PID_FILE = _APP_DATA_DIR / "dns_proxy.pid"
_DNS_LOG_FILE = _APP_DATA_DIR / "dns_proxy.log"

# launchd integration — running the proxy as a system daemon means we
# only ask for admin once (at install time) and the proxy survives
# crashes/reboots without re-prompting.
_LAUNCHD_LABEL = "com.productivity.dnsproxy"
_LAUNCHD_PLIST_PATH = Path("/Library/LaunchDaemons") / f"{_LAUNCHD_LABEL}.plist"
_LAUNCHD_LOG_PATH = Path("/var/log/productivity-dnsproxy.log")
_LAUNCHD_ERR_PATH = Path("/var/log/productivity-dnsproxy.err")
# Daemon script gets copied here at install time. macOS TCC blocks
# root processes from reading files inside ~/Documents (and other
# protected zones), so we can't point launchd directly at the source
# tree — we stage a copy in a non-protected system path.
_LAUNCHD_SCRIPT_PATH = Path("/Library/Application Support/com.productivity.dnsproxy/dns_proxy.py")

# PF (Packet Filter) integration — forces ALL outbound DNS through
# the local proxy regardless of what an app or VPN is configured
# to use.  Defeats most "DNS over HTTPS off-by-default" leaks; loses
# to system extensions that intercept at the socket layer (Cisco
# AnyConnect, etc.) but still helps for direct VPN tunnels.
_PF_ANCHOR_NAME = "com.productivity.dnsproxy"
_PF_ANCHOR_PATH = Path("/etc/pf.anchors") / _PF_ANCHOR_NAME
_PF_CONF_PATH = Path("/etc/pf.conf")
_PF_MARKER_START = "# PRODUCTIVITY_TIMER_DNSPROXY_ANCHOR_START"
_PF_MARKER_END = "# PRODUCTIVITY_TIMER_DNSPROXY_ANCHOR_END"

# Per-domain DNS routing via /etc/resolver/<domain>.  macOS reads
# these files in libsystem (configd → mDNSResponder), BEFORE any
# Network Extension or VPN tunnel gets a chance to intercept.  A
# file containing `nameserver 127.0.0.1` for a blocked domain
# routes ALL resolution of that domain (and its subdomains)
# through the local DNS proxy, which returns 0.0.0.0 → blocked.
# Survives reboots automatically (configd reads /etc/resolver/ at
# boot).  Bullet-proof against Surfshark + Cisco AnyConnect.
_RESOLVER_DIR = Path("/etc/resolver")
_RESOLVER_MANIFEST = _RESOLVER_DIR / ".productivity-timer-manifest"

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


# ── launchd LaunchDaemon integration ────────────────────────────────

def _build_launchd_plist(python_exec: str, proxy_script: str, data_dir: str) -> str:
    """Build the LaunchDaemon plist XML for the DNS proxy."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        '<dict>\n'
        f'    <key>Label</key>\n    <string>{_LAUNCHD_LABEL}</string>\n'
        '    <key>ProgramArguments</key>\n    <array>\n'
        f'        <string>{python_exec}</string>\n'
        f'        <string>{proxy_script}</string>\n'
        '        <string>--run-proxy</string>\n'
        '    </array>\n'
        '    <key>EnvironmentVariables</key>\n    <dict>\n'
        '        <key>PRODUCTIVITY_TIMER_DATA_DIR</key>\n'
        f'        <string>{data_dir}</string>\n'
        '    </dict>\n'
        '    <key>RunAtLoad</key>\n    <true/>\n'
        '    <key>KeepAlive</key>\n    <true/>\n'
        f'    <key>StandardOutPath</key>\n    <string>{_LAUNCHD_LOG_PATH}</string>\n'
        f'    <key>StandardErrorPath</key>\n    <string>{_LAUNCHD_ERR_PATH}</string>\n'
        '    <key>ThrottleInterval</key>\n    <integer>10</integer>\n'
        '</dict>\n</plist>\n'
    )


def is_launchd_plist_installed() -> bool:
    """True iff the LaunchDaemon plist exists on disk."""
    return _LAUNCHD_PLIST_PATH.exists()


def is_launchd_proxy_loaded() -> bool:
    """True iff launchctl knows about the daemon (loaded into the system domain)."""
    try:
        result = subprocess.run(
            ["launchctl", "print", f"system/{_LAUNCHD_LABEL}"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def install_launchd_proxy() -> Tuple[bool, str]:
    """Install the LaunchDaemon plist and bootstrap it.

    Single osascript admin prompt covers: stage the proxy script in a
    non-TCC-protected location, copy plist into /Library/LaunchDaemons,
    fix ownership/perms, bootstrap + enable + kickstart, and create
    log files.

    Why we copy the script: macOS TCC blocks root daemons from
    reading files in protected user zones (Documents, Desktop,
    Downloads, iCloud).  Pointing launchd at the source tree fails
    with "Operation not permitted" until Full Disk Access is granted
    for the python interpreter.  Staging a copy under
    /Library/Application Support sidesteps the prompt entirely.
    """
    import tempfile

    python_exec = sys.executable
    src_script = Path(__file__).resolve()
    staged_script = str(_LAUNCHD_SCRIPT_PATH)
    data_dir = str(_APP_DATA_DIR)

    plist_xml = _build_launchd_plist(python_exec, staged_script, data_dir)

    # Stage the script via /tmp so the admin `cp` is reading from a
    # non-TCC-protected path. macOS blocks even root processes from
    # reading inside ~/Documents without Full Disk Access; reading
    # the source as the user (no TCC restriction on self-owned files)
    # and writing into /tmp dodges that.
    try:
        script_bytes = src_script.read_bytes()
    except OSError as e:
        return False, f"Failed to read source script: {e}"

    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.plist', delete=False, encoding='utf-8', dir='/tmp',
        ) as tmp:
            tmp.write(plist_xml)
            tmp_plist = tmp.name
        with tempfile.NamedTemporaryFile(
            mode='wb', suffix='.py', delete=False, dir='/tmp',
        ) as tmp:
            tmp.write(script_bytes)
            tmp_script = tmp.name
    except OSError as e:
        return False, f"Failed to stage files: {e}"

    plist_target = shlex.quote(str(_LAUNCHD_PLIST_PATH))
    script_target = shlex.quote(staged_script)
    script_dir = shlex.quote(str(_LAUNCHD_SCRIPT_PATH.parent))
    label = shlex.quote(f"system/{_LAUNCHD_LABEL}")

    cmd = " && ".join([
        f"mkdir -p {script_dir}",
        f"cp {shlex.quote(tmp_script)} {script_target}",
        f"chown root:wheel {script_target}",
        f"chmod 0755 {script_target}",
        f"cp {shlex.quote(tmp_plist)} {plist_target}",
        f"chown root:wheel {plist_target}",
        f"chmod 0644 {plist_target}",
        f"touch {shlex.quote(str(_LAUNCHD_LOG_PATH))} {shlex.quote(str(_LAUNCHD_ERR_PATH))}",
        # bootout if a previous version is loaded so bootstrap doesn't fail
        f"launchctl bootout {label} 2>/dev/null; true",
        f"launchctl bootstrap system {plist_target}",
        f"launchctl enable {label}",
        f"launchctl kickstart -k {label}",
        f"rm -f {shlex.quote(tmp_plist)} {shlex.quote(tmp_script)}",
    ])
    result = _run_with_admin(cmd)
    if result.returncode != 0:
        return False, f"Install failed: {result.stderr.strip() or result.stdout.strip()}"
    return True, f"Installed {_LAUNCHD_PLIST_PATH} (script staged at {_LAUNCHD_SCRIPT_PATH})"


def uninstall_launchd_proxy() -> Tuple[bool, str]:
    """Bootout the daemon, delete the plist + staged script (one prompt)."""
    plist_target = shlex.quote(str(_LAUNCHD_PLIST_PATH))
    script_target = shlex.quote(str(_LAUNCHD_SCRIPT_PATH))
    script_dir = shlex.quote(str(_LAUNCHD_SCRIPT_PATH.parent))
    label = shlex.quote(f"system/{_LAUNCHD_LABEL}")
    cmd = " ; ".join([
        f"launchctl bootout {label} 2>/dev/null; true",
        f"rm -f {plist_target}",
        f"rm -f {script_target}",
        f"rmdir {script_dir} 2>/dev/null; true",
    ])
    result = _run_with_admin(cmd)
    if result.returncode != 0:
        return False, f"Uninstall failed: {result.stderr.strip() or result.stdout.strip()}"
    return True, "Uninstalled"


# ── PF (Packet Filter) DNS redirect ────────────────────────────────

def _build_pf_anchor() -> str:
    """Generate PF anchor rules for transparent DNS redirect.

    Caveat — macOS PF limitation:
      On macOS, `rdr` only intercepts packets that transit through
      the host's PF layer.  Locally-originated outbound DNS from
      user processes is hooked at the socket layer (BSD-side) and
      doesn't traverse rdr.  The OpenBSD escape hatch — filter-
      side `pass out ... route-to (lo0 127.0.0.1)` — is a syntax
      error on macOS PF (Apple's PF fork pre-dates route-to in
      user anchors).
      As a result this anchor only blocks DNS *forwarded through*
      this Mac (e.g. acting as a router or hotspot) — useful in
      that niche but a no-op for the common client-side case.
      Disable the relevant Network Extensions (Cisco AnyConnect
      socket filter, VPN packet tunnel) if you need /etc/hosts to
      apply system-wide.
    """
    upstream_list = ", ".join(UPSTREAM_DNS)
    return (
        "# Productivity Timer — DNS rdr (transit-only).\n"
        "# Limitation: macOS PF rdr does not catch locally-originated\n"
        "# DNS traffic; this anchor only intercepts forwarded DNS\n"
        "# (this Mac as a router/hotspot).  See _build_pf_anchor doc.\n"
        "\n"
        f"table <productivity_upstream_dns> persist {{ {upstream_list} }}\n"
        "\n"
        "no rdr proto { tcp, udp } from any to <productivity_upstream_dns> port 53\n"
        "no rdr proto { tcp, udp } from any to 127.0.0.1 port 53\n"
        "rdr pass inet proto udp from any to any port 53 -> 127.0.0.1 port 53\n"
        "rdr pass inet proto tcp from any to any port 53 -> 127.0.0.1 port 53\n"
    )


def _pf_conf_with_marker_block(current: str, snippet: str) -> str:
    """Insert (or replace) our marker block in pf.conf at the right spot.

    PF requires rules in a strict order: options → normalization →
    queueing → translation (rdr/nat) → filtering.  Our `rdr-anchor`
    + `load anchor` lines must land in the translation section,
    BEFORE any `anchor` (filter) declaration.  We insert immediately
    after the last existing `rdr-anchor` line, falling back to just
    before the first filter `anchor` line, falling back to append.
    """
    lines = current.split("\n")
    out = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if stripped == _PF_MARKER_START:
            in_block = True
            continue
        if stripped == _PF_MARKER_END:
            in_block = False
            continue
        if not in_block:
            out.append(line)

    if not snippet.strip():
        return "\n".join(out).rstrip() + "\n"

    insert_at = None
    last_rdr_anchor = None
    first_filter_anchor = None
    for i, line in enumerate(out):
        bare = line.lstrip()
        if bare.startswith("rdr-anchor") or bare.startswith("nat-anchor"):
            last_rdr_anchor = i
        # `anchor "name"` at top-level (not nat-/rdr-/scrub-/load anchor)
        # is the filter-anchor declaration.  load-anchor is a parser
        # directive and doesn't define a filter slot.
        if bare.startswith("anchor ") and first_filter_anchor is None:
            first_filter_anchor = i

    if last_rdr_anchor is not None:
        insert_at = last_rdr_anchor + 1
    elif first_filter_anchor is not None:
        insert_at = first_filter_anchor
    else:
        insert_at = len(out)

    snippet_lines = snippet.strip().split("\n")
    new_lines = out[:insert_at] + snippet_lines + out[insert_at:]
    return "\n".join(new_lines).rstrip() + "\n"


def is_pf_redirect_installed() -> bool:
    """True iff anchor file exists AND pf.conf references it."""
    try:
        if not _PF_ANCHOR_PATH.exists():
            return False
        return _PF_MARKER_START in _PF_CONF_PATH.read_text()
    except OSError:
        return False


def is_pf_redirect_loaded() -> bool:
    """True iff pfctl reports our anchor's rdr rules are active.

    Requires root to query, so this only succeeds when run from
    a privileged context.  From the user's app it's still useful
    via osascript-shell admin, but here we just try without and
    return False on permission denied.
    """
    try:
        result = subprocess.run(
            ["pfctl", "-s", "nat", "-a", _PF_ANCHOR_NAME],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and "127.0.0.1" in result.stdout
    except Exception:
        return False


def install_pf_redirect() -> Tuple[bool, str]:
    """Install the PF anchor + reference in /etc/pf.conf, reload PF.

    Single osascript admin prompt covers everything.  Persistent
    across reboots because /etc/pf.conf is loaded automatically by
    launchd's com.apple.pfctl service.
    """
    import tempfile

    anchor_content = _build_pf_anchor()

    try:
        current_pf = _PF_CONF_PATH.read_text()
    except OSError as e:
        return False, f"Failed to read /etc/pf.conf: {e}"

    # rdr-anchor only (no filter anchor) — see _build_pf_anchor for
    # why filter rules can't carry their weight on macOS PF.
    snippet = (
        f"{_PF_MARKER_START}\n"
        f'rdr-anchor "{_PF_ANCHOR_NAME}"\n'
        f'load anchor "{_PF_ANCHOR_NAME}" from "{_PF_ANCHOR_PATH}"\n'
        f"{_PF_MARKER_END}"
    )
    new_pf = _pf_conf_with_marker_block(current_pf, snippet)

    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.pf', delete=False, dir='/tmp', encoding='utf-8',
        ) as tmp:
            tmp.write(anchor_content)
            tmp_anchor = tmp.name
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.pf.conf', delete=False, dir='/tmp', encoding='utf-8',
        ) as tmp:
            tmp.write(new_pf)
            tmp_pfconf = tmp.name
    except OSError as e:
        return False, f"Failed to stage PF files: {e}"

    anchor_target = shlex.quote(str(_PF_ANCHOR_PATH))
    pfconf_target = shlex.quote(str(_PF_CONF_PATH))
    cmd = " && ".join([
        f"cp {shlex.quote(tmp_anchor)} {anchor_target}",
        f"chown root:wheel {anchor_target}",
        f"chmod 0644 {anchor_target}",
        f"cp {shlex.quote(tmp_pfconf)} {pfconf_target}",
        f"chown root:wheel {pfconf_target}",
        f"chmod 0644 {pfconf_target}",
        # First-time enable is idempotent. Suppress noise from already-on.
        "pfctl -E 2>/dev/null; true",
        # Reload main ruleset so anchor reference picks up.
        f"pfctl -f {pfconf_target}",
        f"rm -f {shlex.quote(tmp_anchor)} {shlex.quote(tmp_pfconf)}",
    ])
    result = _run_with_admin(cmd)
    if result.returncode != 0:
        return False, f"PF install failed: {result.stderr.strip() or result.stdout.strip()}"
    return True, f"Installed PF anchor at {_PF_ANCHOR_PATH}"


def _resolver_base_domains(sites: Set[str]) -> Set[str]:
    """Reduce a site list to /etc/resolver/ base domains.

    /etc/resolver/<domain> applies to <domain> AND all subdomains
    (configd reads it for the longest-suffix-match), so explicit
    `www.` variants are redundant — drop them.  Also reject any
    obviously-malformed entry to keep filename writes safe.
    """
    out: Set[str] = set()
    for s in sites:
        s = (s or "").strip().lower()
        if not s:
            continue
        if s.startswith("www."):
            s = s[4:]
        # Filename safety: only normal hostname chars allowed.
        if any(ch in s for ch in "/\\\n\r\0 \t"):
            continue
        if ".." in s:
            continue
        out.add(s)
    return out


def is_resolver_redirect_installed() -> bool:
    """True iff the resolver manifest exists (we've installed before)."""
    try:
        return _RESOLVER_MANIFEST.exists()
    except OSError:
        return False


def install_resolver_redirect(sites: Set[str]) -> Tuple[bool, str]:
    """Install /etc/resolver/<domain> entries pointing at the local proxy.

    One file per blocked domain, each containing:

        nameserver 127.0.0.1

    A manifest file lists every entry we created, so uninstall
    only removes our files (never disturbs unrelated /etc/resolver/
    entries from other tools).

    Single osascript admin prompt creates the whole set + flushes
    the resolver cache.
    """
    import tempfile

    domains = _resolver_base_domains(sites)
    if not domains:
        return False, "no domains to install"

    # Build an installer shell script — too many domains for a
    # one-line command, so stage in /tmp and exec via admin.
    sorted_domains = sorted(domains)
    script_parts = [
        "#!/bin/bash",
        "set -eu",
        f"mkdir -p {shlex.quote(str(_RESOLVER_DIR))}",
    ]
    for d in sorted_domains:
        target = shlex.quote(str(_RESOLVER_DIR / d))
        script_parts.append(f"printf 'nameserver 127.0.0.1\\n' > {target}")
        script_parts.append(f"chmod 0644 {target}")
    # Manifest with one domain per line — used by uninstall.
    manifest_content = "\n".join(sorted_domains) + "\n"
    # Ship the manifest via heredoc to avoid a separate file copy.
    script_parts.append(
        f"cat > {shlex.quote(str(_RESOLVER_MANIFEST))} <<'PRODUCTIVITY_MANIFEST_EOF'\n"
        f"{manifest_content}"
        f"PRODUCTIVITY_MANIFEST_EOF"
    )
    script_parts.append(f"chmod 0644 {shlex.quote(str(_RESOLVER_MANIFEST))}")
    script_parts.append("dscacheutil -flushcache")
    script_parts.append("killall -HUP mDNSResponder 2>/dev/null || true")

    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sh', delete=False, dir='/tmp', encoding='utf-8',
        ) as tmp:
            tmp.write("\n".join(script_parts) + "\n")
            tmp_script = tmp.name
        os.chmod(tmp_script, 0o755)
    except OSError as e:
        return False, f"Failed to stage installer: {e}"

    cmd = (
        f"bash {shlex.quote(tmp_script)} && "
        f"rm -f {shlex.quote(tmp_script)}"
    )
    result = _run_with_admin(cmd)
    if result.returncode != 0:
        return False, f"Resolver install failed: {result.stderr.strip() or result.stdout.strip()}"
    return True, f"Installed {len(domains)} /etc/resolver/ files"


def update_resolver_redirect(sites: Set[str]) -> Tuple[bool, str]:
    """Reconcile /etc/resolver/ files with the current `sites` set.

    Same single-prompt flow as install, but only writes the diff:
    creates files for newly-added domains, removes files for
    domains no longer in the set, refreshes the manifest.  No-ops
    when the on-disk manifest already matches.
    """
    desired = _resolver_base_domains(sites)
    if not desired:
        # Nothing to install — fall through to uninstall path.
        return uninstall_resolver_redirect()

    if not is_resolver_redirect_installed():
        return install_resolver_redirect(sites)

    try:
        existing = set(
            line.strip() for line in _RESOLVER_MANIFEST.read_text().splitlines()
            if line.strip()
        )
    except OSError as e:
        # Manifest unreadable — fall back to full reinstall.
        return install_resolver_redirect(sites)

    if existing == desired:
        return True, f"Already in sync ({len(desired)} domains)"

    to_add = sorted(desired - existing)
    to_remove = sorted(existing - desired)

    import tempfile
    script_parts = [
        "#!/bin/bash",
        "set -eu",
        f"mkdir -p {shlex.quote(str(_RESOLVER_DIR))}",
    ]
    for d in to_add:
        target = shlex.quote(str(_RESOLVER_DIR / d))
        script_parts.append(f"printf 'nameserver 127.0.0.1\\n' > {target}")
        script_parts.append(f"chmod 0644 {target}")
    for d in to_remove:
        target = shlex.quote(str(_RESOLVER_DIR / d))
        script_parts.append(f"rm -f {target}")
    manifest_content = "\n".join(sorted(desired)) + "\n"
    script_parts.append(
        f"cat > {shlex.quote(str(_RESOLVER_MANIFEST))} <<'PRODUCTIVITY_MANIFEST_EOF'\n"
        f"{manifest_content}"
        f"PRODUCTIVITY_MANIFEST_EOF"
    )
    script_parts.append(f"chmod 0644 {shlex.quote(str(_RESOLVER_MANIFEST))}")
    script_parts.append("dscacheutil -flushcache")
    script_parts.append("killall -HUP mDNSResponder 2>/dev/null || true")

    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sh', delete=False, dir='/tmp', encoding='utf-8',
        ) as tmp:
            tmp.write("\n".join(script_parts) + "\n")
            tmp_script = tmp.name
        os.chmod(tmp_script, 0o755)
    except OSError as e:
        return False, f"Failed to stage updater: {e}"

    cmd = (
        f"bash {shlex.quote(tmp_script)} && "
        f"rm -f {shlex.quote(tmp_script)}"
    )
    result = _run_with_admin(cmd)
    if result.returncode != 0:
        return False, f"Resolver update failed: {result.stderr.strip() or result.stdout.strip()}"
    return True, f"Updated resolver: +{len(to_add)} -{len(to_remove)}"


def uninstall_resolver_redirect() -> Tuple[bool, str]:
    """Remove every /etc/resolver/ file we created (per the manifest)."""
    if not is_resolver_redirect_installed():
        return True, "not installed"

    try:
        domains = [
            line.strip()
            for line in _RESOLVER_MANIFEST.read_text().splitlines()
            if line.strip()
        ]
    except OSError as e:
        return False, f"Failed to read manifest: {e}"

    script_parts = ["#!/bin/bash", "set -eu"]
    for d in domains:
        if any(ch in d for ch in "/\\\n\r\0 \t") or ".." in d:
            continue
        script_parts.append(f"rm -f {shlex.quote(str(_RESOLVER_DIR / d))}")
    script_parts.append(f"rm -f {shlex.quote(str(_RESOLVER_MANIFEST))}")
    script_parts.append("dscacheutil -flushcache")
    script_parts.append("killall -HUP mDNSResponder 2>/dev/null || true")

    import tempfile
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sh', delete=False, dir='/tmp', encoding='utf-8',
        ) as tmp:
            tmp.write("\n".join(script_parts) + "\n")
            tmp_script = tmp.name
        os.chmod(tmp_script, 0o755)
    except OSError as e:
        return False, f"Failed to stage uninstaller: {e}"

    cmd = (
        f"bash {shlex.quote(tmp_script)} && "
        f"rm -f {shlex.quote(tmp_script)}"
    )
    result = _run_with_admin(cmd)
    if result.returncode != 0:
        return False, f"Resolver uninstall failed: {result.stderr.strip() or result.stdout.strip()}"
    return True, f"Uninstalled {len(domains)} resolver files"


def uninstall_pf_redirect() -> Tuple[bool, str]:
    """Remove PF anchor + pf.conf reference, flush our anchor's rules."""
    import tempfile

    try:
        current_pf = _PF_CONF_PATH.read_text()
    except OSError as e:
        return False, f"Failed to read /etc/pf.conf: {e}"

    new_pf = _pf_conf_with_marker_block(current_pf, "").rstrip() + "\n"

    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.pf.conf', delete=False, dir='/tmp', encoding='utf-8',
        ) as tmp:
            tmp.write(new_pf)
            tmp_pfconf = tmp.name
    except OSError as e:
        return False, f"Failed to stage pf.conf: {e}"

    pfconf_target = shlex.quote(str(_PF_CONF_PATH))
    anchor_target = shlex.quote(str(_PF_ANCHOR_PATH))
    label = shlex.quote(_PF_ANCHOR_NAME)
    cmd = " && ".join([
        f"cp {shlex.quote(tmp_pfconf)} {pfconf_target}",
        f"chown root:wheel {pfconf_target}",
        f"chmod 0644 {pfconf_target}",
        f"rm -f {anchor_target}",
        # Flush our anchor's rdr table; ignore failure if anchor empty.
        f"pfctl -a {label} -F nat 2>/dev/null; true",
        f"pfctl -f {pfconf_target}",
        f"rm -f {shlex.quote(tmp_pfconf)}",
    ])
    result = _run_with_admin(cmd)
    if result.returncode != 0:
        return False, f"PF uninstall failed: {result.stderr.strip() or result.stdout.strip()}"
    return True, "Uninstalled PF redirect"


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

        # If a LaunchDaemon is managing the proxy we don't need to
        # spawn or kill anything — just verify it's listening, then
        # configure system DNS.  No osascript prompt on this path.
        if is_launchd_plist_installed() and is_launchd_proxy_loaded():
            if self._wait_for_proxy(timeout=3.0):
                if not self._dns_config.set_proxy_dns():
                    print("[DNS] launchd proxy up but DNS config failed — aborting")
                    return False
                self._running = True
                print("[DNS] Using launchd-managed proxy")
                return True
            print("[DNS] launchd plist installed but proxy not responding — falling back")

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
        """Stop the DNS proxy and restore original DNS settings.

        Leaves the LaunchDaemon alone if one is installed — it's
        meant to outlive individual app sessions.  Use
        ``uninstall_launchd_proxy()`` to remove the daemon itself.
        """
        if not self._running:
            return

        self._running = False

        # Step 1: Restore DNS FIRST (so internet works immediately)
        self._dns_config.restore_original_dns()

        # Step 2: Kill proxy subprocess only if we own it
        if not is_launchd_plist_installed():
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
                        help="Run the DNS proxy server (subprocess entry point)")
    parser.add_argument("--install-daemon", action="store_true",
                        help="Install LaunchDaemon so the proxy runs at boot")
    parser.add_argument("--uninstall-daemon", action="store_true",
                        help="Remove the LaunchDaemon plist and stop the proxy")
    parser.add_argument("--daemon-status", action="store_true",
                        help="Print whether the LaunchDaemon is installed and loaded")
    parser.add_argument("--install-pf", action="store_true",
                        help="Install PF anchor that redirects all DNS to local proxy")
    parser.add_argument("--uninstall-pf", action="store_true",
                        help="Remove PF anchor + pf.conf reference")
    parser.add_argument("--pf-status", action="store_true",
                        help="Print PF redirect install/loaded state")
    parser.add_argument("--install-resolver", action="store_true",
                        help="Install /etc/resolver/<domain> per blocked site (works through VPN)")
    parser.add_argument("--update-resolver", action="store_true",
                        help="Sync /etc/resolver/ files with the current ADULT_SITES set")
    parser.add_argument("--uninstall-resolver", action="store_true",
                        help="Remove all /etc/resolver/ files we installed")
    parser.add_argument("--resolver-status", action="store_true",
                        help="Print whether resolver redirect is installed")
    args = parser.parse_args()

    if args.run_proxy:
        _run_dns_proxy()
        sys.exit(0)

    if args.daemon_status:
        installed = is_launchd_plist_installed()
        loaded = is_launchd_proxy_loaded() if installed else False
        print(f"plist installed: {installed} ({_LAUNCHD_PLIST_PATH})")
        print(f"loaded:          {loaded}")
        if installed:
            try:
                out = subprocess.run(
                    ["launchctl", "print", f"system/{_LAUNCHD_LABEL}"],
                    capture_output=True, text=True, timeout=5,
                ).stdout
                for line in out.splitlines():
                    if "state" in line or "pid" in line or "last exit" in line.lower():
                        print(f"  {line.strip()}")
            except Exception:
                pass
        sys.exit(0 if (installed and loaded) else 1)

    if args.install_daemon:
        ok, msg = install_launchd_proxy()
        print(msg)
        sys.exit(0 if ok else 1)

    if args.uninstall_daemon:
        ok, msg = uninstall_launchd_proxy()
        print(msg)
        sys.exit(0 if ok else 1)

    if args.pf_status:
        installed = is_pf_redirect_installed()
        loaded = is_pf_redirect_loaded() if installed else False
        print(f"anchor file:     {installed} ({_PF_ANCHOR_PATH})")
        print(f"pf.conf marker:  {installed}")
        print(f"rules loaded:    {loaded}  (requires root to verify)")
        sys.exit(0 if (installed and loaded) else 1)

    if args.install_pf:
        ok, msg = install_pf_redirect()
        print(msg)
        sys.exit(0 if ok else 1)

    if args.uninstall_pf:
        ok, msg = uninstall_pf_redirect()
        print(msg)
        sys.exit(0 if ok else 1)

    if args.resolver_status:
        installed = is_resolver_redirect_installed()
        print(f"manifest:        {installed} ({_RESOLVER_MANIFEST})")
        if installed:
            try:
                domains = [
                    l.strip() for l in _RESOLVER_MANIFEST.read_text().splitlines()
                    if l.strip()
                ]
                print(f"domains tracked: {len(domains)}")
            except OSError:
                pass
        sys.exit(0 if installed else 1)

    if args.install_resolver or args.update_resolver:
        # Lazy import: only needed when running from project root
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from src.data.default_blocklists import get_adult_sites
        sites = get_adult_sites()
        if args.update_resolver:
            ok, msg = update_resolver_redirect(sites)
        else:
            ok, msg = install_resolver_redirect(sites)
        print(msg)
        sys.exit(0 if ok else 1)

    if args.uninstall_resolver:
        ok, msg = uninstall_resolver_redirect()
        print(msg)
        sys.exit(0 if ok else 1)

    parser.print_help()
