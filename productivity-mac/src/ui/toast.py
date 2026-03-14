"""
Toast notification widget for Productivity Timer.
Displays a subtle, always-on-top notification at the top-right of the screen
that fades out and self-destructs.
"""

import tkinter as tk


class Toast:
    """A frameless, always-on-top toast that fades away."""

    # Track active toasts to stack them
    _active_toasts: list["Toast"] = []

    def __init__(
        self,
        root: tk.Tk,
        message: str,
        *,
        duration_ms: int = 3000,
        fade_ms: int = 800,
        bg: str = "#1a1a2e",
        fg: str = "#e0e0e0",
        accent: str = "#e94560",
    ):
        self.root = root
        self.duration_ms = duration_ms
        self.fade_ms = fade_ms
        self._destroyed = False

        # Create frameless toplevel
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.92)
        self.win.configure(bg=accent)

        # Inner frame with padding to create accent border effect
        inner = tk.Frame(self.win, bg=bg, padx=14, pady=10)
        inner.pack(padx=(3, 0), pady=0, fill="both", expand=True)  # left accent bar

        label = tk.Label(
            inner,
            text=message,
            font=("Helvetica", 11),
            bg=bg,
            fg=fg,
            anchor="w",
            justify="left",
        )
        label.pack()

        # Position at top-right of screen, stacking below existing toasts
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        screen_w = self.win.winfo_screenwidth()
        margin = 16
        slot = len(Toast._active_toasts)
        x = screen_w - w - margin
        y = margin + slot * (h + 8)
        self.win.geometry(f"+{x}+{y}")

        Toast._active_toasts.append(self)

        # Schedule fade-out after duration
        self._fade_after_id = self.win.after(self.duration_ms, self._start_fade)

    def _start_fade(self, step: int = 0) -> None:
        if self._destroyed:
            return
        total_steps = max(1, self.fade_ms // 30)
        alpha = 0.92 * (1 - step / total_steps)
        if alpha <= 0.05 or step >= total_steps:
            self._destroy()
            return
        try:
            self.win.attributes("-alpha", alpha)
            self.win.after(30, lambda: self._start_fade(step + 1))
        except tk.TclError:
            pass  # window already gone

    def _destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self in Toast._active_toasts:
            Toast._active_toasts.remove(self)
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class TimerToastManager:
    """
    Manages toast notifications at critical timer milestones.
    Tracks which milestones have already fired so each shows only once per session.
    """

    # Milestones as fractions of total time
    MILESTONES = {
        0.50: "Half time",
        0.25: "Quarter time left",
        0.10: "10% remaining",
    }
    # Absolute second thresholds
    ABSOLUTE = {
        300: "5 minutes left",
        60: "1 minute left",
        30: "30 seconds left",
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self._fired: set[str] = set()  # milestone keys already shown
        self._current_total: int = 0  # total seconds for current session

    def reset(self) -> None:
        """Reset fired milestones (call on state change)."""
        self._fired.clear()
        self._current_total = 0

    def set_total(self, total_seconds: int) -> None:
        """Set the total duration for the current session."""
        self._current_total = total_seconds

    def check(self, remaining: int, state: str) -> None:
        """
        Check if a milestone toast should fire.
        Call this on every tick.
        """
        if state not in ("working", "break") or self._current_total <= 0:
            return

        prefix = "Work" if state == "working" else "Break"

        # Check fraction-based milestones
        fraction = remaining / self._current_total
        for threshold, label in self.MILESTONES.items():
            key = f"frac_{threshold}"
            if key not in self._fired and fraction <= threshold:
                # Only show if remaining > all absolute thresholds that would also fire
                # to avoid double-notifications at the same moment
                if remaining > 60:
                    self._fired.add(key)
                    mins = remaining // 60
                    secs = remaining % 60
                    time_str = f"{mins}:{secs:02d}" if mins > 0 else f"{secs}s"
                    self._show(f"{prefix}: {label}  ({time_str})")
                else:
                    self._fired.add(key)  # suppress, absolute will cover it

        # Check absolute thresholds
        for secs_threshold, label in self.ABSOLUTE.items():
            key = f"abs_{secs_threshold}"
            # Fire when we cross the threshold (remaining <= threshold but not yet fired)
            # Don't fire if total session is shorter than 2x the threshold (avoid noise)
            if (
                key not in self._fired
                and remaining <= secs_threshold
                and self._current_total >= secs_threshold * 2
            ):
                self._fired.add(key)
                accent = "#e94560" if state == "working" else "#0f9b58"
                self._show(f"{prefix}: {label}", accent=accent)

    def _show(self, message: str, accent: str = "#e94560") -> None:
        Toast(self.root, message, accent=accent)
