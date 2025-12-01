"""
Typing challenge dialog for disabling the blocker.
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from typing import Callable, Optional


class TypingChallengeDialog:
    """
    Modal dialog that requires typing a long random string to disable blocking.
    Anti-bypass measures:
    - Text cannot be selected/copied
    - Paste is disabled
    - Character-by-character validation
    """

    def __init__(
        self,
        parent: ttk.Window,
        challenge_text: str,
        cooldown_remaining: int,
        on_complete: Callable,
        on_cancel: Callable,
        on_cooldown_disable: Callable,
    ):
        """
        Initialize the typing challenge dialog.

        Args:
            parent: Parent window
            challenge_text: The text user must type
            cooldown_remaining: Seconds remaining in cooldown (0 if can quick disable)
            on_complete: Callback when challenge completed successfully
            on_cancel: Callback when user cancels
            on_cooldown_disable: Callback when user chooses to wait for cooldown
        """
        self.parent = parent
        self.challenge_text = challenge_text
        self.cooldown_remaining = cooldown_remaining
        self.on_complete = on_complete
        self.on_cancel = on_cancel
        self.on_cooldown_disable = on_cooldown_disable

        self._correct_count = 0
        self._window_visible = True

        self._setup_dialog()

    def _setup_dialog(self) -> None:
        """Set up the dialog UI."""
        # Create toplevel window
        self.dialog = ttk.Toplevel(self.parent)
        self.dialog.title("Disable Blocking")
        self.dialog.geometry("550x400")
        self.dialog.resizable(False, False)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # Make it modal
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Center on parent
        self.dialog.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - 550) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - 400) // 2
        self.dialog.geometry(f"+{x}+{y}")

        # Main container
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)

        # Instructions
        instruction_label = ttk.Label(
            main_frame,
            text="Type the following text to disable blocking:",
            font=("Helvetica", 12, "bold")
        )
        instruction_label.pack(anchor=W, pady=(0, 10))

        # Challenge text display (non-selectable)
        challenge_frame = ttk.Frame(main_frame, bootstyle="dark")
        challenge_frame.pack(fill=X, pady=10)

        self.challenge_label = ttk.Label(
            challenge_frame,
            text=self._get_visible_text(),
            font=("Consolas", 14),
            bootstyle="inverse-dark",
            wraplength=500,
            padding=10
        )
        self.challenge_label.pack(fill=X)

        # Disable text selection on challenge label
        self.challenge_label.bind("<Button-1>", lambda e: "break")
        self.challenge_label.bind("<B1-Motion>", lambda e: "break")
        self.challenge_label.bind("<Double-Button-1>", lambda e: "break")
        self.challenge_label.bind("<Triple-Button-1>", lambda e: "break")

        # Input field
        input_label = ttk.Label(
            main_frame,
            text="Type here:",
            font=("Helvetica", 10)
        )
        input_label.pack(anchor=W, pady=(20, 5))

        self.input_field = ttk.Entry(
            main_frame,
            font=("Consolas", 12),
            width=50
        )
        self.input_field.pack(fill=X)
        self.input_field.focus_set()

        # Bind events
        self.input_field.bind("<KeyRelease>", self._on_key_release)
        self.input_field.bind("<Control-v>", lambda e: "break")  # Block paste
        self.input_field.bind("<Control-V>", lambda e: "break")
        self.input_field.bind("<Button-3>", lambda e: "break")   # Block right-click

        # Progress display
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=X, pady=20)

        self.progress_label = ttk.Label(
            progress_frame,
            text=f"Progress: 0/{len(self.challenge_text)} characters",
            font=("Helvetica", 10)
        )
        self.progress_label.pack(anchor=W)

        # Progress bar
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            length=510,
            maximum=len(self.challenge_text),
            value=0,
            bootstyle="success-striped"
        )
        self.progress_bar.pack(fill=X, pady=(5, 0))

        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=X, pady=(20, 0))

        # Cancel button
        cancel_btn = ttk.Button(
            buttons_frame,
            text="Cancel",
            command=self._on_cancel,
            bootstyle="secondary",
            width=12
        )
        cancel_btn.pack(side=LEFT)

        # Cooldown button (if cooldown not complete)
        if self.cooldown_remaining > 0:
            self.cooldown_btn = ttk.Button(
                buttons_frame,
                text=self._format_cooldown_button(),
                command=self._on_cooldown_disable,
                bootstyle="primary-outline",
                width=20,
                state=DISABLED
            )
            self.cooldown_btn.pack(side=RIGHT)

            # Start cooldown update timer
            self._update_cooldown()
        else:
            # Cooldown complete - show enabled button
            self.cooldown_btn = ttk.Button(
                buttons_frame,
                text="Quick Disable",
                command=self._on_cooldown_disable,
                bootstyle="primary",
                width=20
            )
            self.cooldown_btn.pack(side=RIGHT)

    def _get_visible_text(self) -> str:
        """Get the portion of challenge text to display."""
        # Show next 50 characters from current position
        start = self._correct_count
        end = min(start + 50, len(self.challenge_text))
        text = self.challenge_text[start:end]

        if end < len(self.challenge_text):
            text += "..."

        return text

    def _on_key_release(self, event) -> None:
        """Handle key release in input field."""
        typed_text = self.input_field.get()

        # Validate character by character
        correct = 0
        for i, char in enumerate(typed_text):
            if i < len(self.challenge_text) and char == self.challenge_text[i]:
                correct += 1
            else:
                # Wrong character - reset to last correct position
                self.input_field.delete(correct, END)
                break

        self._correct_count = correct

        # Update progress
        self.progress_label.config(
            text=f"Progress: {correct}/{len(self.challenge_text)} characters"
        )
        self.progress_bar.config(value=correct)

        # Update visible challenge text
        self.challenge_label.config(text=self._get_visible_text())

        # Check if complete
        if correct >= len(self.challenge_text):
            self.dialog.destroy()
            self.on_complete()

    def _format_cooldown_button(self) -> str:
        """Format the cooldown button text."""
        mins = self.cooldown_remaining // 60
        secs = self.cooldown_remaining % 60
        return f"Or Wait {mins}:{secs:02d}"

    def _update_cooldown(self) -> None:
        """Update cooldown timer."""
        if not self._window_visible:
            return

        self.cooldown_remaining -= 1

        if self.cooldown_remaining <= 0:
            self.cooldown_btn.config(
                text="Quick Disable",
                state=NORMAL,
                bootstyle="primary"
            )
        else:
            self.cooldown_btn.config(text=self._format_cooldown_button())
            # Schedule next update
            self.dialog.after(1000, self._update_cooldown)

    def _on_cancel(self) -> None:
        """Handle cancel button or window close."""
        self._window_visible = False
        self.dialog.destroy()
        self.on_cancel()

    def _on_cooldown_disable(self) -> None:
        """Handle cooldown disable button."""
        self._window_visible = False
        self.dialog.destroy()
        self.on_cooldown_disable()

    def show(self) -> None:
        """Show the dialog and wait for it to close."""
        self.dialog.wait_window()
