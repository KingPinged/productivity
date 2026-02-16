"""
Main window UI for Productivity Timer.
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from typing import Callable, Optional

from src.utils.constants import TimerState


class MainWindow:
    """
    Main application window displaying timer and controls.
    """

    def __init__(
        self,
        root: ttk.Window,
        on_start: Callable,
        on_pause: Callable,
        on_stop: Callable,
        on_settings: Callable,
        on_blocklist: Callable,
        on_usage_stats: Optional[Callable] = None,
    ):
        """
        Initialize the main window.

        Args:
            root: The ttkbootstrap root window
            on_start: Callback when Start button clicked
            on_pause: Callback when Pause button clicked
            on_stop: Callback when Stop button clicked
            on_settings: Callback when Settings button clicked
            on_blocklist: Callback when Block Lists button clicked
            on_usage_stats: Callback when Usage Stats button clicked
        """
        self.root = root
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_stop = on_stop
        self.on_settings = on_settings
        self.on_blocklist = on_blocklist
        self.on_usage_stats = on_usage_stats

        self._current_state = TimerState.IDLE
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        # Configure window
        self.root.title("Productivity Timer")
        self.root.geometry("400x550")
        self.root.resizable(False, False)

        # Main container
        self.main_frame = ttk.Frame(self.root, padding=15)
        self.main_frame.pack(fill=BOTH, expand=YES)

        # Title
        title_label = ttk.Label(
            self.main_frame,
            text="Productivity Timer",
            font=("Helvetica", 18, "bold"),
            bootstyle="inverse-primary"
        )
        title_label.pack(pady=(0, 20))

        # Timer display frame
        timer_frame = ttk.Frame(self.main_frame)
        timer_frame.pack(pady=10)

        # Timer label (large)
        self.timer_label = ttk.Label(
            timer_frame,
            text="52:00",
            font=("Helvetica", 64, "bold"),
            bootstyle="primary"
        )
        self.timer_label.pack()

        # State label
        self.state_label = ttk.Label(
            timer_frame,
            text="IDLE",
            font=("Helvetica", 16),
            bootstyle="secondary"
        )
        self.state_label.pack(pady=(5, 0))

        # Cycle counter frame
        cycle_frame = ttk.Frame(self.main_frame)
        cycle_frame.pack(pady=(15, 5))

        # Cycle counter label - shows "Today: X | Total: Y"
        self.cycle_label = ttk.Label(
            cycle_frame,
            text="Today: 0 | Total: 0",
            font=("Helvetica", 12),
            bootstyle="info"
        )
        self.cycle_label.pack()

        # Sets progress frame
        sets_frame = ttk.Frame(self.main_frame)
        sets_frame.pack(pady=(5, 10))

        # Sets progress label - shows "Sets: X/Y"
        self.sets_label = ttk.Label(
            sets_frame,
            text="Sets: 0/3",
            font=("Helvetica", 14, "bold"),
            bootstyle="warning"
        )
        self.sets_label.pack()

        # Control buttons frame
        controls_frame = ttk.Frame(self.main_frame)
        controls_frame.pack(pady=15)

        # Start button
        self.start_btn = ttk.Button(
            controls_frame,
            text="Start",
            command=self._on_start_click,
            bootstyle="success",
            width=10
        )
        self.start_btn.pack(side=LEFT, padx=5)

        # Pause button
        self.pause_btn = ttk.Button(
            controls_frame,
            text="Pause",
            command=self._on_pause_click,
            bootstyle="warning",
            width=10,
            state=DISABLED
        )
        self.pause_btn.pack(side=LEFT, padx=5)

        # Stop button
        self.stop_btn = ttk.Button(
            controls_frame,
            text="Stop",
            command=self._on_stop_click,
            bootstyle="danger",
            width=10,
            state=DISABLED
        )
        self.stop_btn.pack(side=LEFT, padx=5)

        # Bottom buttons frame
        bottom_frame = ttk.Frame(self.main_frame)
        bottom_frame.pack(pady=(20, 0), fill=X)

        # Settings button
        self.settings_btn = ttk.Button(
            bottom_frame,
            text="Settings",
            command=self.on_settings,
            bootstyle="secondary-outline",
            width=15
        )
        self.settings_btn.pack(side=LEFT, padx=5, expand=YES)

        # Block Lists button
        self.blocklist_btn = ttk.Button(
            bottom_frame,
            text="Block Lists",
            command=self.on_blocklist,
            bootstyle="secondary-outline",
            width=15
        )
        self.blocklist_btn.pack(side=RIGHT, padx=5, expand=YES)

        # Usage Stats button (centered below)
        stats_frame = ttk.Frame(self.main_frame)
        stats_frame.pack(pady=(10, 0), fill=X)

        self.usage_stats_btn = ttk.Button(
            stats_frame,
            text="Usage Stats",
            command=self._on_usage_stats_click,
            bootstyle="info-outline",
            width=20
        )
        self.usage_stats_btn.pack()

    def _on_usage_stats_click(self) -> None:
        """Handle Usage Stats button click."""
        if self.on_usage_stats:
            self.on_usage_stats()

    def _on_start_click(self) -> None:
        """Handle Start button click."""
        self.on_start()

    def _on_pause_click(self) -> None:
        """Handle Pause button click."""
        self.on_pause()

    def _on_stop_click(self) -> None:
        """Handle Stop button click."""
        self.on_stop()

    def update_timer(self, seconds: int) -> None:
        """
        Update the timer display.

        Args:
            seconds: Remaining time in seconds
        """
        minutes = seconds // 60
        secs = seconds % 60
        self.timer_label.config(text=f"{minutes:02d}:{secs:02d}")

    def update_state(self, state: str) -> None:
        """
        Update the state display and button states.

        Args:
            state: Current timer state
        """
        self._current_state = state

        # Update state label
        state_text = state.upper()
        self.state_label.config(text=state_text)

        # Update label colors based on state
        if state == TimerState.WORKING:
            self.timer_label.config(bootstyle="danger")
            self.state_label.config(bootstyle="danger")
        elif state == TimerState.BREAK:
            self.timer_label.config(bootstyle="success")
            self.state_label.config(bootstyle="success")
        elif state == TimerState.PAUSED:
            self.timer_label.config(bootstyle="warning")
            self.state_label.config(bootstyle="warning")
        else:  # IDLE
            self.timer_label.config(bootstyle="primary")
            self.state_label.config(bootstyle="secondary")

        # Update button states
        if state == TimerState.IDLE:
            self.start_btn.config(state=NORMAL, text="Start", bootstyle="success")
            self.pause_btn.config(state=DISABLED)
            self.stop_btn.config(state=DISABLED)
            self.settings_btn.config(state=NORMAL)
            self.blocklist_btn.config(state=NORMAL)
        elif state == TimerState.WORKING:
            self.start_btn.config(state=DISABLED, text="Start", bootstyle="success")
            self.pause_btn.config(state=NORMAL, text="Pause")
            self.stop_btn.config(state=NORMAL)
            self.settings_btn.config(state=DISABLED)
            self.blocklist_btn.config(state=DISABLED)
        elif state == TimerState.BREAK:
            self.start_btn.config(state=NORMAL, text="Skip Break", bootstyle="info")
            self.pause_btn.config(state=NORMAL, text="Pause")
            self.stop_btn.config(state=NORMAL)
            self.settings_btn.config(state=DISABLED)
            self.blocklist_btn.config(state=DISABLED)
        elif state == TimerState.PAUSED:
            self.start_btn.config(state=NORMAL, text="Resume", bootstyle="success")
            self.pause_btn.config(state=DISABLED)
            self.stop_btn.config(state=NORMAL)
            self.settings_btn.config(state=DISABLED)
            self.blocklist_btn.config(state=DISABLED)

    def show(self) -> None:
        """Show the main window."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self) -> None:
        """Hide the main window (minimize to tray)."""
        self.root.withdraw()

    def set_initial_time(self, seconds: int) -> None:
        """Set the initial timer display."""
        self.update_timer(seconds)

    def update_cycle_count(self, today: int, total: int) -> None:
        """
        Update the cycle counter display.

        Args:
            today: Number of cycles completed today
            total: Total lifetime cycles completed
        """
        self.cycle_label.config(text=f"Today: {today} | Total: {total}")

    def update_sets_progress(self, completed: int, total: int) -> None:
        """
        Update the sets progress display.

        Args:
            completed: Number of sets completed in current session
            total: Total sets required
        """
        self.sets_label.config(text=f"Sets: {completed}/{total}")

        # Update color based on progress
        if completed == 0:
            self.sets_label.config(bootstyle="secondary")
        elif completed >= total:
            self.sets_label.config(bootstyle="success")
        else:
            self.sets_label.config(bootstyle="warning")
