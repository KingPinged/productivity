"""
Floating toast notification for unproductive app/website alerts.
Uses the native macOS NSWindow API to stay visible above all apps
regardless of focus. Only dismissed by clicking the toast itself.
"""

import tkinter as tk
from typing import Optional


# Track active toasts for vertical stacking
_active_toasts: list = []

# NSStatusWindowLevel — above all normal windows and panels
_NS_STATUS_WINDOW_LEVEL = 25


def _format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _make_window_always_on_top(win: tk.Toplevel) -> None:
    """Use PyObjC to make a Toplevel truly always-on-top, even when app loses focus."""
    try:
        from AppKit import NSApp

        # Identify our NSWindow by matching its unique title
        toast_id = win.title()
        for ns_win in NSApp.windows():
            if ns_win.title() == toast_id:
                ns_win.setLevel_(_NS_STATUS_WINDOW_LEVEL)
                ns_win.setHidesOnDeactivate_(False)
                break
    except Exception:
        pass


class ToastNotification:
    """
    Floating toast notification widget.
    Appears top-right, stays above all windows on all desktops.
    Dismissed only by clicking anywhere on the toast.
    """

    TOAST_WIDTH = 320
    TOAST_PADDING = 20

    _toast_counter = 0

    def __init__(
        self,
        master: tk.Tk,
        title: str,
        message: str,
        detail: Optional[str] = None,
    ):
        self._master = master
        self._window: Optional[tk.Toplevel] = None

        self._show(title, message, detail)

    def _show(self, title: str, message: str, detail: Optional[str]) -> None:
        """Create and display the toast window."""
        # Remember if main window was hidden so we can re-hide it
        was_withdrawn = self._master.state() == 'withdrawn'

        win = tk.Toplevel(self._master)
        self._window = win

        # Assign a unique internal title so we can find the NSWindow later
        ToastNotification._toast_counter += 1
        toast_id = f"__toast_{ToastNotification._toast_counter}__"
        win.title(toast_id)

        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.92)
        except tk.TclError:
            pass

        # Prevent toast from bringing the main window to the foreground
        if was_withdrawn:
            self._master.withdraw()

        # Dark theme colors
        bg = "#1a1a2e"
        fg = "#e0e0e0"
        accent = "#e94560"
        detail_fg = "#888888"

        win.configure(bg=bg)

        # Main frame
        frame = tk.Frame(win, bg=bg, padx=16, pady=12, cursor="hand2")
        frame.pack(fill=tk.BOTH, expand=True)

        # Top row: warning icon + title + close hint
        top = tk.Frame(frame, bg=bg, cursor="hand2")
        top.pack(fill=tk.X)

        title_label = tk.Label(
            top, text=title, font=("SF Pro Display", 13, "bold"),
            fg=accent, bg=bg, anchor="w", cursor="hand2",
        )
        title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        close_btn = tk.Label(
            top, text="\u2715", font=("SF Pro Display", 12),
            fg="#666666", bg=bg, cursor="hand2",
        )
        close_btn.pack(side=tk.RIGHT)

        # Message
        msg_label = tk.Label(
            frame, text=message, font=("SF Pro Display", 12),
            fg=fg, bg=bg, anchor="w", wraplength=self.TOAST_WIDTH - 40,
            justify=tk.LEFT, cursor="hand2",
        )
        msg_label.pack(fill=tk.X, pady=(6, 0))

        # Detail (nudge text)
        detail_label = None
        if detail:
            detail_label = tk.Label(
                frame, text=detail, font=("SF Pro Display", 11),
                fg=detail_fg, bg=bg, anchor="w",
                wraplength=self.TOAST_WIDTH - 40, justify=tk.LEFT,
                cursor="hand2",
            )
            detail_label.pack(fill=tk.X, pady=(4, 0))

        # Clicking anywhere on the toast dismisses it
        for widget in [win, frame, top, title_label, close_btn, msg_label]:
            widget.bind("<Button-1>", lambda e: self.dismiss())
        if detail_label:
            detail_label.bind("<Button-1>", lambda e: self.dismiss())

        # Position: top-right of screen, stacked below existing toasts
        win.update_idletasks()
        screen_w = win.winfo_screenwidth()
        toast_h = win.winfo_reqheight()

        x = screen_w - self.TOAST_WIDTH - self.TOAST_PADDING
        y = self.TOAST_PADDING

        # Stack below existing toasts
        for toast in _active_toasts:
            if toast._window and toast._window.winfo_exists():
                y += toast._window.winfo_height() + 8

        win.geometry(f"{self.TOAST_WIDTH}x{toast_h}+{x}+{y}")

        # Make the window truly always-on-top via native macOS API
        # Must happen after geometry is set and window is mapped
        _make_window_always_on_top(win)

        _active_toasts.append(self)

    def dismiss(self) -> None:
        """Close the toast."""
        if self in _active_toasts:
            _active_toasts.remove(self)

        if self._window and self._window.winfo_exists():
            self._window.destroy()
            self._window = None


def show_unproductive_alert(
    master: tk.Tk,
    name: str,
    category: str,
    seconds_today: int,
) -> ToastNotification:
    """
    Show a toast alert for unproductive app/website usage.

    Args:
        master: Tk root window
        name: App name or website domain
        category: 'app' or 'website'
        seconds_today: Total seconds spent today
    """
    kind = "App" if category == "app" else "Website"
    title = f"\u26a0 Unproductive {kind} Alert"
    message = f"{name} \u2014 {_format_duration(seconds_today)} today"
    detail = "Consider switching to something productive."

    return ToastNotification(master, title, message, detail)
