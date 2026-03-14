"""
System tray icon for Productivity Timer (macOS).
Uses pyobjc NSStatusBar directly — no separate event loop, no thread conflicts.
"""

from typing import Callable, Optional

from src.utils.constants import TimerState

try:
    from AppKit import (
        NSStatusBar, NSVariableStatusItemLength, NSMenu, NSMenuItem,
        NSImage,
    )
    from Foundation import NSObject, NSSize, NSData
    APPKIT_AVAILABLE = True
except ImportError:
    APPKIT_AVAILABLE = False

try:
    from PIL import Image, ImageDraw
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# Store callback references at module level to prevent garbage collection
_menu_targets = []


class TrayIcon:
    """
    System tray (status bar) icon using native macOS NSStatusItem.
    No threads — integrates directly with the Cocoa layer Tkinter already uses.
    """

    def __init__(
        self,
        on_show: Callable,
        on_start: Callable,
        on_pause: Callable,
        on_stop: Callable,
        on_settings: Callable,
        on_exit: Callable,
        root=None,
    ):
        self.on_show = on_show
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_stop = on_stop
        self.on_settings = on_settings
        self.on_exit = on_exit
        self._root = root  # tkinter root for dispatching callbacks safely

        self._status_item = None
        self._current_state = TimerState.IDLE
        self._available = APPKIT_AVAILABLE and PIL_AVAILABLE
        self._started = False
        self._session_active = False

    def _create_ns_image(self, color: str = "#808080") -> 'NSImage':
        """Create an NSImage from a PIL-drawn icon."""
        size = 22
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        margin = 2
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=color,
            outline="#FFFFFF",
            width=1
        )

        buf = io.BytesIO()
        image.save(buf, format='PNG')
        png_bytes = buf.getvalue()
        data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
        ns_image = NSImage.alloc().initWithData_(data)
        ns_image.setSize_(NSSize(size, size))
        ns_image.setTemplate_(True)  # Adapts to dark/light menu bar
        return ns_image

    def _make_menu_item(self, title: str, callback: Callable) -> 'NSMenuItem':
        """Create a menu item with a callback target."""
        if not APPKIT_AVAILABLE:
            return None
        target = _CallbackTarget.alloc().init()
        target._callback = callback
        target._root = self._root  # pass root for thread-safe dispatch
        _menu_targets.append(target)  # prevent GC

        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title, "handleAction:", ""
        )
        mi.setTarget_(target)
        return mi

    def _build_menu(self) -> 'NSMenu':
        """Build the status bar dropdown menu."""
        _menu_targets.clear()
        menu = NSMenu.alloc().init()

        menu.addItem_(self._make_menu_item("Show Timer", self.on_show))
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(self._make_menu_item("Start Session", self.on_start))
        menu.addItem_(self._make_menu_item("Pause", self.on_pause))
        menu.addItem_(self._make_menu_item("Stop Session", self.on_stop))
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(self._make_menu_item("Settings", self.on_settings))

        if not self._session_active:
            menu.addItem_(NSMenuItem.separatorItem())
            menu.addItem_(self._make_menu_item("Exit", self.on_exit))

        return menu

    def set_session_active(self, active: bool) -> None:
        """Show/hide Exit menu item based on session state."""
        self._session_active = active
        if self._status_item:
            self._status_item.setMenu_(self._build_menu())

    def start(self) -> None:
        """Create and show the status bar icon on the main thread."""
        if not self._available or self._started:
            return

        try:
            self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
                NSVariableStatusItemLength
            )
            self._status_item.setImage_(self._create_ns_image())
            self._status_item.setToolTip_("Productivity Timer")
            self._status_item.setMenu_(self._build_menu())
            self._started = True
            print("Tray icon started (NSStatusBar)")
        except Exception as e:
            print(f"Tray icon error: {e}")
            self._available = False

    def stop(self) -> None:
        """Remove the status bar icon."""
        if self._status_item:
            try:
                NSStatusBar.systemStatusBar().removeStatusItem_(self._status_item)
            except Exception:
                pass
            self._status_item = None
        self._started = False
        _menu_targets.clear()

    def update_state(self, state: str) -> None:
        """Update the icon color based on timer state."""
        self._current_state = state
        if not self._status_item:
            return

        color_map = {
            TimerState.WORKING: ("#E74C3C", "Working"),
            TimerState.BREAK: ("#2ECC71", "Break"),
            TimerState.PAUSED: ("#F39C12", "Paused"),
        }
        color, label = color_map.get(state, ("#808080", "Idle"))

        try:
            self._status_item.setImage_(self._create_ns_image(color))
            self._status_item.setToolTip_(f"Productivity Timer - {label}")
        except Exception:
            pass

    def update_tooltip(self, text: str) -> None:
        """Update the tray icon tooltip."""
        if self._status_item:
            try:
                self._status_item.setToolTip_(text)
            except Exception:
                pass

    def is_available(self) -> bool:
        """Check if system tray is available."""
        return self._available


if APPKIT_AVAILABLE:
    class _CallbackTarget(NSObject):
        """Bridging object: receives Cocoa menu actions, calls Python callbacks."""

        _callback = None
        _root = None

        def handleAction_(self, sender):
            if self._callback:
                # Dispatch through root.after to ensure tkinter thread safety.
                # Cocoa menu callbacks run from the NSRunLoop which can interrupt
                # tkinter's event processing, causing crashes.
                if self._root:
                    self._root.after(0, self._callback)
                else:
                    self._callback()
