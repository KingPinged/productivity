"""Frameless always-on-top bar showing session intention at top-center of screen."""

import platform
import tkinter as tk


class IntentionBar:
    """
    Slim overlay bar pinned to the top-center of the primary monitor.
    Click-through (WS_EX_TRANSPARENT) so clicks pass to windows behind it.
    Fades out when mouse hovers over it, reappears when mouse moves away.
    """

    DISPLAY_MAX_CHARS = 80
    _POLL_MS = 100
    _ALPHA_VISIBLE = 0.85
    _ALPHA_HIDDEN = 0.0

    def __init__(self, root: tk.Tk, intention: str):
        self.root = root
        self._destroyed = False
        self._hidden_by_hover = False

        # Truncate for display
        display_text = intention
        if len(display_text) > self.DISPLAY_MAX_CHARS:
            display_text = display_text[: self.DISPLAY_MAX_CHARS - 1] + "\u2026"

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", self._ALPHA_VISIBLE)
        self.win.configure(bg="#1e1e3c")

        # Content
        self.label = tk.Label(
            self.win,
            text=f"\U0001f3af  {display_text}",
            font=("Helvetica", 13),
            fg="#d0d0ff",
            bg="#1e1e3c",
            padx=28,
            pady=6,
        )
        self.label.pack()

        # Position: top-center of primary monitor
        self.win.update_idletasks()
        bar_w = self.win.winfo_reqwidth()
        screen_w, _ = self._get_screen_size()
        x = (screen_w - bar_w) // 2
        self.win.geometry(f"+{x}+0")

        # Make click-through
        self._set_click_through()

        # Start hover polling (since WS_EX_TRANSPARENT blocks real hover events)
        self._poll_hover()

    @staticmethod
    def _get_screen_size() -> tuple[int, int]:
        """Get actual screen size accounting for DPI scaling on Windows."""
        if platform.system() == 'Windows':
            try:
                import ctypes
                user32 = ctypes.windll.user32
                # Use SM_CXSCREEN/SM_CYSCREEN which return physical pixels
                user32.SetProcessDPIAware()
                w = user32.GetSystemMetrics(0)
                h = user32.GetSystemMetrics(1)
                return w, h
            except Exception:
                pass
        # Fallback
        temp = tk.Tk()
        temp.withdraw()
        w = temp.winfo_screenwidth()
        h = temp.winfo_screenheight()
        temp.destroy()
        return w, h

    def _set_click_through(self) -> None:
        """Make the window pass all mouse events to windows behind it."""
        if platform.system() == 'Windows':
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )

    def _poll_hover(self) -> None:
        """Check if mouse is over the bar and fade accordingly."""
        if self._destroyed:
            return
        try:
            # Get mouse position (screen coords)
            mx = self.win.winfo_pointerx()
            my = self.win.winfo_pointery()
            # Get bar bounds
            bx = self.win.winfo_rootx()
            by = self.win.winfo_rooty()
            bw = self.win.winfo_width()
            bh = self.win.winfo_height()

            over = bx <= mx <= bx + bw and by <= my <= by + bh

            if over and not self._hidden_by_hover:
                self._hidden_by_hover = True
                self.win.attributes("-alpha", self._ALPHA_HIDDEN)
            elif not over and self._hidden_by_hover:
                self._hidden_by_hover = False
                self.win.attributes("-alpha", self._ALPHA_VISIBLE)
        except tk.TclError:
            return

        self.win.after(self._POLL_MS, self._poll_hover)

    def destroy(self) -> None:
        """Remove the bar from screen."""
        if self._destroyed:
            return
        self._destroyed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def show(self) -> None:
        """Re-show the bar (e.g. after app restores from tray)."""
        if not self._destroyed:
            try:
                self.win.deiconify()
                self.win.lift()
            except tk.TclError:
                pass

    def hide(self) -> None:
        """Temporarily hide the bar (e.g. when app minimizes to tray)."""
        if not self._destroyed:
            try:
                self.win.withdraw()
            except tk.TclError:
                pass
