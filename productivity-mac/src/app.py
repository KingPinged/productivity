"""
Main application orchestration for Productivity Timer (macOS).
"""

import time
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from typing import Optional

from src.utils.constants import TimerState
from src.utils.admin import is_admin
from src.data.config import Config
from src.data.default_blocklists import get_adult_sites
from src.data.nsfw_cache import NSFWCache
from src.core.nsfw_detector import NSFWDetector, PageSignals
from src.core.timer import PomodoroTimer
from src.core.process_blocker import ProcessBlocker
from src.core.website_blocker import WebsiteBlocker
from src.core.disable_guard import DisableGuard
from src.core.extension_server import ExtensionServer, ExtensionRequestHandler
from src.core.afk_detector import AFKDetector
from src.core.internet_disabler import InternetDisabler
from src.core.usage_tracker import UsageTracker
from src.data.usage_data import UsageData
from src.ui.main_window import MainWindow
from src.ui.typing_challenge import TypingChallengeDialog
from src.ui.settings_window import SettingsWindow
from src.ui.blocklist_editor import BlocklistEditor
from src.ui.tray_icon import TrayIcon
from src.ui.desktop_stats import DesktopStatsWidget, StatsData
from src.ui.usage_stats_window import UsageStatsWindow


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

        # Sets tracking - tracks work sessions completed in current session
        self._sets_completed = 0
        self._session_active = False  # True when user has started working on sets
        self._is_blocking = False  # Prevent redundant start/stop blocking calls

        # Initialize root window
        self.root = ttk.Window(themename=config.theme)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Initialize core components
        self._init_timer()
        self._init_blockers()
        self._init_nsfw_detection()

        # Initialize UI
        self._init_ui()

        # Initialize tray icon
        self._init_tray()

        # Initialize usage tracking (must be before desktop stats)
        self._init_usage_tracking()

        # Initialize desktop stats widget
        self._init_desktop_stats()

        # Handle start minimized
        if config.start_minimized:
            self.root.withdraw()

    def _init_timer(self) -> None:
        """Initialize the Pomodoro timer and AFK detector."""
        self.afk_detector = AFKDetector(
            afk_threshold_seconds=self.config.afk_threshold_minutes * 60
        )

        self.timer = PomodoroTimer(
            work_seconds=self.config.work_minutes * 60,
            break_seconds=self.config.break_minutes * 60,
            on_tick=self._on_timer_tick,
            on_state_change=self._on_state_change,
            on_session_complete=self._on_session_complete,
            afk_check=self.afk_detector.is_afk,
        )

        self.disable_guard = DisableGuard(
            cooldown_seconds=self.config.cooldown_minutes * 60,
            challenge_length=self.config.typing_challenge_length,
        )

    def _init_blockers(self) -> None:
        """Initialize blocking components."""
        blocked_apps = self.config.get_all_blocked_apps()
        blocked_websites = self.config.get_all_blocked_websites()
        adult_sites = get_adult_sites()

        self.process_blocker = ProcessBlocker(blocked_apps)
        self.website_blocker = WebsiteBlocker(
            blocked_websites, adult_sites, self.config.whitelisted_urls
        )

        # Start extension server for browser extension communication
        self.extension_server = ExtensionServer()
        self.extension_server.start()
        self.extension_server.set_blocked_sites(blocked_websites)
        self.extension_server.set_always_blocked_sites(adult_sites)
        self.extension_server.set_whitelisted_urls(self.config.whitelisted_urls)

        # Initialize punishment system for adult sites
        self._init_punishment_system()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self.main_window = MainWindow(
            root=self.root,
            on_start=self._on_start,
            on_pause=self._on_pause,
            on_stop=self._on_stop,
            on_settings=self._on_settings,
            on_blocklist=self._on_blocklist,
            on_usage_stats=self._on_usage_stats,
        )

        # Set initial timer display
        self.main_window.set_initial_time(self.config.work_minutes * 60)

        # Set initial cycle count display
        self._update_cycle_display()

        # Set initial sets display
        self.main_window.update_sets_progress(0, self.config.sets_per_session)

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

    def _init_desktop_stats(self) -> None:
        """Initialize the desktop stats widget."""
        self.desktop_stats = DesktopStatsWidget(
            get_stats_callback=self._get_stats_data,
            update_interval_ms=1000
        )
        self.desktop_stats.start()

    def _init_usage_tracking(self) -> None:
        """Initialize usage tracking for apps and websites."""
        import atexit

        # Load usage data
        self.usage_data = UsageData.load()

        # Initialize app tracker with AFK integration
        self.usage_tracker = UsageTracker(
            on_usage_tick=self._on_usage_tick,
            afk_check=self.afk_detector.is_afk,
        )
        self.usage_tracker.start()

        # Set up extension server callback for website tracking
        self.extension_server.set_usage_callback(self._on_website_usage)

        # Schedule periodic saves (every 60 seconds)
        self._schedule_usage_save()

        # Register atexit handler to save on unexpected exit
        atexit.register(self._save_usage_data_sync)

    def _on_usage_tick(self, name: str, category: str, seconds: int) -> None:
        """Handle usage tick from app tracker."""
        self.usage_data.record_usage(name, category, seconds)

    def _on_website_usage(self, category: str, name: str, seconds: int) -> None:
        """Handle website usage report from extension."""
        print(f"Website usage: {name} - {seconds}s")
        self.usage_data.record_usage(name, category, seconds)

    def _schedule_usage_save(self) -> None:
        """Schedule periodic usage data saves."""
        self._save_usage_data_sync()
        self.root.after(60000, self._schedule_usage_save)

    def _save_usage_data_sync(self) -> None:
        """Save usage data synchronously."""
        try:
            if hasattr(self, 'usage_data') and self.usage_data.is_dirty():
                self.usage_data.save()
                print("Usage data saved")
        except Exception as e:
            print(f"Error saving usage data: {e}")

    def _get_stats_data(self) -> StatsData:
        """Get current stats data for the desktop widget."""
        seconds_since_clean = self.internet_disabler.state.get_seconds_since_clean()

        top_apps = []
        top_websites = []
        if hasattr(self, 'usage_data'):
            top_apps = self.usage_data.get_top_items('app', 'today', limit=3)
            top_websites = self.usage_data.get_top_items('website', 'today', limit=3)

        return StatsData(
            hours_worked_today=(self.config.get_cycles_today() * self.config.work_minutes) / 60,
            hours_worked_total=(self.config.total_cycles * self.config.work_minutes) / 60,
            cycles_today=self.config.get_cycles_today(),
            cycles_total=self.config.total_cycles,
            seconds_since_adult_access=seconds_since_clean,
            work_minutes=self.config.work_minutes,
            session_history=self.config.get_session_history(7),
            percentage_change=self.config.get_percentage_change(),
            top_apps_today=top_apps,
            top_websites_today=top_websites,
        )

    def _init_punishment_system(self) -> None:
        """Initialize the adult site punishment system."""
        self.internet_disabler = InternetDisabler(
            max_strikes=self.config.max_adult_strikes,
            punishment_hours=self.config.punishment_hours
        )

        # Initialize clean_since_timestamp if this is first run
        self.internet_disabler.state.initialize_clean_since()

        # Set up extension server callbacks for punishment system
        self.extension_server.set_adult_strike_callback(self._on_adult_strike)
        self.extension_server.set_punishment_state_callback(self._get_punishment_state)

        # Check if we're currently in a punishment lock and notify user
        if self.internet_disabler.is_locked():
            remaining = self.internet_disabler.get_lock_time_remaining()
            minutes = remaining // 60
            print(f"Punishment lock active: {minutes} minutes remaining")

    def _init_nsfw_detection(self) -> None:
        """Initialize AI-powered NSFW detection (no DNS monitor on macOS)."""
        self.nsfw_cache = NSFWCache.load()

        self.nsfw_detector = NSFWDetector(
            api_key=self.config.openai_api_key,
            cache=self.nsfw_cache,
            on_nsfw_detected=self._on_nsfw_domain_detected,
        )

        # Wire up extension server callbacks
        self.extension_server.set_nsfw_check_callback(self._on_nsfw_check)
        self.extension_server.set_nsfw_cache_callback(self._get_nsfw_checked_domains)

        # Schedule periodic cache saves (every 60s)
        self._schedule_nsfw_cache_save()

        # Add NSFW domains from cache to always_blocked on startup
        cached_nsfw = self.nsfw_cache.get_all_nsfw_domains()
        if cached_nsfw:
            current = ExtensionRequestHandler.always_blocked_sites
            current.update(cached_nsfw)
            print(f"[NSFW] Loaded {len(cached_nsfw)} cached NSFW domains")

        # NOTE: DNS monitor is skipped on macOS - no easy equivalent to Get-DnsClientCache
        # NSFW detection relies entirely on the browser extension's content checking

    def _on_nsfw_check(self, data: dict) -> dict:
        """Handle NSFW content check request from extension."""
        domain = data.get('domain', '?')
        print(f"[NSFW] Check request received for: {domain}")

        if not self.config.ai_nsfw_detection_enabled:
            print(f"[NSFW] Feature disabled in settings")
            return {'is_nsfw': False, 'confidence': 0.0, 'cached': False, 'method': 'disabled'}

        if not self.config.openai_api_key:
            print(f"[NSFW] No OpenAI API key configured")
            return {'is_nsfw': False, 'confidence': 0.0, 'cached': False, 'method': 'no_api_key'}

        signals = PageSignals(
            url=data.get('url', ''),
            domain=data.get('domain', ''),
            title=data.get('title', ''),
            meta_description=data.get('meta_description', ''),
            body_text=data.get('body_text', ''),
        )
        result = self.nsfw_detector.check_content_sync(signals)
        print(f"[NSFW] Result for {domain}: {result}")
        return result

    def _get_nsfw_checked_domains(self) -> list:
        """Get all checked domain names for extension cache sync."""
        return [e.domain for e in self.nsfw_cache.get_all_entries()]

    def _on_nsfw_domain_detected(self, domain: str) -> None:
        """Handle newly detected NSFW domain - add to blocklists and fire strike."""
        print(f"[NSFW] AI detected NSFW domain: {domain}")

        # Add to always_blocked in extension server
        ExtensionRequestHandler.always_blocked_sites.add(domain)

        # Add to hosts file blocker if admin
        if self.has_admin and hasattr(self, 'website_blocker'):
            self.website_blocker.add_adult_site(domain)

        # Fire adult strike
        self.root.after(0, lambda: self._on_adult_strike())

    def _schedule_nsfw_cache_save(self) -> None:
        """Schedule periodic NSFW cache saves."""
        self._save_nsfw_cache_sync()
        self.root.after(60000, self._schedule_nsfw_cache_save)

    def _save_nsfw_cache_sync(self) -> None:
        """Save NSFW cache synchronously."""
        try:
            if hasattr(self, 'nsfw_cache') and self.nsfw_cache.is_dirty():
                self.nsfw_cache.save()
                print("[NSFW] Cache saved")
        except Exception as e:
            print(f"[NSFW] Error saving cache: {e}")

    def _on_adult_strike(self) -> dict:
        """Handle adult site visit attempt - called by extension server."""
        new_count, triggered = self.internet_disabler.add_strike()

        if triggered:
            self.root.after(0, self._show_punishment_notification)

        return self._get_punishment_state()

    def _get_punishment_state(self) -> dict:
        """Get current punishment state for extension."""
        return self.internet_disabler.get_status()

    def _show_punishment_notification(self) -> None:
        """Show notification that punishment has been activated."""
        self.main_window.show()
        messagebox.showerror(
            "Internet Disabled",
            f"You have exceeded the maximum number of adult site visit attempts.\n\n"
            f"Your internet has been DISABLED for {self.config.punishment_hours} hours.\n\n"
            "This cannot be bypassed. Use this time to reflect on your choices."
        )

    def _on_timer_tick(self, seconds_remaining: int) -> None:
        """Handle timer tick - update UI."""
        self.root.after(0, lambda: self.main_window.update_timer(seconds_remaining))

        minutes = seconds_remaining // 60
        secs = seconds_remaining % 60
        state = self.timer.state.upper()
        cycles_today = self.config.get_cycles_today()
        self.root.after(
            0,
            lambda s=state, m=minutes, sc=secs, c=cycles_today: self.tray_icon.update_tooltip(
                f"{s} - {m:02d}:{sc:02d} | Cycles: {c}"
            )
        )

    def _on_state_change(self, new_state: str) -> None:
        """Handle timer state change."""
        self.root.after(0, lambda: self.main_window.update_state(new_state))
        self.root.after(0, lambda: self.tray_icon.update_state(new_state))

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
            self.config.increment_cycle()
            self.root.after(0, self._update_cycle_display)

            self._sets_completed += 1
            self.root.after(0, self._update_sets_display)
            print(f"Set completed: {self._sets_completed}/{self.config.sets_per_session}")

            if self._sets_completed >= self.config.sets_per_session:
                self._session_active = False
                self.root.after(0, lambda: self._show_sets_complete_notification())
            else:
                remaining = self.config.sets_per_session - self._sets_completed
                self.root.after(0, lambda r=remaining: self._show_notification(
                    f"Work session complete! {r} set(s) remaining. Time for a break."
                ))
        elif completed_state == TimerState.BREAK:
            self.root.after(0, lambda: self._show_notification("Break is over! Ready to focus?"))

    def _update_cycle_display(self) -> None:
        """Update the cycle counter display in the UI."""
        today = self.config.get_cycles_today()
        total = self.config.total_cycles
        self.main_window.update_cycle_count(today, total)

    def _update_sets_display(self) -> None:
        """Update the sets progress display in the UI."""
        if self._session_active:
            self.main_window.update_sets_progress(
                self._sets_completed,
                self.config.sets_per_session
            )
        else:
            self.main_window.update_sets_progress(0, self.config.sets_per_session)

    def _show_sets_complete_notification(self) -> None:
        """Show notification when all sets are completed."""
        self.main_window.show()
        self.root.bell()
        messagebox.showinfo(
            "Session Complete!",
            f"Congratulations! You completed all {self.config.sets_per_session} sets!\n\n"
            "You are now free to close the app or start another session."
        )
        self._update_sets_display()

    def _show_notification(self, message: str) -> None:
        """Show a notification to the user."""
        self.main_window.show()
        self.root.bell()

    def _start_blocking(self) -> None:
        """Start blocking apps and websites."""
        if self._is_blocking:
            return
        self._is_blocking = True

        self.process_blocker.start()

        if self.has_admin:
            success, error = self.website_blocker.block()
            if not success:
                self.root.after(0, lambda: messagebox.showwarning(
                    "Website Blocking Failed",
                    f"Could not block websites:\n{error}\n\n"
                    "App blocking is still active.\n"
                    "Website blocking requires admin privileges."
                ))
            else:
                is_active, status = self.website_blocker.verify_blocking_active()
                if is_active:
                    print(f"Website blocking: {status}")

        self.extension_server.set_blocking_state(True)
        self.extension_server.reset_block_count()

        self.disable_guard.start_session()

    def _stop_blocking(self) -> None:
        """Stop blocking apps and websites."""
        if not self._is_blocking:
            return
        self._is_blocking = False

        self.process_blocker.stop()

        if self.has_admin:
            success, error = self.website_blocker.unblock()
            if not success:
                print(f"Warning: Could not unblock websites: {error}")

        self.extension_server.set_blocking_state(False)

    def _on_start(self) -> None:
        """Handle start/resume/skip-break button click."""
        if self.timer.state == TimerState.IDLE:
            if not self._session_active:
                self._session_active = True
                self._sets_completed = 0
                print(f"Session started: 0/{self.config.sets_per_session} sets")
            self.timer.start_work()
            self._update_sets_display()
        elif self.timer.state == TimerState.PAUSED:
            self.timer.resume()
        elif self.timer.state == TimerState.BREAK:
            print("Break skipped")
            self.timer.skip()

    def _on_pause(self) -> None:
        """Handle pause button click."""
        if self.timer.state in (TimerState.WORKING, TimerState.BREAK):
            self.timer.pause()

    def _on_stop(self) -> None:
        """Handle stop button click - requires disable guard."""
        self.root.after(0, self._handle_stop)

    def _handle_stop(self) -> None:
        """Handle stop on main thread."""
        if self.timer.state == TimerState.IDLE:
            return

        if self._session_active:
            remaining = self.config.sets_per_session - self._sets_completed
            result = messagebox.askyesno(
                "Session In Progress",
                f"You have {remaining} set(s) remaining!\n\n"
                f"Completed: {self._sets_completed}/{self.config.sets_per_session}\n\n"
                "Do you really want to stop? You'll need to complete a typing challenge.",
                icon='warning'
            )
            if result:
                self._show_disable_challenge()
            return

        if self.timer.state == TimerState.WORKING and self.disable_guard.is_session_active():
            self._show_disable_challenge()
        else:
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
            on_cancel=lambda: None,
            on_cooldown_disable=self._do_stop if cooldown_remaining == 0 else lambda: None,
        )

    def _do_stop(self) -> None:
        """Actually stop the timer and blocking."""
        self.timer.stop()
        self._stop_blocking()
        self.disable_guard.end_session()

        self._session_active = False
        self._sets_completed = 0
        self._update_sets_display()

        self.main_window.update_state(TimerState.IDLE)
        self.main_window.set_initial_time(self.config.work_minutes * 60)

    def _on_settings(self) -> None:
        """Handle settings button click."""
        self.root.after(0, self._handle_settings)

    def _handle_settings(self) -> None:
        """Handle settings on main thread."""
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

        self.timer.update_durations(
            work_seconds=config.work_minutes * 60,
            break_seconds=config.break_minutes * 60,
        )

        self.disable_guard.update_settings(
            cooldown_seconds=config.cooldown_minutes * 60,
            challenge_length=config.typing_challenge_length,
        )

        # Update NSFW detector API key (no DNS monitor on macOS)
        if hasattr(self, 'nsfw_detector'):
            self.nsfw_detector.update_api_key(config.openai_api_key)

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

        blocked_websites = config.get_all_blocked_websites()
        self.process_blocker.update_blocked_apps(config.get_all_blocked_apps())
        self.website_blocker.update_blocked_sites(blocked_websites)

        self.extension_server.set_blocked_sites(blocked_websites)

    def _on_usage_stats(self) -> None:
        """Handle usage stats button click."""
        UsageStatsWindow(
            parent=self.root,
            usage_data=self.usage_data,
        )

    def _on_tray_show(self) -> None:
        """Handle tray icon show click."""
        self.root.after(0, self.main_window.show)

    def _on_close(self) -> None:
        """Handle window close - minimize to tray or block during session."""
        if self._session_active:
            if self.tray_icon.is_available():
                self.main_window.hide()
            return

        if self.timer.state == TimerState.WORKING:
            if self.tray_icon.is_available():
                self.main_window.hide()
            return

        if self.tray_icon.is_available():
            self.main_window.hide()
        else:
            self._on_exit()

    def _on_exit_request(self) -> None:
        """Handle exit request - requires challenge during work session."""
        self.root.after(0, self._handle_exit_request)

    def _handle_exit_request(self) -> None:
        """Handle exit request on main thread."""
        if self._session_active:
            remaining = self.config.sets_per_session - self._sets_completed
            self.main_window.show()

            result = messagebox.askyesno(
                "Session In Progress",
                f"You have {remaining} set(s) remaining!\n\n"
                f"Completed: {self._sets_completed}/{self.config.sets_per_session}\n\n"
                "Do you really want to quit? You'll need to complete a typing challenge.",
                icon='warning'
            )

            if result:
                self._show_exit_challenge()
            return

        if self.timer.state == TimerState.WORKING and self.disable_guard.is_session_active():
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
            on_cancel=lambda: None,
            on_cooldown_disable=self._on_exit if cooldown_remaining == 0 else lambda: None,
        )

    def _on_exit(self) -> None:
        """Handle application exit."""
        self.timer.stop()
        self._stop_blocking()
        self.tray_icon.stop()
        self.extension_server.stop()
        self.desktop_stats.stop()

        # Stop usage tracking and save data
        self.usage_tracker.stop()
        self.usage_data.save()

        # Save NSFW cache (no DNS monitor to stop on macOS)
        if hasattr(self, 'nsfw_cache'):
            self.nsfw_cache.save()

        # Cleanup punishment system
        self.internet_disabler.cleanup()

        # Destroy window
        self.root.quit()
        self.root.destroy()

    def run(self) -> None:
        """Run the application main loop."""
        self.root.mainloop()
