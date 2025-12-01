"""
Website blocker using Windows hosts file.
"""

import subprocess
import shutil
import os
from typing import Set, Tuple
from pathlib import Path

from src.utils.constants import HOSTS_PATH, HOSTS_MARKER_START, HOSTS_MARKER_END


class WebsiteBlocker:
    """
    Blocks websites by modifying the Windows hosts file.
    Requires administrator privileges.
    """

    def __init__(self, blocked_sites: Set[str]):
        """
        Initialize the website blocker.

        Args:
            blocked_sites: Set of domain names to block
        """
        self.blocked_sites = set(blocked_sites)
        self._is_blocking = False
        self._backup_path = HOSTS_PATH.parent / "hosts.productivity.backup"
        self._last_error = ""

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
            # Using 0.0.0.0 is more effective than 127.0.0.1
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
            self._last_error = f"Permission denied. Run as administrator. ({e})"
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
        self.blocked_sites = set(blocked_sites)

        # If currently blocking, re-apply with new sites
        if self._is_blocking:
            self.unblock()
            self.block()

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
            # Try with different encoding
            with open(HOSTS_PATH, 'r', encoding='latin-1') as f:
                return f.read()

    def _write_hosts(self, content: str) -> bool:
        """Write hosts file directly."""
        try:
            # Create backup first
            if HOSTS_PATH.exists():
                try:
                    shutil.copy2(str(HOSTS_PATH), str(self._backup_path))
                except Exception:
                    pass  # Backup failure is not critical

            # Write directly to hosts file
            with open(HOSTS_PATH, 'w', encoding='utf-8') as f:
                f.write(content)

            return True

        except PermissionError:
            self._last_error = "Permission denied writing to hosts file. Ensure app is running as Administrator."
            return False
        except Exception as e:
            self._last_error = f"Failed to write hosts file: {e}"
            return False

    def _remove_our_blocks(self, content: str) -> str:
        """Remove our marker block from hosts content."""
        lines = content.split('\n')
        result = []
        in_our_block = False

        for line in lines:
            if HOSTS_MARKER_START in line:
                in_our_block = True
                continue
            if HOSTS_MARKER_END in line:
                in_our_block = False
                continue
            if not in_our_block:
                result.append(line)

        # Remove trailing empty lines
        while result and not result[-1].strip():
            result.pop()

        return '\n'.join(result)

    def _flush_dns(self) -> None:
        """Flush the Windows DNS cache."""
        try:
            # Use shell=True for better Windows compatibility
            subprocess.run(
                "ipconfig /flushdns",
                shell=True,
                capture_output=True,
                timeout=10
            )
        except Exception:
            pass  # Non-critical if this fails

    def restore_backup(self) -> bool:
        """Restore hosts file from backup (emergency recovery)."""
        try:
            if self._backup_path.exists():
                shutil.copy2(str(self._backup_path), str(HOSTS_PATH))
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
