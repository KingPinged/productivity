"""
Configuration management for Productivity Timer.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import List

from src.utils.constants import (
    APP_DATA_DIR,
    CONFIG_FILE,
    DEFAULT_WORK_MINUTES,
    DEFAULT_BREAK_MINUTES,
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_TYPING_CHALLENGE_LENGTH,
    DEFAULT_THEME,
)


@dataclass
class Config:
    """Application configuration."""

    # Timer settings
    work_minutes: int = DEFAULT_WORK_MINUTES
    break_minutes: int = DEFAULT_BREAK_MINUTES

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

    # System settings
    auto_start_windows: bool = True
    start_minimized: bool = False

    # UI settings
    theme: str = DEFAULT_THEME

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
