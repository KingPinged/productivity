"""
Website blocker using /etc/hosts file (macOS).
Uses osascript for privilege escalation when writing to hosts file.
"""

import subprocess
import shutil
import tempfile
from typing import Set, Tuple
from pathlib import Path

from src.utils.constants import HOSTS_PATH, HOSTS_MARKER_START, HOSTS_MARKER_END

# Separate markers for always-blocked (adult) content
HOSTS_ADULT_MARKER_START = "# PRODUCTIVITY_TIMER_ADULT_BLOCK_START"
HOSTS_ADULT_MARKER_END = "# PRODUCTIVITY_TIMER_ADULT_BLOCK_END"


class WebsiteBlocker:
    """
    Blocks websites by modifying the /etc/hosts file.
    Uses osascript for sudo privilege escalation on macOS.
    """

    def __init__(self, blocked_sites: Set[str], always_blocked_sites: Set[str] = None,
                 whitelisted_urls: list = None):
        """
        Initialize the website blocker.

        Args:
            blocked_sites: Set of domain names to block during sessions
            always_blocked_sites: Set of domain names to always block (adult content)
            whitelisted_urls: List of URLs that are whitelisted - their domains will be
                              excluded from hosts file blocking (handled by browser extension)
        """
        self.whitelisted_urls = whitelisted_urls or []
        # Filter out domains that have whitelisted URLs
        self.blocked_sites = self._filter_whitelisted_domains(set(blocked_sites))
        self.always_blocked_sites = set(always_blocked_sites) if always_blocked_sites else set()
        self._is_blocking = False
        self._backup_path = HOSTS_PATH.parent / "hosts.productivity.backup"
        self._last_error = ""

        # Apply always-blocked sites immediately on init
        if self.always_blocked_sites:
            self._apply_always_blocked()

    def _filter_whitelisted_domains(self, blocked_sites: Set[str]) -> Set[str]:
        """
        Remove domains from blocked_sites if they have whitelisted URLs.
        Those domains will be blocked by the browser extension instead,
        which can handle URL-level whitelisting.
        """
        if not self.whitelisted_urls:
            return blocked_sites

        # Extract domains from whitelisted URLs
        whitelisted_domains = set()
        for url in self.whitelisted_urls:
            # Remove protocol
            domain = url.lower().replace('https://', '').replace('http://', '')
            # Remove path
            domain = domain.split('/')[0]
            # Remove www. prefix for comparison
            domain_no_www = domain.replace('www.', '')
            whitelisted_domains.add(domain)
            whitelisted_domains.add(domain_no_www)
            whitelisted_domains.add('www.' + domain_no_www)

        # Filter out domains that have whitelisted URLs
        filtered = set()
        for site in blocked_sites:
            site_lower = site.lower()
            site_no_www = site_lower.replace('www.', '')
            # Check if this domain or its www variant is in whitelisted domains
            if site_lower not in whitelisted_domains and site_no_www not in whitelisted_domains:
                filtered.add(site)
            else:
                print(f"Excluding {site} from hosts file (has whitelisted URLs, browser extension will handle)")

        return filtered

    def block(self) -> Tuple[bool, str]:
        """
        Add blocking entries to hosts file.

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Verify hosts file exists
            if not HOSTS_PATH.exists():
                self._last_error = f"Hosts file not found at {HOSTS_PATH}"
                return False, self._last_error

            # Read current hosts file
            content = self._read_hosts()

            # Remove any existing blocks from us
            content = self._remove_our_blocks(content)

            # Build new block entries
            block_entries = [HOSTS_MARKER_START]
            for site in sorted(self.blocked_sites):
                # Clean the site name
                site = site.strip().lower()
                if not site:
                    continue

                # Add entry - 0.0.0.0 is faster and more effective than 127.0.0.1
                block_entries.append(f"0.0.0.0 {site}")

                # Add www variant if not already www
                if not site.startswith("www."):
                    block_entries.append(f"0.0.0.0 www.{site}")

            block_entries.append(HOSTS_MARKER_END)

            # Append our blocks
            new_content = content.rstrip() + "\n\n" + "\n".join(block_entries) + "\n"

            # Write to hosts file
            success = self._write_hosts(new_content)
            if not success:
                return False, self._last_error

            # Flush DNS cache
            self._flush_dns()

            self._is_blocking = True
            return True, ""

        except PermissionError as e:
            self._last_error = f"Permission denied. ({e})"
            return False, self._last_error
        except Exception as e:
            self._last_error = f"Error blocking websites: {e}"
            return False, self._last_error

    def unblock(self) -> Tuple[bool, str]:
        """
        Remove our blocking entries from hosts file.

        Returns:
            Tuple of (success, error_message)
        """
        try:
            if not HOSTS_PATH.exists():
                self._is_blocking = False
                return True, ""

            # Read current hosts file
            content = self._read_hosts()

            # Remove our blocks
            content = self._remove_our_blocks(content)

            # Write back
            success = self._write_hosts(content)
            if not success:
                return False, self._last_error

            # Flush DNS cache
            self._flush_dns()

            self._is_blocking = False
            return True, ""

        except PermissionError as e:
            self._last_error = f"Permission denied: {e}"
            return False, self._last_error
        except Exception as e:
            self._last_error = f"Error unblocking websites: {e}"
            return False, self._last_error

    def update_blocked_sites(self, blocked_sites: Set[str]) -> None:
        """Update the set of blocked websites."""
        # Filter out domains that have whitelisted URLs
        self.blocked_sites = self._filter_whitelisted_domains(set(blocked_sites))

        # If currently blocking, re-apply with new sites
        if self._is_blocking:
            self.unblock()
            self.block()

    def add_adult_site(self, domain: str) -> None:
        """Add a single domain to the always-blocked (adult) set and re-apply hosts rules."""
        domain = domain.strip().lower()
        if domain and domain not in self.always_blocked_sites:
            self.always_blocked_sites.add(domain)
            self._apply_always_blocked()

    def update_whitelisted_urls(self, whitelisted_urls: list) -> None:
        """Update the list of whitelisted URLs."""
        self.whitelisted_urls = whitelisted_urls or []

    def is_blocking(self) -> bool:
        """Check if website blocking is currently active."""
        return self._is_blocking

    def get_last_error(self) -> str:
        """Get the last error message."""
        return self._last_error

    def _read_hosts(self) -> str:
        """Read the hosts file content."""
        try:
            with open(HOSTS_PATH, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(HOSTS_PATH, 'r', encoding='latin-1') as f:
                return f.read()

    def _write_hosts(self, content: str) -> bool:
        """Write hosts file using osascript for privilege escalation."""
        try:
            # Create backup first
            if HOSTS_PATH.exists():
                try:
                    subprocess.run(
                        [
                            'osascript', '-e',
                            f'do shell script "cp /etc/hosts {self._backup_path}" with administrator privileges',
                        ],
                        capture_output=True,
                    )
                except Exception:
                    pass  # Backup failure is not critical

            # Write content to a temp file, then copy to /etc/hosts with admin privileges
            with tempfile.NamedTemporaryFile(mode='w', suffix='.hosts', delete=False, encoding='utf-8') as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            # Copy temp file to /etc/hosts with admin privileges
            result = subprocess.run(
                [
                    'osascript', '-e',
                    f'do shell script "cp {tmp_path} /etc/hosts && rm {tmp_path}" with administrator privileges',
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                self._last_error = f"Failed to write hosts file: {result.stderr.strip()}"
                return False

            return True

        except Exception as e:
            self._last_error = f"Failed to write hosts file: {e}"
            return False

    def _remove_our_blocks(self, content: str, keep_adult_blocks: bool = True) -> str:
        """Remove our marker block from hosts content.

        Args:
            content: Hosts file content
            keep_adult_blocks: If True, preserve adult content blocks
        """
        lines = content.split('\n')
        result = []
        in_session_block = False
        in_adult_block = False

        for line in lines:
            # Handle session blocks
            if HOSTS_MARKER_START in line:
                in_session_block = True
                continue
            if HOSTS_MARKER_END in line:
                in_session_block = False
                continue

            # Handle adult blocks
            if HOSTS_ADULT_MARKER_START in line:
                if keep_adult_blocks:
                    result.append(line)
                in_adult_block = True
                continue
            if HOSTS_ADULT_MARKER_END in line:
                if keep_adult_blocks:
                    result.append(line)
                in_adult_block = False
                continue

            # Keep lines that aren't in session block
            if not in_session_block:
                if in_adult_block and keep_adult_blocks:
                    result.append(line)
                elif not in_adult_block:
                    result.append(line)

        # Remove trailing empty lines
        while result and not result[-1].strip():
            result.pop()

        return '\n'.join(result)

    def _apply_always_blocked(self) -> Tuple[bool, str]:
        """
        Apply always-blocked sites (adult content) to hosts file.
        These are never removed until app is uninstalled.

        Returns:
            Tuple of (success, error_message)
        """
        try:
            if not HOSTS_PATH.exists():
                return False, f"Hosts file not found at {HOSTS_PATH}"

            # Read current hosts file
            content = self._read_hosts()

            # Check if adult blocks already exist
            if HOSTS_ADULT_MARKER_START in content:
                content = self._remove_adult_blocks(content)

            # Build adult block entries
            block_entries = [HOSTS_ADULT_MARKER_START]
            for site in sorted(self.always_blocked_sites):
                site = site.strip().lower()
                if not site:
                    continue

                block_entries.append(f"0.0.0.0 {site}")
                if not site.startswith("www."):
                    block_entries.append(f"0.0.0.0 www.{site}")

            block_entries.append(HOSTS_ADULT_MARKER_END)

            # Append adult blocks
            new_content = content.rstrip() + "\n\n" + "\n".join(block_entries) + "\n"

            # Write to hosts file
            success = self._write_hosts(new_content)
            if not success:
                return False, self._last_error

            # Flush DNS cache
            self._flush_dns()

            print(f"Adult content blocking: {len(self.always_blocked_sites)} sites blocked")
            return True, ""

        except PermissionError:
            return False, "Permission denied."
        except Exception as e:
            return False, f"Error applying adult blocks: {e}"

    def _remove_adult_blocks(self, content: str) -> str:
        """Remove adult content blocks from hosts content."""
        lines = content.split('\n')
        result = []
        in_adult_block = False

        for line in lines:
            if HOSTS_ADULT_MARKER_START in line:
                in_adult_block = True
                continue
            if HOSTS_ADULT_MARKER_END in line:
                in_adult_block = False
                continue
            if not in_adult_block:
                result.append(line)

        while result and not result[-1].strip():
            result.pop()

        return '\n'.join(result)

    def _flush_dns(self) -> None:
        """Flush the macOS DNS cache."""
        try:
            subprocess.run(
                ['dscacheutil', '-flushcache'],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ['killall', '-HUP', 'mDNSResponder'],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass  # Non-critical if this fails

    def restore_backup(self) -> bool:
        """Restore hosts file from backup (emergency recovery)."""
        try:
            if self._backup_path.exists():
                subprocess.run(
                    [
                        'osascript', '-e',
                        f'do shell script "cp {self._backup_path} /etc/hosts" with administrator privileges',
                    ],
                    capture_output=True,
                )
                self._flush_dns()
                self._is_blocking = False
                return True
            return False
        except Exception:
            return False

    def verify_blocking_active(self) -> Tuple[bool, str]:
        """
        Verify that our blocking entries are in the hosts file.

        Returns:
            Tuple of (is_active, status_message)
        """
        try:
            if not HOSTS_PATH.exists():
                return False, "Hosts file not found"

            content = self._read_hosts()

            if HOSTS_MARKER_START in content and HOSTS_MARKER_END in content:
                # Count blocked entries
                lines = content.split('\n')
                count = sum(1 for line in lines if line.strip().startswith('0.0.0.0'))
                return True, f"Blocking active ({count} entries)"
            else:
                return False, "No blocking entries found in hosts file"

        except Exception as e:
            return False, f"Error checking hosts file: {e}"
