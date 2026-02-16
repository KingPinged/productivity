"""
AFK (Away From Keyboard) detection for Productivity Timer (macOS).
Detects user inactivity using Quartz CGEventSource API.
"""


class AFKDetector:
    """
    Detects user inactivity (no keyboard/mouse input).
    Uses macOS Quartz API for accurate system-wide input tracking.
    """

    def __init__(self, afk_threshold_seconds: int = 600):
        """
        Initialize the AFK detector.

        Args:
            afk_threshold_seconds: Seconds of inactivity before considered AFK.
                                   Default is 600 (10 minutes).
        """
        self.afk_threshold_seconds = afk_threshold_seconds
        self._enabled = True

        try:
            from Quartz import (
                CGEventSourceSecondsSinceLastEventType,
                kCGEventSourceStateHIDSystemState,
                kCGAnyInputEventType,
            )
            self._CGEventSourceSecondsSinceLastEventType = CGEventSourceSecondsSinceLastEventType
            self._kCGEventSourceStateHIDSystemState = kCGEventSourceStateHIDSystemState
            self._kCGAnyInputEventType = kCGAnyInputEventType
        except ImportError:
            print("Quartz not available - AFK detection disabled")
            self._enabled = False

    def get_idle_seconds(self) -> int:
        """
        Get the number of seconds since the last user input.

        Returns:
            Seconds since last keyboard/mouse input, or 0 if detection unavailable.
        """
        if not self._enabled:
            return 0

        try:
            idle = self._CGEventSourceSecondsSinceLastEventType(
                self._kCGEventSourceStateHIDSystemState,
                self._kCGAnyInputEventType,
            )
            return int(idle)
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
        return self._enabled
