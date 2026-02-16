"""
Settings window for Productivity Timer.
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from typing import Callable

from src.data.config import Config
from src.utils.autostart import is_autostart_enabled, enable_autostart, disable_autostart


class SettingsWindow:
    """
    Settings dialog for configuring timer and blocking options.
    """

    def __init__(
        self,
        parent: ttk.Window,
        config: Config,
        on_save: Callable[[Config], None],
    ):
        """
        Initialize the settings window.

        Args:
            parent: Parent window
            config: Current configuration
            on_save: Callback when settings are saved
        """
        self.parent = parent
        self.config = config
        self.on_save = on_save
        self._saved = False  # Track if user clicked Save

        # Store original values to detect changes
        self._original_values = {
            'work_minutes': config.work_minutes,
            'break_minutes': config.break_minutes,
            'sets_per_session': config.sets_per_session,
            'cooldown_minutes': config.cooldown_minutes,
            'typing_challenge_length': config.typing_challenge_length,
            'start_minimized': config.start_minimized,
            'auto_start': is_autostart_enabled(),
            'ai_nsfw_detection_enabled': config.ai_nsfw_detection_enabled,
            'openai_api_key': config.openai_api_key,
        }

        self._setup_dialog()

    def _setup_dialog(self) -> None:
        """Set up the dialog UI."""
        # Create toplevel window
        self.dialog = ttk.Toplevel(self.parent)
        self.dialog.title("Settings")
        self.dialog.resizable(True, True)  # Allow resizing
        self.dialog.minsize(400, 500)  # Minimum size

        # Handle window close button (X)
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)

        # Main container
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)

        # Timer Settings Section
        timer_label = ttk.Label(
            main_frame,
            text="Timer Settings",
            font=("Helvetica", 14, "bold")
        )
        timer_label.pack(anchor=W, pady=(0, 10))

        timer_frame = ttk.Labelframe(main_frame, text="Duration", padding=10)
        timer_frame.pack(fill=X, pady=(0, 20))

        # Work duration
        work_frame = ttk.Frame(timer_frame)
        work_frame.pack(fill=X, pady=5)

        ttk.Label(work_frame, text="Work Duration (minutes):").pack(side=LEFT)
        self.work_var = ttk.IntVar(value=self.config.work_minutes)
        work_spin = ttk.Spinbox(
            work_frame,
            from_=1,
            to=120,
            textvariable=self.work_var,
            width=10
        )
        work_spin.pack(side=RIGHT)

        # Break duration
        break_frame = ttk.Frame(timer_frame)
        break_frame.pack(fill=X, pady=5)

        ttk.Label(break_frame, text="Break Duration (minutes):").pack(side=LEFT)
        self.break_var = ttk.IntVar(value=self.config.break_minutes)
        break_spin = ttk.Spinbox(
            break_frame,
            from_=1,
            to=60,
            textvariable=self.break_var,
            width=10
        )
        break_spin.pack(side=RIGHT)

        # Sets per session
        sets_frame = ttk.Frame(timer_frame)
        sets_frame.pack(fill=X, pady=5)

        ttk.Label(sets_frame, text="Sets per Session:").pack(side=LEFT)
        self.sets_var = ttk.IntVar(value=self.config.sets_per_session)
        sets_spin = ttk.Spinbox(
            sets_frame,
            from_=1,
            to=10,
            textvariable=self.sets_var,
            width=10
        )
        sets_spin.pack(side=RIGHT)

        # Sets description
        sets_desc = ttk.Label(
            timer_frame,
            text="(Work sessions to complete before you can close the app)",
            font=("Helvetica", 8),
            bootstyle="secondary"
        )
        sets_desc.pack(anchor=W, pady=(0, 5))

        # Disable Guard Settings Section
        guard_label = ttk.Label(
            main_frame,
            text="Disable Guard Settings",
            font=("Helvetica", 14, "bold")
        )
        guard_label.pack(anchor=W, pady=(10, 10))

        guard_frame = ttk.Labelframe(main_frame, text="Protection", padding=10)
        guard_frame.pack(fill=X, pady=(0, 20))

        # Cooldown duration
        cooldown_frame = ttk.Frame(guard_frame)
        cooldown_frame.pack(fill=X, pady=5)

        ttk.Label(cooldown_frame, text="Cooldown (minutes):").pack(side=LEFT)
        self.cooldown_var = ttk.IntVar(value=self.config.cooldown_minutes)
        cooldown_spin = ttk.Spinbox(
            cooldown_frame,
            from_=1,
            to=60,
            textvariable=self.cooldown_var,
            width=10
        )
        cooldown_spin.pack(side=RIGHT)

        # Typing challenge length
        challenge_frame = ttk.Frame(guard_frame)
        challenge_frame.pack(fill=X, pady=5)

        ttk.Label(challenge_frame, text="Typing Challenge Length:").pack(side=LEFT)
        self.challenge_var = ttk.IntVar(value=self.config.typing_challenge_length)
        challenge_spin = ttk.Spinbox(
            challenge_frame,
            from_=100,
            to=5000,
            increment=100,
            textvariable=self.challenge_var,
            width=10
        )
        challenge_spin.pack(side=RIGHT)

        # System Settings Section
        system_label = ttk.Label(
            main_frame,
            text="System Settings",
            font=("Helvetica", 14, "bold")
        )
        system_label.pack(anchor=W, pady=(10, 10))

        system_frame = ttk.Labelframe(main_frame, text="Startup", padding=10)
        system_frame.pack(fill=X, pady=(0, 20))

        # Auto-start at login
        self.autostart_var = ttk.BooleanVar(value=is_autostart_enabled())
        autostart_check = ttk.Checkbutton(
            system_frame,
            text="Start at Login",
            variable=self.autostart_var,
            bootstyle="round-toggle"
        )
        autostart_check.pack(anchor=W, pady=5)

        # Start minimized
        self.minimized_var = ttk.BooleanVar(value=self.config.start_minimized)
        minimized_check = ttk.Checkbutton(
            system_frame,
            text="Start minimized to tray",
            variable=self.minimized_var,
            bootstyle="round-toggle"
        )
        minimized_check.pack(anchor=W, pady=5)

        # AI Content Detection Section
        ai_label = ttk.Label(
            main_frame,
            text="AI Content Detection",
            font=("Helvetica", 14, "bold")
        )
        ai_label.pack(anchor=W, pady=(10, 10))

        ai_frame = ttk.Labelframe(main_frame, text="NSFW Detection", padding=10)
        ai_frame.pack(fill=X, pady=(0, 20))

        # Enable toggle
        self.ai_nsfw_var = ttk.BooleanVar(value=self.config.ai_nsfw_detection_enabled)
        ai_toggle = ttk.Checkbutton(
            ai_frame,
            text="Enable AI NSFW Detection",
            variable=self.ai_nsfw_var,
            bootstyle="round-toggle"
        )
        ai_toggle.pack(anchor=W, pady=5)

        # API Key
        key_frame = ttk.Frame(ai_frame)
        key_frame.pack(fill=X, pady=5)

        ttk.Label(key_frame, text="OpenAI API Key:").pack(side=LEFT)
        self.api_key_var = ttk.StringVar(value=self.config.openai_api_key)
        api_key_entry = ttk.Entry(
            key_frame,
            textvariable=self.api_key_var,
            show='*',
            width=30
        )
        api_key_entry.pack(side=RIGHT, fill=X, expand=YES, padx=(10, 0))

        # Help text
        ai_help = ttk.Label(
            ai_frame,
            text="Uses OpenAI Moderation API (free) + GPT-4o-mini (~$0.00005/check)\nfor ambiguous cases. Detects NSFW sites not in the static blocklist.",
            font=("Helvetica", 8),
            bootstyle="secondary",
            wraplength=380
        )
        ai_help.pack(anchor=W, pady=(5, 0))

        # Buttons
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=X, pady=(20, 0))

        cancel_btn = ttk.Button(
            buttons_frame,
            text="Cancel",
            command=self._on_close,
            bootstyle="secondary",
            width=12
        )
        cancel_btn.pack(side=LEFT)

        save_btn = ttk.Button(
            buttons_frame,
            text="Save",
            command=self._on_save,
            bootstyle="success",
            width=12
        )
        save_btn.pack(side=RIGHT)

        # Finalize dialog - MUST be done AFTER all widgets are created
        self.dialog.update_idletasks()

        # Set size and center on parent
        width = 450
        height = 820  # Increased to accommodate AI detection settings
        x = self.parent.winfo_x() + (self.parent.winfo_width() - width) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - height) // 2
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")

        # Make modal
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.focus_set()

    def _get_current_values(self) -> dict:
        """Get current values from UI widgets."""
        # Force spinbox values to update by focusing away
        self.dialog.focus_set()

        return {
            'work_minutes': self.work_var.get(),
            'break_minutes': self.break_var.get(),
            'sets_per_session': self.sets_var.get(),
            'cooldown_minutes': self.cooldown_var.get(),
            'typing_challenge_length': self.challenge_var.get(),
            'start_minimized': self.minimized_var.get(),
            'auto_start': self.autostart_var.get(),
            'ai_nsfw_detection_enabled': self.ai_nsfw_var.get(),
            'openai_api_key': self.api_key_var.get(),
        }

    def _has_unsaved_changes(self) -> bool:
        """Check if there are unsaved changes."""
        current = self._get_current_values()
        return current != self._original_values

    def _on_close(self) -> None:
        """Handle window close (X button or Cancel)."""
        if self._has_unsaved_changes():
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                parent=self.dialog
            )
            if result is True:  # Yes - save and close
                self._on_save()
            elif result is False:  # No - discard and close
                self.dialog.destroy()
            # None (Cancel) - do nothing, stay open
        else:
            self.dialog.destroy()

    def _on_save(self) -> None:
        """Handle save button click."""
        # Force spinbox values to update
        self.dialog.focus_set()

        # Update config
        self.config.work_minutes = self.work_var.get()
        self.config.break_minutes = self.break_var.get()
        self.config.sets_per_session = self.sets_var.get()
        self.config.cooldown_minutes = self.cooldown_var.get()
        self.config.typing_challenge_length = self.challenge_var.get()
        self.config.start_minimized = self.minimized_var.get()
        self.config.ai_nsfw_detection_enabled = self.ai_nsfw_var.get()
        self.config.openai_api_key = self.api_key_var.get()

        # Handle auto-start
        if self.autostart_var.get():
            enable_autostart()
            self.config.auto_start_windows = True
        else:
            disable_autostart()
            self.config.auto_start_windows = False

        # Save config to file
        self.config.save()

        # Mark as saved
        self._saved = True

        # Notify callback
        self.on_save(self.config)

        print(f"Settings saved: work={self.config.work_minutes}min, break={self.config.break_minutes}min, sets={self.config.sets_per_session}")

        # Close dialog
        self.dialog.destroy()
