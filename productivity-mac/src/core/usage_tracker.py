"""
Usage tracker for monitoring which applications are in focus (macOS).
Uses NSWorkspace API to detect the foreground application and track time spent.
"""

import threading
import time
from typing import Optional, Callable

from src.utils.constants import USAGE_TRACKING_INTERVAL


class UsageTracker:
    """
    Tracks which applications are currently in focus.
    Uses macOS NSWorkspace API to monitor foreground app and record usage time.
    """

    def __init__(
        self,
        on_usage_tick: Optional[Callable[[str, str, int], None]] = None,
        afk_check: Optional[Callable[[], bool]] = None,
    ):
        """
        Initialize the usage tracker.

        Args:
            on_usage_tick: Callback(name, category, seconds) when tracking
            afk_check: Function returning True if user is AFK
        """
        self.on_usage_tick = on_usage_tick
        self.afk_check = afk_check

        self._available = True
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_app: Optional[str] = None

        try:
            from AppKit import NSWorkspace
            self._NSWorkspace = NSWorkspace
        except ImportError:
            print("Usage tracker: AppKit not available, app tracking disabled")
            self._available = False

    def get_foreground_app(self) -> Optional[str]:
        """
        Get the name of the currently focused application.

        Returns:
            Application name (e.g., "Safari") or None if unavailable
        """
        if not self._available:
            return None

        try:
            active_app = self._NSWorkspace.sharedWorkspace().activeApplication()
            if active_app:
                return active_app.get('NSApplicationName')
            return None
        except Exception:
            return None

    def get_foreground_window_title(self) -> Optional[str]:
        """
        Get the title of the currently focused window.
        On macOS, we return the app name since window titles require
        accessibility API permissions.

        Returns:
            Application name or None if unavailable
        """
        return self.get_foreground_app()

    def _tracking_loop(self) -> None:
        """Background thread that tracks foreground app usage."""
        while self._running:
            try:
                # Check if user is AFK
                if self.afk_check and self.afk_check():
                    # User is AFK - don't count this interval
                    time.sleep(USAGE_TRACKING_INTERVAL)
                    continue

                # Get current foreground app
                app_name = self.get_foreground_app()

                if app_name and self.on_usage_tick:
                    # Record 1 second of usage for this app
                    self.on_usage_tick(app_name, 'app', 1)
                    self._current_app = app_name

            except Exception as e:
                print(f"Usage tracker error: {e}")

            time.sleep(USAGE_TRACKING_INTERVAL)

    def start(self) -> None:
        """Start the usage tracking background thread."""
        if self._running or not self._available:
            return

        self._running = True
        self._thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self._thread.start()
        print("Usage tracker started")

    def stop(self) -> None:
        """Stop the usage tracking."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        print("Usage tracker stopped")

    def is_running(self) -> bool:
        """Check if tracking is active."""
        return self._running

    def get_current_app(self) -> Optional[str]:
        """Get the last tracked foreground app."""
        return self._current_app

    def is_available(self) -> bool:
        """Check if usage tracking is available on this system."""
        return self._available
