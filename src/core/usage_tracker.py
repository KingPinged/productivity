"""
Usage tracker for monitoring which applications are in focus.
Uses Windows API to detect the foreground window and track time spent.
"""

import ctypes
import ctypes.wintypes
import platform
import threading
import time
from pathlib import Path
from typing import Optional, Callable

from src.utils.constants import USAGE_TRACKING_INTERVAL


# Windows API constants
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class UsageTracker:
    """
    Tracks which applications are currently in focus.
    Uses Windows API to monitor foreground window and record usage time.
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

        self._is_windows = platform.system() == "Windows"
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_app: Optional[str] = None

        if self._is_windows:
            self._user32 = ctypes.windll.user32
            self._kernel32 = ctypes.windll.kernel32
            self._psapi = ctypes.windll.psapi
        else:
            print("Usage tracker: Windows required for app tracking")

    def get_foreground_app(self) -> Optional[str]:
        """
        Get the process name of the currently focused window.

        Returns:
            Process name (e.g., "chrome.exe") or None if unavailable
        """
        if not self._is_windows:
            return None

        try:
            # Get the foreground window handle
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return None

            # Get the process ID
            pid = ctypes.wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value:
                return None

            # Open the process to get its name
            handle = self._kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                pid.value
            )
            if not handle:
                return None

            try:
                # Get the process executable path
                buffer = ctypes.create_unicode_buffer(512)
                size = ctypes.wintypes.DWORD(512)

                if self._kernel32.QueryFullProcessImageNameW(
                    handle,
                    0,
                    buffer,
                    ctypes.byref(size)
                ):
                    # Extract just the filename from the path
                    full_path = buffer.value
                    return Path(full_path).name.lower()

            finally:
                self._kernel32.CloseHandle(handle)

            return None

        except Exception as e:
            # Silently fail - some windows may not be accessible
            return None

    def get_foreground_window_title(self) -> Optional[str]:
        """
        Get the title of the currently focused window.

        Returns:
            Window title or None if unavailable
        """
        if not self._is_windows:
            return None

        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return None

            length = self._user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return None

            buffer = ctypes.create_unicode_buffer(length + 1)
            self._user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value

        except Exception:
            return None

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
        if self._running or not self._is_windows:
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
        return self._is_windows
