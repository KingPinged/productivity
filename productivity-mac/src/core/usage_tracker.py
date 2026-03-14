"""
Usage tracker for monitoring which applications are in focus (macOS).
Uses NSWorkspace API to detect the foreground application and track time spent.

All PyObjC/Quartz calls run on the main thread (via tkinter after()) to avoid
GIL corruption that occurs when calling these APIs from background threads
on Python 3.13+.
"""

from typing import Optional, Callable

from src.utils.constants import USAGE_TRACKING_INTERVAL


class UsageTracker:
    """
    Tracks which applications are currently in focus.
    Uses macOS NSWorkspace API to monitor foreground app and record usage time.
    Polls on the main thread via root.after() to avoid PyObjC threading issues.
    """

    def __init__(
        self,
        on_usage_tick: Optional[Callable[[str, str, int], None]] = None,
        afk_check: Optional[Callable[[], bool]] = None,
        root=None,
        browser_tracker=None,
    ):
        """
        Initialize the usage tracker.

        Args:
            on_usage_tick: Callback(name, category, seconds) when tracking
            afk_check: Function returning True if user is AFK
            root: Tkinter root window for scheduling (required)
            browser_tracker: Optional BrowserTracker for native URL detection
        """
        self.on_usage_tick = on_usage_tick
        self.afk_check = afk_check
        self._root = root
        self.browser_tracker = browser_tracker

        self._available = True
        self._running = False
        self._after_id = None
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

    def _tick(self) -> None:
        """Main-thread polling tick scheduled via root.after()."""
        if not self._running:
            return

        try:
            # Check if user is AFK (Quartz call — must be on main thread)
            if not (self.afk_check and self.afk_check()):
                # Get current foreground app (NSWorkspace — must be on main thread)
                app_name = self.get_foreground_app()

                if app_name and self.on_usage_tick:
                    self.on_usage_tick(app_name, 'app', USAGE_TRACKING_INTERVAL)
                    self._current_app = app_name

                # Native browser tracking fallback
                if app_name and self.browser_tracker:
                    self.browser_tracker.on_tick(app_name, USAGE_TRACKING_INTERVAL)
        except Exception as e:
            print(f"Usage tracker error: {e}")

        # Schedule next tick
        if self._running and self._root:
            self._after_id = self._root.after(
                USAGE_TRACKING_INTERVAL * 1000, self._tick
            )

    def start(self) -> None:
        """Start usage tracking on the main thread."""
        if self._running or not self._available:
            return
        if not self._root:
            print("Usage tracker: no root window, cannot start")
            return

        self._running = True
        self._after_id = self._root.after(
            USAGE_TRACKING_INTERVAL * 1000, self._tick
        )
        print("Usage tracker started")

    def stop(self) -> None:
        """Stop usage tracking."""
        self._running = False
        if self._after_id and self._root:
            try:
                self._root.after_cancel(self._after_id)
            except (ValueError, Exception):
                pass
            self._after_id = None
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
