"""
Main application orchestration for Productivity Timer (macOS).
"""

import os
import signal
import sys
import time
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from typing import Optional

from src.utils.constants import TimerState, UNPRODUCTIVE_ALERT_INTERVAL_MINUTES
from src.utils.admin import is_admin
from src.data.config import Config
from src.data.default_blocklists import get_adult_sites
from src.data.nsfw_cache import NSFWCache
from src.data.productivity_cache import ProductivityCache
from src.core.nsfw_detector import NSFWDetector, PageSignals
from src.core.productivity_monitor import ProductivityMonitor
from src.core.timer import PomodoroTimer
from src.core.process_blocker import ProcessBlocker
from src.core.website_blocker import WebsiteBlocker
from src.core.disable_guard import DisableGuard
from src.core.extension_server import ExtensionServer
from src.core.dns_proxy import DNSProxy
from src.core.afk_detector import AFKDetector
from src.data.punishment_state import PunishmentState
from src.core.usage_tracker import UsageTracker
from src.core.browser_tracker import BrowserTracker
from src.data.usage_data import UsageData
from src.ui.main_window import MainWindow
from src.ui.typing_challenge import TypingChallengeDialog
from src.ui.settings_window import SettingsWindow
from src.ui.blocklist_editor import BlocklistEditor
from src.ui.tray_icon import TrayIcon
from src.ui.desktop_stats import DesktopStatsWidget, StatsData
from src.ui.usage_stats_window import UsageStatsWindow
from src.ui.toast import TimerToastManager, Toast
from src.core.free_time_bucket import FreeTimeBucket
from src.ui.toast_notification import show_unproductive_alert
from src.data.session_state import SessionState


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
        self._tick_count = 0  # Throttle tooltip updates

        # Productivity alert tracking: "app:Discord" -> last alerted minute threshold
        self._alerted_thresholds: dict = {}
        self._alert_date: str = ""  # date string for daily reset

        # Initialize root window
        self.root = ttk.Window(themename=config.theme)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Block Cmd+Q — route through _on_exit_request instead of hard quit
        self.root.createcommand("::tk::mac::Quit", self._on_exit_request)

        # Catch SIGTERM and SIGINT — refuse to die during active sessions
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Initialize core components
        self._init_timer()
        self._init_blockers()
        self._init_dns_proxy()
        self._init_nsfw_detection()

        # Initialize UI
        self._init_ui()

        # Initialize tray icon
        self._init_tray()

        # Initialize usage tracking (must be before desktop stats)
        self._init_usage_tracking()

        # Initialize productivity monitoring (alerts for unproductive usage)
        self._init_productivity_monitor()

        # Initialize desktop stats widget
        self._init_desktop_stats()

        # Handle start minimized
        if config.start_minimized:
            self.root.withdraw()

        # Initialize free time bucket
        self.free_time_bucket = FreeTimeBucket.load(
            on_bucket_empty=lambda: self.root.after(0, self._on_bucket_empty),
            on_warning=lambda: self.root.after(0, self._on_bucket_warning),
            on_time_earned=lambda secs: self.root.after(0, lambda s=secs: self._on_time_earned(s)),
        )
        self._schedule_bucket_save()

        # If bucket feature is enabled and bucket is empty at startup, activate blocking
        if (self.config.free_time_bucket_enabled
                and not self.free_time_bucket.has_time()):
            self.root.after(500, self._start_blocking)

        # Set initial bucket display
        self.root.after(100, self._update_bucket_display)

        # Check for interrupted session and auto-resume
        self._check_interrupted_session()

    def _check_interrupted_session(self) -> None:
        """Resume an interrupted session if one exists (crash recovery)."""
        import time as _time
        state = SessionState.load()
        if state is None or not state.is_active:
            return

        # Calculate how much time passed while we were dead
        elapsed = _time.time() - state.timestamp
        adjusted_remaining = int(state.seconds_remaining - elapsed)

        if adjusted_remaining <= 0:
            # Session would have ended while we were dead — don't resume
            SessionState.clear()
            return

        print(f"Resuming interrupted session: {state.timer_state}, "
              f"{adjusted_remaining}s remaining, "
              f"sets {state.sets_completed}/{state.sets_total}")

        # Restore session state
        self._session_active = True
        self._sets_completed = state.sets_completed
        self.tray_icon.set_session_active(True)

        # Update UI
        self.main_window.update_sets_progress(
            state.sets_completed, state.sets_total
        )

        # Restore timer
        if state.timer_state == TimerState.WORKING:
            self.timer.restore_work(adjusted_remaining)
            self._start_blocking()
        elif state.timer_state == TimerState.BREAK:
            self.timer.restore_break(adjusted_remaining)

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

        self.toast_manager = TimerToastManager(self.root)

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
            blocked_websites, adult_sites, self.config.whitelisted_urls,
            has_admin=self.has_admin
        )

        # Start extension server for browser extension communication
        self.extension_server = ExtensionServer()
        self.extension_server.start()
        self.extension_server.set_tk_root(self.root)
        self.extension_server.set_blocked_sites(blocked_websites)
        self.extension_server.set_always_blocked_sites(adult_sites)
        self.extension_server.set_whitelisted_urls(self.config.whitelisted_urls)

        # Initialize punishment system for adult sites
        self._init_punishment_system()

    def _init_dns_proxy(self) -> None:
        """Initialize the local DNS filtering proxy for system-wide blocking."""
        self.dns_proxy = DNSProxy()

        # Share blocklists with the proxy
        blocked_websites = self.config.get_all_blocked_websites()
        adult_sites = get_adult_sites()
        self.dns_proxy.set_blocked_sites(blocked_websites)
        self.dns_proxy.set_always_blocked_sites(adult_sites)

        # Start the proxy (launches subprocess, configures DNS)
        if self.dns_proxy.start():
            print("[DNS] System-wide DNS filtering active")
        else:
            print("[DNS] DNS proxy failed to start — falling back to hosts file only")

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
            root=self.root,
        )

        if self.tray_icon.is_available():
            self.tray_icon.start()

    def _init_desktop_stats(self) -> None:
        """Initialize the desktop stats widget."""
        self.desktop_stats = DesktopStatsWidget(
            master=self.root,
            get_stats_callback=self._get_stats_data,
            update_interval_ms=1000
        )
        self.desktop_stats.start()

    def _init_usage_tracking(self) -> None:
        """Initialize usage tracking for apps and websites."""
        import atexit
        import os

        # Load usage data
        self.usage_data = UsageData.load()

        # Resolve blocked page path for native browser blocking
        blocked_html = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'browser_extension', 'blocked.html'
        )

        # Native browser tracker (fallback when extension is absent)
        self.browser_tracker = BrowserTracker(
            on_website_usage=self._on_website_usage,
            is_extension_connected=self.extension_server.is_extension_connected,
            is_blocking=lambda: self._is_blocking,
            get_blocked_sites=self.extension_server.get_blocked_sites,
            get_always_blocked_sites=self.extension_server.get_always_blocked_sites,
            blocked_page_path=blocked_html,
        )

        # Initialize app tracker with AFK integration (polls on main thread)
        self.usage_tracker = UsageTracker(
            on_usage_tick=self._on_usage_tick,
            afk_check=self.afk_detector.is_afk,
            root=self.root,
            browser_tracker=self.browser_tracker,
        )
        self.usage_tracker.start()

        # Set up extension server callback for website tracking
        self.extension_server.set_usage_callback(self._on_website_usage)

        # Register atexit handler to save on unexpected exit
        atexit.register(self._save_usage_data_sync)

    def _init_productivity_monitor(self) -> None:
        """Initialize productivity classification and alert system."""
        self.productivity_cache = ProductivityCache.load()

        blocked_apps = self.config.get_all_blocked_apps()
        blocked_websites = self.config.get_all_blocked_websites()

        self.productivity_monitor = ProductivityMonitor(
            blocked_apps=blocked_apps,
            blocked_websites=blocked_websites,
            api_key=self.config.openai_api_key,
            cache=self.productivity_cache,
        )

        # Initialize daily reset tracking
        from datetime import datetime
        self._alert_date = datetime.now().strftime('%Y-%m-%d')

    def _check_unproductive_alert(self, name: str, category: str) -> None:
        """Check if an unproductive app/website has crossed an alert threshold."""
        from datetime import datetime

        # Daily reset
        today = datetime.now().strftime('%Y-%m-%d')
        if today != self._alert_date:
            self._alerted_thresholds.clear()
            self._alert_date = today

        # Look up cumulative seconds today
        key = f"{category}:{name}"
        daily = self.usage_data.get_daily_stats()
        entry = daily.entries.get(key)
        if not entry:
            return

        total_seconds = entry.seconds
        total_minutes = total_seconds // 60
        interval = UNPRODUCTIVE_ALERT_INTERVAL_MINUTES

        # Current threshold: largest multiple of interval that's <= total_minutes
        if total_minutes < interval:
            return

        current_threshold = (total_minutes // interval) * interval
        last_alerted = self._alerted_thresholds.get(key, 0)

        if current_threshold > last_alerted:
            self._alerted_thresholds[key] = current_threshold
            self.root.after(0, lambda: show_unproductive_alert(
                self.root, name, category, total_seconds
            ))

    def _on_usage_tick(self, name: str, category: str, seconds: int) -> None:
        """Handle usage tick from app tracker."""
        self.usage_data.record_usage(name, category, seconds)

        # Drain free time bucket if using a blocked app during IDLE
        if (category == 'app'
                and self.config.free_time_bucket_enabled
                and self.timer.state == TimerState.IDLE
                and self.free_time_bucket.has_time()
                and name.lower() in (app.lower() for app in self.config.get_all_blocked_apps())):
            self.free_time_bucket.drain(seconds)

        # Productivity alert: skip browsers (extension handles tab URLs)
        if self.productivity_monitor.is_browser(name):
            return
        if self.productivity_monitor.classify_app(name):
            self._check_unproductive_alert(name, category)

    def _on_website_usage(self, category: str, name: str, seconds: int) -> None:
        """Handle website usage report from extension."""
        print(f"Website usage: {name} - {seconds}s")
        self.usage_data.record_usage(name, category, seconds)

        # Drain free time bucket if using a blocked website during IDLE
        if (self.config.free_time_bucket_enabled
                and self.timer.state == TimerState.IDLE
                and self.free_time_bucket.has_time()
                and name.lower() in (site.lower() for site in self.config.get_all_blocked_websites())):
            self.free_time_bucket.drain(seconds)

        if self.productivity_monitor.classify_website(name):
            self._check_unproductive_alert(name, category)

    def _schedule_usage_save(self) -> None:
        """Schedule periodic usage data saves."""
        self._save_usage_data_sync()
        self.root.after(60000, self._schedule_usage_save)

    def _schedule_bucket_save(self) -> None:
        """Schedule periodic free time bucket saves."""
        if self.free_time_bucket.is_dirty():
            self.free_time_bucket.save()
        self.root.after(60000, self._schedule_bucket_save)

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
        seconds_since_clean = self.punishment_state.get_seconds_since_clean()

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
        """Initialize the adult site strike tracking system."""
        self.punishment_state = PunishmentState.load()

        # Initialize clean_since_timestamp if this is first run
        self.punishment_state.initialize_clean_since()

        # Set up extension server callbacks for punishment system
        self.extension_server.set_adult_strike_callback(self._on_adult_strike)
        self.extension_server.set_punishment_state_callback(self._get_punishment_state)

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

        # Schedule periodic saves for all dirty data (every 60s)
        self._schedule_periodic_saves()

        # Add NSFW domains from cache to always_blocked on startup
        cached_nsfw = self.nsfw_cache.get_all_nsfw_domains()
        if cached_nsfw:
            self.extension_server.update_always_blocked_sites(cached_nsfw)
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
        self.extension_server.add_always_blocked_site(domain)

        # Add to hosts file blocker if admin
        if self.has_admin and hasattr(self, 'website_blocker'):
            self.website_blocker.add_adult_site(domain)

        # Add to DNS proxy blocklist
        if hasattr(self, 'dns_proxy') and self.dns_proxy.is_running():
            self.dns_proxy.add_always_blocked_site(domain)
            self.dns_proxy.flush_state()

        # Fire adult strike
        self.root.after(0, lambda: self._on_adult_strike())

    def _schedule_periodic_saves(self) -> None:
        """Single consolidated timer for all periodic saves (every 60s)."""
        self._save_usage_data_sync()
        try:
            if hasattr(self, 'nsfw_cache') and self.nsfw_cache.is_dirty():
                self.nsfw_cache.save()
        except Exception as e:
            print(f"[NSFW] Error saving cache: {e}")
        try:
            if hasattr(self, 'productivity_cache') and self.productivity_cache.is_dirty():
                self.productivity_cache.save()
        except Exception as e:
            print(f"[Productivity] Error saving cache: {e}")
        # Flush DNS proxy state if dirty
        try:
            if hasattr(self, 'dns_proxy') and self.dns_proxy.is_running():
                self.dns_proxy.flush_state()
        except Exception as e:
            print(f"[DNS] Error flushing state: {e}")
        self.root.after(60000, self._schedule_periodic_saves)

    def _save_session_state(self) -> None:
        """Persist current session state to disk for crash recovery."""
        if not self._session_active:
            return
        try:
            SessionState(
                is_active=self._session_active,
                timer_state=self.timer.state,
                seconds_remaining=self.timer.time_remaining,
                sets_completed=self._sets_completed,
                sets_total=self.config.sets_per_session,
                is_blocking=self._is_blocking,
                timestamp=0,  # set by save()
            ).save()
        except Exception as e:
            print(f"Error saving session state: {e}")

    def _on_adult_strike(self) -> dict:
        """Handle adult site visit attempt - called by extension server."""
        self.punishment_state.add_strike()
        return self._get_punishment_state()

    def _get_punishment_state(self) -> dict:
        """Get current punishment state for extension."""
        strikes_used = self.punishment_state.strike_count
        max_strikes = self.config.max_adult_strikes
        strikes_remaining = max(0, max_strikes - strikes_used + 1)
        return {
            'strikes_remaining': strikes_remaining,
            'is_locked': False,
            'lock_time_remaining': 0,
            'lock_end_timestamp': 0,
            'strike_count': strikes_used,
            'max_strikes': max_strikes,
        }

    def _on_timer_tick(self, seconds_remaining: int) -> None:
        """Handle timer tick - update UI."""
        self.root.after(0, lambda: self.main_window.update_timer(seconds_remaining))

        # Check for milestone toast notifications
        state = self.timer.state
        self.root.after(
            0,
            lambda r=seconds_remaining, s=state: self.toast_manager.check(r, s)
        )

        # Save session state every 10 ticks (~10s)
        self._tick_count += 1
        if self._tick_count % 10 == 0:
            self._save_session_state()

        # Update tray tooltip with timer and cycle count
        minutes = seconds_remaining // 60
        secs = seconds_remaining % 60
        state_upper = state.upper()
        cycles_today = self.config.get_cycles_today()
        # Build tooltip with optional free time info
        tooltip = f"{state_upper} - {minutes:02d}:{secs:02d} | Cycles: {cycles_today}"
        if self.config.free_time_bucket_enabled:
            bucket_text = self.free_time_bucket.format_balance(draining=False)
            tooltip += f" | Free: {bucket_text}"

        self.root.after(
            0,
            lambda t=tooltip: self.tray_icon.update_tooltip(t)
        )

        # Update bucket display
        if self.config.free_time_bucket_enabled:
            self.root.after(0, self._update_bucket_display)

    def _on_state_change(self, new_state: str) -> None:
        """Handle timer state change."""
        self.root.after(0, lambda: self.main_window.update_state(new_state))
        self.root.after(0, lambda: self.tray_icon.update_state(new_state))
        self._save_session_state()

        # Reset toast milestones and set duration for the new session
        self.toast_manager.reset()
        if new_state == TimerState.WORKING:
            self.toast_manager.set_total(self.timer.work_seconds)
        elif new_state == TimerState.BREAK:
            # Use actual remaining time (could be long break override)
            self.toast_manager.set_total(self.timer.time_remaining)

        # Start/stop blocking based on state
        if new_state == TimerState.WORKING:
            self._start_blocking()
        elif new_state == TimerState.BREAK:
            self._stop_blocking()
        elif new_state == TimerState.IDLE:
            # If bucket feature is enabled and bucket is empty, keep blocking
            if (self.config.free_time_bucket_enabled
                    and not self.free_time_bucket.has_time()):
                # Stay blocked — don't call _stop_blocking
                pass
            else:
                self._stop_blocking()
            self.disable_guard.end_session()

        # Update bucket display on state change
        self.root.after(0, self._update_bucket_display)

    def _on_session_complete(self, completed_state: str) -> None:
        """Handle session completion (work or break ended)."""
        if completed_state == TimerState.WORKING:
            self.config.increment_cycle()

            # Earn free time if bucket feature is enabled
            if self.config.free_time_bucket_enabled:
                earned = self.config.work_minutes * 60 * self.config.free_time_ratio
                self.free_time_bucket.add_time(earned)

            self.root.after(0, self._update_cycle_display)

            self._sets_completed += 1
            self.root.after(0, self._update_sets_display)
            print(f"Set completed: {self._sets_completed}/{self.config.sets_per_session}")

            if self._sets_completed >= self.config.sets_per_session:
                self._session_active = False
                # Trigger long break instead of regular break
                long_break_secs = self.config.long_break_minutes * 60
                self.timer.set_next_break_duration(long_break_secs)
                self.tray_icon.set_session_active(False)
                SessionState.clear()
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
            f"Enjoy your {self.config.long_break_minutes}-minute long break.\n"
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

        # Enable session blocking in DNS proxy
        if hasattr(self, 'dns_proxy') and self.dns_proxy.is_running():
            self.dns_proxy.set_session_blocking(True)
            self.dns_proxy.flush_state()

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

        # Disable session blocking in DNS proxy
        if hasattr(self, 'dns_proxy') and self.dns_proxy.is_running():
            self.dns_proxy.set_session_blocking(False)
            self.dns_proxy.flush_state()

    def _on_start(self) -> None:
        """Handle start/resume/skip-break button click."""
        if self.timer.state == TimerState.IDLE:
            if not self._session_active:
                self._session_active = True
                self._sets_completed = 0
                self.tray_icon.set_session_active(True)
                print(f"Session started: 0/{self.config.sets_per_session} sets")
            self.timer.start_work()
            self._update_sets_display()
            self._save_session_state()
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
        # Capture elapsed work time before stop() resets _time_remaining
        is_working = (self.timer.state == TimerState.WORKING
                      or (self.timer.state == TimerState.PAUSED
                          and self.timer.paused_from_state == TimerState.WORKING))
        if is_working and self.config.free_time_bucket_enabled:
            elapsed = self.timer.work_seconds - self.timer.time_remaining
            if elapsed > 0:
                earned = elapsed * self.config.free_time_ratio
                self.free_time_bucket.add_time(earned)

        self.timer.stop()
        self._stop_blocking()
        self.disable_guard.end_session()

        self._session_active = False
        SessionState.clear()
        self.tray_icon.set_session_active(False)
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

        # Ensure main window is visible (may be hidden when opened from tray)
        self.main_window.show()

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

        # Update productivity monitor API key
        if hasattr(self, 'productivity_monitor'):
            self.productivity_monitor.update_api_key(config.openai_api_key)

        self.main_window.set_initial_time(config.work_minutes * 60)

        # Re-evaluate bucket display and blocking state after settings change
        self._update_bucket_display()

        # Re-evaluate blocking state when bucket setting changes during IDLE
        if self.timer.state == TimerState.IDLE:
            if (config.free_time_bucket_enabled
                    and not self.free_time_bucket.has_time()):
                self._start_blocking()
            else:
                self._stop_blocking()

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

        # Update DNS proxy blocklists
        if hasattr(self, 'dns_proxy') and self.dns_proxy.is_running():
            self.dns_proxy.set_blocked_sites(blocked_websites)
            self.dns_proxy.set_always_blocked_sites(get_adult_sites())
            self.dns_proxy.flush_state()

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
            self._on_exit(write_sentinel=False)

    def _handle_signal(self, signum, frame) -> None:
        """Handle SIGTERM/SIGINT — always exit to not block system shutdown.

        The guard/launchd processes will respawn us after shutdown completes,
        so we don't lose session protection. Blocking SIGTERM prevents macOS
        from shutting down or logging out.
        """
        print(f"Signal {signum} caught — exiting (guards will respawn)")
        self._on_exit(write_sentinel=False)

    def _on_exit_request(self) -> None:
        """Handle exit request - requires challenge during work session."""
        self.root.after(0, self._handle_exit_request)

    def _handle_exit_request(self) -> None:
        """Handle exit request on main thread.

        The app always respawns via the guard processes.  Quitting just
        restarts it — the user can't escape.
        """
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
            # No session active — exit without clean sentinel so guards respawn us
            self._on_exit(write_sentinel=False)

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

    def _on_exit(self, write_sentinel: bool = True) -> None:
        """Handle application exit.

        Args:
            write_sentinel: If True, write the clean-exit file so guards
                            won't respawn.  Pass False to let guards restart
                            the app automatically.
        """
        from src.utils.constants import CLEAN_EXIT_FILE

        SessionState.clear()
        self.timer.stop()
        self._stop_blocking()
        self.tray_icon.stop()
        self.extension_server.stop()
        self.desktop_stats.stop()

        # Stop DNS proxy and restore DNS settings
        if hasattr(self, 'dns_proxy'):
            self.dns_proxy.stop()

        # Stop usage tracking and save data
        self.usage_tracker.stop()
        self.usage_data.save()

        # Save NSFW cache (no DNS monitor to stop on macOS)
        if hasattr(self, 'nsfw_cache'):
            self.nsfw_cache.save()

        # Save free time bucket
        self.free_time_bucket.save()

        # Save productivity cache
        if hasattr(self, 'productivity_cache'):
            self.productivity_cache.save()

        # Cleanup punishment system
        self.internet_disabler.cleanup()

        # Save punishment state
        self.punishment_state.save()

        if write_sentinel:
            # Write clean exit sentinel so guard/launchd won't respawn
            try:
                CLEAN_EXIT_FILE.parent.mkdir(parents=True, exist_ok=True)
                CLEAN_EXIT_FILE.write_text("clean")
            except Exception:
                pass

        # Destroy window and exit immediately.
        # Use os._exit() to avoid Python finalization crashing daemon threads
        # (Python 3.13 GIL error when daemon threads are in sleep/select during shutdown)
        self.root.quit()
        self.root.destroy()
        os._exit(0)

    def _update_bucket_display(self) -> None:
        """Update the free time bucket display in the main window."""
        if not self.config.free_time_bucket_enabled:
            self.main_window.update_free_time("", visible=False)
            return

        is_draining = (self.timer.state == TimerState.IDLE
                       and self.free_time_bucket.has_time())
        text = self.free_time_bucket.format_balance(draining=is_draining)
        self.main_window.update_free_time(text, visible=True)

    def _on_bucket_empty(self) -> None:
        """Handle bucket draining to zero — activate blocking during IDLE."""
        if self.timer.state == TimerState.IDLE:
            self._start_blocking()
            Toast(self.root, "Free time used up - blocked apps/sites are now blocked",
                  accent="#e94560")

    def _on_bucket_warning(self) -> None:
        """Handle bucket approaching zero — show warning toast."""
        if self.timer.state == TimerState.IDLE:
            Toast(self.root, "2 minutes of free time remaining",
                  accent="#f0ad4e")

    def _on_time_earned(self, seconds: float) -> None:
        """Handle time earned — show notification and update display."""
        minutes = int(seconds / 60)
        Toast(self.root, f"Earned {minutes} minutes of free time!",
              accent="#0f9b58")
        self._update_bucket_display()

    def run(self) -> None:
        """Run the application main loop."""
        self.root.mainloop()
