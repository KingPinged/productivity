"""
Configuration management for Productivity Timer.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import List, Dict

from src.utils.constants import (
    APP_DATA_DIR,
    CONFIG_FILE,
    DEFAULT_WORK_MINUTES,
    DEFAULT_BREAK_MINUTES,
    DEFAULT_SETS_PER_SESSION,
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_TYPING_CHALLENGE_LENGTH,
    DEFAULT_AFK_THRESHOLD_MINUTES,
    DEFAULT_MAX_ADULT_STRIKES,
    DEFAULT_PUNISHMENT_HOURS,
    DEFAULT_THEME,
)


@dataclass
class Config:
    """Application configuration."""

    # Timer settings
    work_minutes: int = DEFAULT_WORK_MINUTES
    break_minutes: int = DEFAULT_BREAK_MINUTES
    sets_per_session: int = DEFAULT_SETS_PER_SESSION  # Work sessions to complete before app can close

    # Blocking settings - enabled categories
    enabled_app_categories: List[str] = field(default_factory=lambda: ["games", "social_media"])
    enabled_website_categories: List[str] = field(default_factory=lambda: ["social_media", "video_streaming"])

    # Custom blocked items (user-added)
    custom_blocked_apps: List[str] = field(default_factory=list)
    custom_blocked_websites: List[str] = field(default_factory=list)

    # Whitelisted URLs (allowed even if domain is blocked)
    whitelisted_urls: List[str] = field(default_factory=lambda: [
        "https://www.twitch.tv/caseoh_",
        "https://www.youtube.com/watch?v=jfKfPfyJRdk",
    ])

    # Disable guard settings
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES
    typing_challenge_length: int = DEFAULT_TYPING_CHALLENGE_LENGTH

    # AFK detection settings
    afk_threshold_minutes: int = DEFAULT_AFK_THRESHOLD_MINUTES  # Pause after X min of inactivity

    # Adult site punishment settings
    max_adult_strikes: int = DEFAULT_MAX_ADULT_STRIKES  # Strikes before internet disabled
    punishment_hours: int = DEFAULT_PUNISHMENT_HOURS  # Hours of internet lockout

    # System settings
    auto_start_windows: bool = True
    start_minimized: bool = False

    # AI NSFW detection settings
    ai_nsfw_detection_enabled: bool = True
    openai_api_key: str = ""

    # UI settings
    theme: str = DEFAULT_THEME

    # Session cycle tracking
    total_cycles: int = 0  # Lifetime total of completed work sessions
    cycles_today: int = 0  # Work sessions completed today
    last_cycle_date: str = ""  # Date string (YYYY-MM-DD) to detect day change

    # Session history for weekly comparison (date -> cycles count)
    # Stores last 7 days of session data
    session_history: Dict[str, int] = field(default_factory=dict)

    def increment_cycle(self) -> int:
        """
        Increment the cycle counter when a work session completes.
        Resets daily counter if it's a new day.

        Returns:
            The new total cycle count
        """
        today = date.today().isoformat()

        # Check if it's a new day - reset daily counter
        if self.last_cycle_date != today:
            self.cycles_today = 0
            self.last_cycle_date = today

        # Increment counters
        self.total_cycles += 1
        self.cycles_today += 1

        # Update session history for today
        self.session_history[today] = self.cycles_today

        # Cleanup old history (keep only last 14 days for safety)
        self._cleanup_session_history()

        # Auto-save
        self.save()

        return self.total_cycles

    def _cleanup_session_history(self) -> None:
        """Remove session history older than 14 days."""
        cutoff_date = (date.today() - timedelta(days=14)).isoformat()
        self.session_history = {
            d: c for d, c in self.session_history.items() if d >= cutoff_date
        }

    def get_session_history(self, days: int = 7) -> List[Dict]:
        """
        Get session history for the last N days.

        Returns:
            List of dicts with 'date', 'cycles', 'minutes' keys, ordered oldest to newest
        """
        result = []
        today = date.today()

        for i in range(days - 1, -1, -1):  # Start from oldest
            day = (today - timedelta(days=i)).isoformat()
            cycles = self.session_history.get(day, 0)
            result.append({
                'date': day,
                'cycles': cycles,
                'minutes': cycles * self.work_minutes
            })

        return result

    def get_percentage_change(self) -> tuple[float, bool]:
        """
        Calculate percentage change in sessions from yesterday to today.

        Returns:
            Tuple of (percentage_change, is_increase)
            percentage_change is absolute value, is_increase indicates direction
        """
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        today_cycles = self.session_history.get(today, self.get_cycles_today())
        yesterday_cycles = self.session_history.get(yesterday, 0)

        if yesterday_cycles == 0:
            if today_cycles > 0:
                return 100.0, True  # 100% increase from nothing
            return 0.0, True  # No change

        change = ((today_cycles - yesterday_cycles) / yesterday_cycles) * 100
        return abs(change), change >= 0

    def get_cycles_today(self) -> int:
        """Get the number of cycles completed today, resetting if new day."""
        today = date.today().isoformat()
        if self.last_cycle_date != today:
            return 0
        return self.cycles_today

    def reset_cycles(self) -> None:
        """Reset all cycle counters."""
        self.total_cycles = 0
        self.cycles_today = 0
        self.last_cycle_date = ""
        self.save()

    def save(self) -> None:
        """Save configuration to file."""
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> 'Config':
        """Load configuration from file, or create default if not exists."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                return cls(**data)
            except (json.JSONDecodeError, TypeError):
                # Invalid config, return default
                return cls()
        return cls()

    def get_all_blocked_apps(self) -> set[str]:
        """Get all blocked app process names."""
        from src.data.default_blocklists import get_all_blocked_apps

        apps = get_all_blocked_apps(self.enabled_app_categories)
        apps.update(app.lower() for app in self.custom_blocked_apps)
        return apps

    def get_all_blocked_websites(self) -> set[str]:
        """Get all blocked website domains."""
        from src.data.default_blocklists import get_all_blocked_websites

        sites = get_all_blocked_websites(self.enabled_website_categories)
        sites.update(self.custom_blocked_websites)
        return sites
