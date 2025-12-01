"""
Main application orchestration for Productivity Timer.
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from typing import Optional

from src.utils.constants import TimerState
from src.utils.admin import is_admin
from src.data.config import Config
from src.core.timer import PomodoroTimer
from src.core.process_blocker import ProcessBlocker
from src.core.website_blocker import WebsiteBlocker
from src.core.disable_guard import DisableGuard
from src.core.extension_server import ExtensionServer
from src.ui.main_window import MainWindow
from src.ui.typing_challenge import TypingChallengeDialog
from src.ui.settings_window import SettingsWindow
from src.ui.blocklist_editor import BlocklistEditor
from src.ui.tray_icon import TrayIcon


class ProductivityApp:
    """
    Main application class that orchestrates all components.
    """

    def __init__(self, config: Config, has_admin: bool = False):
        """
        Initialize the application.

        Args:
            config: Application configuration
            has_admin: Whether running with admin privileges
        """
        self.config = config
        self.has_admin = has_admin

        # Initialize root window
        self.root = ttk.Window(themename=config.theme)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Initialize core components
        self._init_timer()
        self._init_blockers()

        # Initialize UI
        self._init_ui()

        # Initialize tray icon
        self._init_tray()

        # Handle start minimized
        if config.start_minimized:
            self.root.withdraw()

    def _init_timer(self) -> None:
        """Initialize the Pomodoro timer."""
        self.timer = PomodoroTimer(
            work_seconds=self.config.work_minutes * 60,
            break_seconds=self.config.break_minutes * 60,
            on_tick=self._on_timer_tick,
            on_state_change=self._on_state_change,
            on_session_complete=self._on_session_complete,
        )

        self.disable_guard = DisableGuard(
            cooldown_seconds=self.config.cooldown_minutes * 60,
            challenge_length=self.config.typing_challenge_length,
        )

    def _init_blockers(self) -> None:
        """Initialize blocking components."""
        blocked_apps = self.config.get_all_blocked_apps()
        blocked_websites = self.config.get_all_blocked_websites()

        self.process_blocker = ProcessBlocker(blocked_apps)
        self.website_blocker = WebsiteBlocker(blocked_websites)

        # Start extension server for browser extension communication
        self.extension_server = ExtensionServer()
        self.extension_server.start()
        self.extension_server.set_blocked_sites(blocked_websites)
        self.extension_server.set_whitelisted_urls(self.config.whitelisted_urls)

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self.main_window = MainWindow(
            root=self.root,
            on_start=self._on_start,
            on_pause=self._on_pause,
            on_stop=self._on_stop,
            on_settings=self._on_settings,
            on_blocklist=self._on_blocklist,
        )

        # Set initial timer display
        self.main_window.set_initial_time(self.config.work_minutes * 60)

    def _init_tray(self) -> None:
        """Initialize the system tray icon."""
        self.tray_icon = TrayIcon(
            on_show=self._on_tray_show,
            on_start=self._on_start,
            on_pause=self._on_pause,
            on_stop=self._on_stop,
            on_settings=self._on_settings,
            on_exit=self._on_exit_request,
        )

        if self.tray_icon.is_available():
            self.tray_icon.start()

    def _on_timer_tick(self, seconds_remaining: int) -> None:
        """Handle timer tick - update UI."""
        # Use after() to update UI from timer thread
        self.root.after(0, lambda: self.main_window.update_timer(seconds_remaining))

        # Update tray tooltip
        minutes = seconds_remaining // 60
        secs = seconds_remaining % 60
        state = self.timer.state.upper()
        self.root.after(
            0,
            lambda: self.tray_icon.update_tooltip(f"{state} - {minutes:02d}:{secs:02d}")
        )

    def _on_state_change(self, new_state: str) -> None:
        """Handle timer state change."""
        self.root.after(0, lambda: self.main_window.update_state(new_state))
        self.root.after(0, lambda: self.tray_icon.update_state(new_state))

        # Start/stop blocking based on state
        if new_state == TimerState.WORKING:
            self._start_blocking()
        elif new_state == TimerState.BREAK:
            self._stop_blocking()
        elif new_state == TimerState.IDLE:
            self._stop_blocking()
            self.disable_guard.end_session()

    def _on_session_complete(self, completed_state: str) -> None:
        """Handle session completion (work or break ended)."""
        if completed_state == TimerState.WORKING:
            # Work session ended - notify user
            self.root.after(0, lambda: self._show_notification("Work session complete! Time for a break."))
        elif completed_state == TimerState.BREAK:
            # Break ended - notify user
            self.root.after(0, lambda: self._show_notification("Break is over! Ready to focus?"))

    def _show_notification(self, message: str) -> None:
        """Show a notification to the user."""
        # Bring window to front
        self.main_window.show()

        # Play system sound (beep)
        self.root.bell()

    def _start_blocking(self) -> None:
        """Start blocking apps and websites."""
        # Start process blocker
        self.process_blocker.start()

        # Start website blocker (if admin)
        if self.has_admin:
            success, error = self.website_blocker.block()
            if not success:
                # Show warning but continue with app blocking
                self.root.after(0, lambda: messagebox.showwarning(
                    "Website Blocking Failed",
                    f"Could not block websites:\n{error}\n\n"
                    "App blocking is still active.\n"
                    "Make sure you're running as Administrator."
                ))
            else:
                # Verify blocking is active
                is_active, status = self.website_blocker.verify_blocking_active()
                if is_active:
                    print(f"Website blocking: {status}")

        # Update extension server state (for browser extension sync)
        self.extension_server.set_blocking_state(True)
        self.extension_server.reset_block_count()

        # Start disable guard session
        self.disable_guard.start_session()

    def _stop_blocking(self) -> None:
        """Stop blocking apps and websites."""
        self.process_blocker.stop()

        if self.has_admin:
            success, error = self.website_blocker.unblock()
            if not success:
                print(f"Warning: Could not unblock websites: {error}")

        # Update extension server state (for browser extension sync)
        self.extension_server.set_blocking_state(False)

    def _on_start(self) -> None:
        """Handle start button click."""
        if self.timer.state == TimerState.IDLE:
            self.timer.start_work()
        elif self.timer.state == TimerState.PAUSED:
            self.timer.resume()

    def _on_pause(self) -> None:
        """Handle pause button click."""
        if self.timer.state in (TimerState.WORKING, TimerState.BREAK):
            self.timer.pause()

    def _on_stop(self) -> None:
        """Handle stop button click - requires disable guard."""
        if self.timer.state == TimerState.IDLE:
            return

        # Check if we're in a protected session
        if self.timer.state == TimerState.WORKING and self.disable_guard.is_session_active():
            self._show_disable_challenge()
        else:
            # Not in work mode or not protected - allow stop
            self._do_stop()

    def _show_disable_challenge(self) -> None:
        """Show the disable challenge dialog."""
        cooldown_remaining = self.disable_guard.get_cooldown_remaining()
        challenge_text = self.disable_guard.generate_challenge_text()

        TypingChallengeDialog(
            parent=self.root,
            challenge_text=challenge_text,
            cooldown_remaining=cooldown_remaining,
            on_complete=self._do_stop,
            on_cancel=lambda: None,  # Do nothing on cancel
            on_cooldown_disable=self._do_stop if cooldown_remaining == 0 else lambda: None,
        )

    def _do_stop(self) -> None:
        """Actually stop the timer and blocking."""
        self.timer.stop()
        self._stop_blocking()
        self.disable_guard.end_session()
        self.main_window.update_state(TimerState.IDLE)
        self.main_window.set_initial_time(self.config.work_minutes * 60)

    def _on_settings(self) -> None:
        """Handle settings button click."""
        if self.timer.state != TimerState.IDLE:
            messagebox.showwarning(
                "Settings Locked",
                "Settings cannot be changed during an active session."
            )
            return

        SettingsWindow(
            parent=self.root,
            config=self.config,
            on_save=self._on_settings_save,
        )

    def _on_settings_save(self, config: Config) -> None:
        """Handle settings save."""
        self.config = config

        # Update timer durations
        self.timer.update_durations(
            work_seconds=config.work_minutes * 60,
            break_seconds=config.break_minutes * 60,
        )

        # Update disable guard settings
        self.disable_guard.update_settings(
            cooldown_seconds=config.cooldown_minutes * 60,
            challenge_length=config.typing_challenge_length,
        )

        # Update initial display
        self.main_window.set_initial_time(config.work_minutes * 60)

    def _on_blocklist(self) -> None:
        """Handle blocklist button click."""
        if self.timer.state != TimerState.IDLE:
            messagebox.showwarning(
                "Block Lists Locked",
                "Block lists cannot be changed during an active session."
            )
            return

        BlocklistEditor(
            parent=self.root,
            config=self.config,
            on_save=self._on_blocklist_save,
        )

    def _on_blocklist_save(self, config: Config) -> None:
        """Handle blocklist save."""
        self.config = config

        # Update blockers with new lists
        blocked_websites = config.get_all_blocked_websites()
        self.process_blocker.update_blocked_apps(config.get_all_blocked_apps())
        self.website_blocker.update_blocked_sites(blocked_websites)

        # Update extension server with new blocked sites
        self.extension_server.set_blocked_sites(blocked_websites)

    def _on_tray_show(self) -> None:
        """Handle tray icon show click."""
        self.main_window.show()

    def _on_close(self) -> None:
        """Handle window close - minimize to tray or block during work."""
        # During work session, only allow minimize to tray (not close)
        if self.timer.state == TimerState.WORKING:
            if self.tray_icon.is_available():
                self.main_window.hide()
            # If no tray, just ignore the close - can't escape that easily!
            return

        if self.tray_icon.is_available():
            self.main_window.hide()
        else:
            self._on_exit()

    def _on_exit_request(self) -> None:
        """Handle exit request - requires challenge during work session."""
        if self.timer.state == TimerState.WORKING and self.disable_guard.is_session_active():
            # Show the window so user can see the challenge
            self.main_window.show()
            self._show_exit_challenge()
        else:
            self._on_exit()

    def _show_exit_challenge(self) -> None:
        """Show the exit challenge dialog."""
        cooldown_remaining = self.disable_guard.get_cooldown_remaining()
        challenge_text = self.disable_guard.generate_challenge_text()

        TypingChallengeDialog(
            parent=self.root,
            challenge_text=challenge_text,
            cooldown_remaining=cooldown_remaining,
            on_complete=self._on_exit,
            on_cancel=lambda: None,  # Do nothing on cancel
            on_cooldown_disable=self._on_exit if cooldown_remaining == 0 else lambda: None,
        )

    def _on_exit(self) -> None:
        """Handle application exit."""
        # Stop everything
        self.timer.stop()
        self._stop_blocking()
        self.tray_icon.stop()
        self.extension_server.stop()

        # Destroy window
        self.root.quit()
        self.root.destroy()

    def run(self) -> None:
        """Run the application main loop."""
        self.root.mainloop()
