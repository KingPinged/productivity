"""
System tray icon for Productivity Timer.
"""

import threading
from typing import Callable, Optional
from PIL import Image, ImageDraw

try:
    import pystray
    from pystray import Icon, Menu, MenuItem
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False

from src.utils.constants import TimerState


class TrayIcon:
    """
    System tray icon with context menu.
    """

    def __init__(
        self,
        on_show: Callable,
        on_start: Callable,
        on_pause: Callable,
        on_stop: Callable,
        on_settings: Callable,
        on_exit: Callable,
    ):
        """
        Initialize the tray icon.

        Args:
            on_show: Callback to show main window
            on_start: Callback to start timer
            on_pause: Callback to pause timer
            on_stop: Callback to stop timer
            on_settings: Callback to show settings
            on_exit: Callback to exit application
        """
        self.on_show = on_show
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_stop = on_stop
        self.on_settings = on_settings
        self.on_exit = on_exit

        self._icon: Optional[Icon] = None
        self._current_state = TimerState.IDLE

        if PYSTRAY_AVAILABLE:
            self._setup_icon()

    def _create_icon_image(self, color: str = "#808080") -> Image:
        """
        Create a simple icon image.

        Args:
            color: Fill color for the icon

        Returns:
            PIL Image object
        """
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Draw a circle with the given color
        margin = 4
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=color,
            outline="#FFFFFF",
            width=2
        )

        # Draw a "P" for Productivity
        draw.text(
            (size // 2 - 8, size // 2 - 12),
            "P",
            fill="#FFFFFF",
            font=None  # Use default font
        )

        return image

    def _setup_icon(self) -> None:
        """Set up the system tray icon."""
        image = self._create_icon_image()

        menu = Menu(
            MenuItem("Show Timer", self._on_show_click, default=True),
            Menu.SEPARATOR,
            MenuItem("Start Session", self._on_start_click),
            MenuItem("Pause", self._on_pause_click),
            MenuItem("Stop Session", self._on_stop_click),
            Menu.SEPARATOR,
            MenuItem("Settings", self._on_settings_click),
            Menu.SEPARATOR,
            MenuItem("Exit", self._on_exit_click),
        )

        self._icon = Icon(
            "ProductivityTimer",
            image,
            "Productivity Timer",
            menu
        )

    def _on_show_click(self, icon, item) -> None:
        """Handle Show Timer click."""
        self.on_show()

    def _on_start_click(self, icon, item) -> None:
        """Handle Start Session click."""
        self.on_start()

    def _on_pause_click(self, icon, item) -> None:
        """Handle Pause click."""
        self.on_pause()

    def _on_stop_click(self, icon, item) -> None:
        """Handle Stop Session click."""
        self.on_stop()

    def _on_settings_click(self, icon, item) -> None:
        """Handle Settings click."""
        self.on_settings()

    def _on_exit_click(self, icon, item) -> None:
        """Handle Exit click."""
        # Don't stop here - let the app decide if exit is allowed
        # The app will call stop() when actually exiting
        self.on_exit()

    def start(self) -> None:
        """Start the tray icon in a background thread."""
        if self._icon:
            thread = threading.Thread(target=self._icon.run, daemon=True)
            thread.start()

    def stop(self) -> None:
        """Stop the tray icon."""
        if self._icon:
            self._icon.stop()

    def update_state(self, state: str) -> None:
        """
        Update the icon based on timer state.

        Args:
            state: Current timer state
        """
        self._current_state = state

        if not self._icon:
            return

        # Update icon color based on state
        if state == TimerState.WORKING:
            color = "#E74C3C"  # Red
            tooltip = "Productivity Timer - Working"
        elif state == TimerState.BREAK:
            color = "#2ECC71"  # Green
            tooltip = "Productivity Timer - Break"
        elif state == TimerState.PAUSED:
            color = "#F39C12"  # Orange
            tooltip = "Productivity Timer - Paused"
        else:
            color = "#808080"  # Gray
            tooltip = "Productivity Timer - Idle"

        # Update icon
        self._icon.icon = self._create_icon_image(color)
        self._icon.title = tooltip

    def update_tooltip(self, text: str) -> None:
        """
        Update the tray icon tooltip.

        Args:
            text: New tooltip text
        """
        if self._icon:
            self._icon.title = text

    def is_available(self) -> bool:
        """Check if system tray is available."""
        return PYSTRAY_AVAILABLE
