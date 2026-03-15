"""Frameless always-on-top bar showing session intention at top of screen."""

import tkinter as tk


class IntentionBar:
    """
    Slim overlay bar pinned to the top-center of the primary monitor.
    Becomes near-invisible on hover, reappears on mouse leave.
    """

    DISPLAY_MAX_CHARS = 80

    def __init__(self, root: tk.Tk, intention: str):
        """
        Args:
            root: The main tkinter root window
            intention: The intention text to display
        """
        self.root = root
        self._destroyed = False

        # Truncate for display
        display_text = intention
        if len(display_text) > self.DISPLAY_MAX_CHARS:
            display_text = display_text[: self.DISPLAY_MAX_CHARS - 1] + "\u2026"

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.92)
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
        screen_w = self.win.winfo_screenwidth()
        x = (screen_w - bar_w) // 2
        self.win.geometry(f"+{x}+0")

        # Hover bindings
        self.win.bind("<Enter>", self._on_enter)
        self.win.bind("<Leave>", self._on_leave)
        self.label.bind("<Enter>", self._on_enter)
        self.label.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event) -> None:
        if not self._destroyed:
            self.win.attributes("-alpha", 0.02)

    def _on_leave(self, _event) -> None:
        if not self._destroyed:
            self.win.attributes("-alpha", 0.92)

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
