"""
Application-wide constants for Productivity Timer (macOS).
"""

from pathlib import Path

# App info
APP_NAME = "ProductivityTimer"
APP_VERSION = "1.0.0"

# Paths
APP_DATA_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
CONFIG_FILE = APP_DATA_DIR / "config.json"
HOSTS_PATH = Path("/etc/hosts")

# Timer defaults (52/17 method)
DEFAULT_WORK_MINUTES = 52
DEFAULT_BREAK_MINUTES = 17
DEFAULT_SETS_PER_SESSION = 3  # Number of work sessions before user can close app

# Disable guard settings
DEFAULT_COOLDOWN_MINUTES = 10
DEFAULT_TYPING_CHALLENGE_LENGTH = 1000

# AFK detection settings
DEFAULT_AFK_THRESHOLD_MINUTES = 10  # Pause timer after 10 minutes of inactivity

# Long break settings
DEFAULT_LONG_BREAK_MINUTES = 30

# Free time bucket settings
FREE_TIME_WARNING_SECONDS = 120
DEFAULT_FREE_TIME_RATIO = 2.0

# Adult site punishment settings
DEFAULT_MAX_ADULT_STRIKES = 2  # 3rd attempt triggers punishment
DEFAULT_PUNISHMENT_HOURS = 2  # Lock duration in hours
PUNISHMENT_STATE_FILE = APP_DATA_DIR / "punishment_state.json"
PUNISHMENT_ENFORCEMENT_INTERVAL = 60  # Re-check adapters every 60 seconds

# Usage tracking settings
USAGE_DATA_FILE = APP_DATA_DIR / "usage_data.json"
NSFW_CACHE_FILE = APP_DATA_DIR / "nsfw_cache.json"
FREE_TIME_BUCKET_FILE = APP_DATA_DIR / "free_time_bucket.json"
PRODUCTIVITY_CACHE_FILE = APP_DATA_DIR / "productivity_cache.json"
SESSION_STATE_FILE = APP_DATA_DIR / "session_state.json"
CLEAN_EXIT_FILE = APP_DATA_DIR / "clean_exit"
USAGE_TRACKING_INTERVAL = 5  # seconds between tracking checks

# Process blocker settings
PROCESS_CHECK_INTERVAL = 5  # seconds

# Productivity monitoring
UNPRODUCTIVE_ALERT_INTERVAL_MINUTES = 30

# Hosts file markers
HOSTS_MARKER_START = "# === PRODUCTIVITY TIMER BLOCK START ==="
HOSTS_MARKER_END = "# === PRODUCTIVITY TIMER BLOCK END ==="

# Theme
DEFAULT_THEME = "darkly"

# Timer states
class TimerState:
    IDLE = "idle"
    WORKING = "working"
    BREAK = "break"
    PAUSED = "paused"
