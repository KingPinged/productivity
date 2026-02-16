"""
AFK (Away From Keyboard) detection for Productivity Timer.
Detects user inactivity using Windows GetLastInputInfo API.
"""

import ctypes
import platform
from ctypes import Structure, c_uint, sizeof


class LASTINPUTINFO(Structure):
    """Windows LASTINPUTINFO structure."""
    _fields_ = [
        ('cbSize', c_uint),
        ('dwTime', c_uint),
    ]


class AFKDetector:
    """
    Detects user inactivity (no keyboard/mouse input).
    Uses Windows GetLastInputInfo API for accurate system-wide input tracking.
    """

    def __init__(self, afk_threshold_seconds: int = 600):
        """
        Initialize the AFK detector.

        Args:
            afk_threshold_seconds: Seconds of inactivity before considered AFK.
                                   Default is 600 (10 minutes).
        """
        self.afk_threshold_seconds = afk_threshold_seconds
        self._is_windows = platform.system() == "Windows"
        self._enabled = True

        if self._is_windows:
            self._user32 = ctypes.windll.user32
            self._kernel32 = ctypes.windll.kernel32
        else:
            # Non-Windows: AFK detection disabled
            self._enabled = False

    def get_idle_seconds(self) -> int:
        """
        Get the number of seconds since the last user input.

        Returns:
            Seconds since last keyboard/mouse input, or 0 if detection unavailable.
        """
        if not self._enabled or not self._is_windows:
            return 0

        try:
            last_input_info = LASTINPUTINFO()
            last_input_info.cbSize = sizeof(LASTINPUTINFO)

            if self._user32.GetLastInputInfo(ctypes.byref(last_input_info)):
                # Get current tick count
                current_tick = self._kernel32.GetTickCount()

                # Calculate idle time in milliseconds
                # Handle tick count wraparound (occurs every ~49 days)
                if current_tick >= last_input_info.dwTime:
                    idle_ms = current_tick - last_input_info.dwTime
                else:
                    # Wraparound occurred
                    idle_ms = (0xFFFFFFFF - last_input_info.dwTime) + current_tick

                return idle_ms // 1000  # Convert to seconds

            return 0

        except Exception:
            return 0

    def is_afk(self) -> bool:
        """
        Check if the user is currently AFK (idle beyond threshold).

        Returns:
            True if user has been idle for longer than the threshold.
        """
        if not self._enabled:
            return False

        return self.get_idle_seconds() >= self.afk_threshold_seconds

    def set_threshold(self, seconds: int) -> None:
        """
        Update the AFK threshold.

        Args:
            seconds: New threshold in seconds.
        """
        self.afk_threshold_seconds = max(60, seconds)  # Minimum 1 minute

    def is_available(self) -> bool:
        """
        Check if AFK detection is available on this system.

        Returns:
            True if AFK detection is supported and enabled.
        """
        return self._enabled and self._is_windows
