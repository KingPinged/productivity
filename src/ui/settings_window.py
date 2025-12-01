"""
Settings window for Productivity Timer.
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
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

        self._setup_dialog()

    def _setup_dialog(self) -> None:
        """Set up the dialog UI."""
        # Create toplevel window
        self.dialog = ttk.Toplevel(self.parent)
        self.dialog.title("Settings")
        self.dialog.geometry("450x500")
        self.dialog.resizable(False, False)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # Center on parent
        self.dialog.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - 450) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - 500) // 2
        self.dialog.geometry(f"+{x}+{y}")

        # Main container with scrollable frame
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)

        # Timer Settings Section
        timer_label = ttk.Label(
            main_frame,
            text="Timer Settings",
            font=("Helvetica", 14, "bold")
        )
        timer_label.pack(anchor=W, pady=(0, 10))

        timer_frame = ttk.LabelFrame(main_frame, text="Duration", padding=10)
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

        # Disable Guard Settings Section
        guard_label = ttk.Label(
            main_frame,
            text="Disable Guard Settings",
            font=("Helvetica", 14, "bold")
        )
        guard_label.pack(anchor=W, pady=(10, 10))

        guard_frame = ttk.LabelFrame(main_frame, text="Protection", padding=10)
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

        system_frame = ttk.LabelFrame(main_frame, text="Startup", padding=10)
        system_frame.pack(fill=X, pady=(0, 20))

        # Auto-start with Windows
        self.autostart_var = ttk.BooleanVar(value=is_autostart_enabled())
        autostart_check = ttk.Checkbutton(
            system_frame,
            text="Start with Windows",
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

        # Buttons
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=X, pady=(20, 0))

        cancel_btn = ttk.Button(
            buttons_frame,
            text="Cancel",
            command=self.dialog.destroy,
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

    def _on_save(self) -> None:
        """Handle save button click."""
        # Update config
        self.config.work_minutes = self.work_var.get()
        self.config.break_minutes = self.break_var.get()
        self.config.cooldown_minutes = self.cooldown_var.get()
        self.config.typing_challenge_length = self.challenge_var.get()
        self.config.start_minimized = self.minimized_var.get()

        # Handle auto-start
        if self.autostart_var.get():
            enable_autostart()
            self.config.auto_start_windows = True
        else:
            disable_autostart()
            self.config.auto_start_windows = False

        # Save config to file
        self.config.save()

        # Notify callback
        self.on_save(self.config)

        # Close dialog
        self.dialog.destroy()
