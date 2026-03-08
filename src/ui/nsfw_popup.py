"""
Always-on-top NSFW violation popup with strike counter.
Shows when user visits an NSFW site, displaying current strike count
and how many strikes remain before WiFi is disabled.
"""

import tkinter as tk


class NSFWStrikePopup:
    """
    Always-on-top popup that warns the user about NSFW violations.
    Cannot be dismissed for 3 seconds.
    """

    def __init__(
        self,
        parent: tk.Tk,
        strike_count: int,
        max_strikes: int,
        punishment_hours: int,
        domain: str = "",
    ):
        self.parent = parent
        self.strike_count = strike_count
        self.max_strikes = max_strikes
        self.punishment_hours = punishment_hours
        self.domain = domain

        self._build_popup()

    def _build_popup(self) -> None:
        """Build and display the popup window."""
        self.popup = tk.Toplevel(self.parent)
        self.popup.title("NSFW VIOLATION")
        self.popup.configure(bg="#1a1a2e")

        # Always on top, block close button
        self.popup.attributes("-topmost", True)
        self.popup.overrideredirect(False)
        self.popup.protocol("WM_DELETE_WINDOW", lambda: None)

        # Size and center on screen
        width, height = 500, 320
        screen_w = self.popup.winfo_screenwidth()
        screen_h = self.popup.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.popup.geometry(f"{width}x{height}+{x}+{y}")

        # Main container
        container = tk.Frame(self.popup, bg="#1a1a2e", padx=30, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        # Header
        header = tk.Label(
            container,
            text="NSFW VIOLATION",
            font=("Helvetica", 22, "bold"),
            fg="#ff4757",
            bg="#1a1a2e",
        )
        header.pack(pady=(10, 5))

        # Domain that triggered it
        if self.domain:
            domain_label = tk.Label(
                container,
                text=f"Detected: {self.domain}",
                font=("Helvetica", 10),
                fg="#a0a0a0",
                bg="#1a1a2e",
            )
            domain_label.pack(pady=(0, 10))

        # Strike counter
        strikes_remaining = max(0, self.max_strikes - self.strike_count)
        strike_text = f"Strike {self.strike_count} / {self.max_strikes}"

        strike_label = tk.Label(
            container,
            text=strike_text,
            font=("Helvetica", 28, "bold"),
            fg="#ffa502",
            bg="#1a1a2e",
        )
        strike_label.pack(pady=(10, 5))

        # Warning message
        if strikes_remaining > 0:
            warn_text = (
                f"{strikes_remaining} more violation{'s' if strikes_remaining != 1 else ''} "
                f"until WiFi is disabled for {self.punishment_hours} hours"
            )
            warn_color = "#ffa502"
        else:
            warn_text = (
                f"WiFi has been DISABLED for {self.punishment_hours} hours.\n"
                "This cannot be bypassed."
            )
            warn_color = "#ff4757"

        warn_label = tk.Label(
            container,
            text=warn_text,
            font=("Helvetica", 12),
            fg=warn_color,
            bg="#1a1a2e",
            wraplength=420,
        )
        warn_label.pack(pady=(5, 20))

        # Dismiss button (disabled for 3 seconds)
        self.dismiss_btn = tk.Button(
            container,
            text="Dismiss (3s)",
            font=("Helvetica", 11),
            fg="#ffffff",
            bg="#444444",
            activebackground="#555555",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            state=tk.DISABLED,
            command=self._dismiss,
            padx=20,
            pady=8,
        )
        self.dismiss_btn.pack(pady=(10, 0))

        # Start countdown to enable dismiss
        self._countdown(3)

        # Force focus
        self.popup.focus_force()
        self.popup.grab_set()

    def _countdown(self, seconds_left: int) -> None:
        """Countdown before dismiss button becomes active."""
        if seconds_left > 0:
            self.dismiss_btn.configure(text=f"Dismiss ({seconds_left}s)")
            self.popup.after(1000, lambda: self._countdown(seconds_left - 1))
        else:
            self.dismiss_btn.configure(
                text="Dismiss",
                state=tk.NORMAL,
                bg="#e74c3c",
            )

    def _dismiss(self) -> None:
        """Dismiss the popup."""
        try:
            self.popup.grab_release()
            self.popup.destroy()
        except tk.TclError:
            pass
