"""
DNS cache monitor for system-wide NSFW domain detection.
Works across ALL browsers without requiring an extension.
Polls the Windows DNS cache for newly resolved domains and checks them via AI.
"""

import subprocess
import threading
import time
import re
from typing import Callable, Optional, Set


# Domains to never check (common infrastructure, CDNs, etc.)
SKIP_DOMAINS = {
    'localhost', 'local', 'wpad', 'isatap',
}

SKIP_SUFFIXES = (
    '.microsoft.com', '.windows.com', '.windowsupdate.com',
    '.bing.com', '.msftconnecttest.com', '.msedge.net',
    '.azure.com', '.office.com', '.office365.com',
    '.googleapis.com', '.google.com', '.gstatic.com',
    '.cloudflare.com', '.amazonaws.com', '.akamai.net',
    '.mozilla.org', '.mozilla.com', '.firefox.com',
    '.github.com', '.github.io',
    '.local', '.internal', '.lan', '.home',
)

POLL_INTERVAL = 5  # seconds between DNS cache polls


class DNSMonitor:
    """
    Monitors the Windows DNS resolver cache for new domains.
    Sends newly seen domains to the NSFW detector for AI classification.
    Works across all browsers and applications - no extension needed.
    """

    def __init__(
        self,
        on_new_domain: Callable[[str], None],
        known_domains: Optional[Set[str]] = None,
    ):
        """
        Args:
            on_new_domain: Called with each newly seen domain for AI checking.
            known_domains: Pre-populated set of domains to skip (already checked).
        """
        self.on_new_domain = on_new_domain
        self._seen_domains: Set[str] = set(known_domains) if known_domains else set()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        """Start monitoring the DNS cache."""
        if self._running:
            return

        # Seed with current DNS cache so we don't re-check everything on startup
        current = self._read_dns_cache()
        self._seen_domains.update(current)
        print(f"[DNS Monitor] Started - {len(self._seen_domains)} domains already seen")

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False

    def add_known_domain(self, domain: str) -> None:
        """Add a domain to the seen set (e.g., from cache load)."""
        self._seen_domains.add(domain.lower())

    def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                domains = self._read_dns_cache()
                new_domains = domains - self._seen_domains

                for domain in new_domains:
                    self._seen_domains.add(domain)
                    if self._should_check(domain):
                        print(f"[DNS Monitor] New domain detected: {domain}")
                        try:
                            self.on_new_domain(domain)
                        except Exception as e:
                            print(f"[DNS Monitor] Error checking {domain}: {e}")

            except Exception as e:
                print(f"[DNS Monitor] Poll error: {e}")

            time.sleep(POLL_INTERVAL)

    def _read_dns_cache(self) -> Set[str]:
        """Read all domain names from the Windows DNS resolver cache."""
        try:
            result = subprocess.run(
                ['powershell', '-Command',
                 'Get-DnsClientCache | Select-Object -ExpandProperty Entry'],
                capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )

            domains = set()
            for line in result.stdout.splitlines():
                domain = line.strip().lower()
                if domain and '.' in domain:
                    # Strip www. for consistency
                    clean = domain.removeprefix('www.')
                    domains.add(clean)
            return domains

        except Exception as e:
            print(f"[DNS Monitor] Failed to read DNS cache: {e}")
            return set()

    def _should_check(self, domain: str) -> bool:
        """Filter out infrastructure/internal domains."""
        if not domain or '.' not in domain:
            return False

        if domain in SKIP_DOMAINS:
            return False

        for suffix in SKIP_SUFFIXES:
            if domain.endswith(suffix):
                return False

        # Skip IP addresses and reverse DNS
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', domain):
            return False
        if domain.endswith('.arpa'):
            return False

        return True
