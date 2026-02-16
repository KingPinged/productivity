"""
Internet Disabler - Punishment system for adult site visits.
Disables network adapters as punishment for exceeding adult site visit attempts.
"""

import subprocess
import threading
import time
import re
from typing import List, Tuple, Optional

from src.data.punishment_state import PunishmentState
from src.utils.constants import (
    DEFAULT_MAX_ADULT_STRIKES,
    DEFAULT_PUNISHMENT_HOURS,
    PUNISHMENT_ENFORCEMENT_INTERVAL,
)


class InternetDisabler:
    """
    Manages network adapter control for punishment system.
    Disables all network adapters when strike limit exceeded.
    """

    def __init__(
        self,
        max_strikes: int = DEFAULT_MAX_ADULT_STRIKES,
        punishment_hours: int = DEFAULT_PUNISHMENT_HOURS
    ):
        self.max_strikes = max_strikes
        self.punishment_hours = punishment_hours
        self.punishment_seconds = punishment_hours * 3600

        # Load persistent state
        self.state = PunishmentState.load()

        # Threading
        self._restore_timer: Optional[threading.Timer] = None
        self._enforcement_thread: Optional[threading.Thread] = None
        self._enforcement_running = False

        # Check if we're in an active lock on startup
        self._check_and_maintain_lock()

    def get_all_adapters(self) -> List[str]:
        """
        Get all network adapter names using netsh.
        Returns list of adapter names that are currently connected or enabled.
        """
        try:
            result = subprocess.run(
                ['netsh', 'interface', 'show', 'interface'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            adapters = []
            lines = result.stdout.strip().split('\n')

            # Skip header lines (first 3 lines typically)
            for line in lines[3:]:
                # Parse the line - format: "Admin State    State          Type             Interface Name"
                # Example: "Enabled        Connected      Dedicated        Wi-Fi"
                parts = line.split()
                if len(parts) >= 4:
                    # The interface name can have spaces, so join everything from index 3
                    admin_state = parts[0]
                    interface_name = ' '.join(parts[3:])

                    # Include adapters that are enabled (regardless of connection state)
                    if admin_state.lower() == 'enabled':
                        adapters.append(interface_name)

            return adapters

        except Exception as e:
            print(f"Error getting network adapters: {e}")
            return []

    def _disable_adapter(self, adapter_name: str) -> bool:
        """Disable a single network adapter."""
        try:
            result = subprocess.run(
                ['netsh', 'interface', 'set', 'interface', adapter_name, 'disable'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Error disabling adapter {adapter_name}: {e}")
            return False

    def _enable_adapter(self, adapter_name: str) -> bool:
        """Enable a single network adapter."""
        try:
            result = subprocess.run(
                ['netsh', 'interface', 'set', 'interface', adapter_name, 'enable'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Error enabling adapter {adapter_name}: {e}")
            return False

    def disable_all_adapters(self) -> Tuple[bool, str]:
        """
        Disable all network adapters.
        Returns (success, error_message).
        """
        adapters = self.get_all_adapters()

        if not adapters:
            return False, "No network adapters found"

        disabled = []
        for adapter in adapters:
            if self._disable_adapter(adapter):
                disabled.append(adapter)
                print(f"Disabled adapter: {adapter}")
            else:
                print(f"Failed to disable adapter: {adapter}")

        if disabled:
            # Calculate lock end time
            lock_end = time.time() + self.punishment_seconds

            # Update state
            self.state.start_lock(lock_end, disabled)

            # Start restore timer
            self._start_restore_timer(self.punishment_seconds)

            # Start enforcement thread
            self._start_enforcement_thread()

            return True, f"Disabled {len(disabled)} adapter(s)"

        return False, "Failed to disable any adapters"

    def enable_all_adapters(self) -> Tuple[bool, str]:
        """
        Re-enable previously disabled adapters.
        Returns (success, error_message).
        """
        if not self.state.disabled_adapters:
            return False, "No adapters to re-enable"

        enabled = []
        for adapter in self.state.disabled_adapters:
            if self._enable_adapter(adapter):
                enabled.append(adapter)
                print(f"Enabled adapter: {adapter}")
            else:
                print(f"Failed to enable adapter: {adapter}")

        # Stop enforcement
        self._stop_enforcement_thread()

        # Clear state
        self.state.end_lock()

        if enabled:
            return True, f"Enabled {len(enabled)} adapter(s)"

        return False, "Failed to enable any adapters"

    def _check_and_maintain_lock(self) -> None:
        """
        Called on startup - maintain lock if still active.
        Re-disables adapters and restarts timer if needed.
        """
        if not self.state.is_locked:
            return

        current_time = time.time()

        if current_time < self.state.lock_end_timestamp:
            # Lock should still be active
            remaining_seconds = self.state.lock_end_timestamp - current_time
            print(f"Punishment lock active. {remaining_seconds / 60:.1f} minutes remaining.")

            # Re-disable adapters (in case user manually re-enabled them)
            for adapter in self.state.disabled_adapters:
                self._disable_adapter(adapter)

            # Also disable any new adapters that might have appeared
            current_adapters = self.get_all_adapters()
            for adapter in current_adapters:
                if adapter not in self.state.disabled_adapters:
                    if self._disable_adapter(adapter):
                        self.state.disabled_adapters.append(adapter)
                        self.state.save()

            # Start timer for remaining duration
            self._start_restore_timer(remaining_seconds)

            # Start enforcement thread
            self._start_enforcement_thread()
        else:
            # Lock expired - restore adapters
            print("Punishment lock expired. Restoring network.")
            self.enable_all_adapters()

    def _start_restore_timer(self, seconds: float) -> None:
        """Start background timer to restore adapters after timeout."""
        # Cancel existing timer if any
        if self._restore_timer:
            self._restore_timer.cancel()

        def restore_callback():
            print("Punishment duration complete. Restoring network.")
            self.enable_all_adapters()

        self._restore_timer = threading.Timer(seconds, restore_callback)
        self._restore_timer.daemon = True
        self._restore_timer.start()

    def _start_enforcement_thread(self) -> None:
        """Start thread that periodically ensures adapters stay disabled."""
        if self._enforcement_running:
            return

        self._enforcement_running = True

        def enforcement_loop():
            while self._enforcement_running and self.state.is_locked:
                # Check if lock has expired
                if time.time() >= self.state.lock_end_timestamp:
                    break

                # Re-disable any adapters that were manually re-enabled
                for adapter in self.state.disabled_adapters:
                    self._disable_adapter(adapter)

                # Also check for new adapters
                current_adapters = self.get_all_adapters()
                for adapter in current_adapters:
                    if adapter not in self.state.disabled_adapters:
                        if self._disable_adapter(adapter):
                            self.state.disabled_adapters.append(adapter)
                            self.state.save()

                time.sleep(PUNISHMENT_ENFORCEMENT_INTERVAL)

        self._enforcement_thread = threading.Thread(target=enforcement_loop, daemon=True)
        self._enforcement_thread.start()

    def _stop_enforcement_thread(self) -> None:
        """Stop the enforcement thread."""
        self._enforcement_running = False

    def add_strike(self) -> Tuple[int, bool]:
        """
        Add a strike for adult site visit.
        Returns (new_strike_count, triggered_punishment).
        """
        if self.state.is_locked:
            # Already in punishment, don't add more strikes
            return self.state.strike_count, False

        new_count = self.state.add_strike()

        if new_count > self.max_strikes:
            # Trigger punishment
            success, _ = self.disable_all_adapters()
            return new_count, success

        return new_count, False

    def get_strikes_remaining(self) -> int:
        """Get how many strikes left before punishment."""
        if self.state.is_locked:
            return 0
        remaining = self.max_strikes - self.state.strike_count + 1
        return max(0, remaining)

    def is_locked(self) -> bool:
        """Check if currently in punishment lock."""
        return self.state.is_locked

    def get_lock_time_remaining(self) -> int:
        """Get seconds remaining in lock (0 if not locked)."""
        if not self.state.is_locked:
            return 0

        remaining = self.state.lock_end_timestamp - time.time()
        return max(0, int(remaining))

    def get_status(self) -> dict:
        """Get current punishment status as dict."""
        return {
            'strikes_remaining': self.get_strikes_remaining(),
            'is_locked': self.is_locked(),
            'lock_time_remaining': self.get_lock_time_remaining(),
            'lock_end_timestamp': self.state.lock_end_timestamp if self.state.is_locked else 0,
            'strike_count': self.state.strike_count,
            'max_strikes': self.max_strikes
        }

    def cleanup(self) -> None:
        """Cleanup resources (call on app shutdown)."""
        # Note: We intentionally do NOT restore adapters on cleanup
        # The punishment should persist even if the app is closed
        self._stop_enforcement_thread()
        if self._restore_timer:
            self._restore_timer.cancel()
