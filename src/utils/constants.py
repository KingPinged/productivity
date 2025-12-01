"""
Application-wide constants for Productivity Timer.
"""

from pathlib import Path

# App info
APP_NAME = "ProductivityTimer"
APP_VERSION = "1.0.0"

# Paths
APP_DATA_DIR = Path.home() / "AppData" / "Local" / APP_NAME
CONFIG_FILE = APP_DATA_DIR / "config.json"
HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")

# Timer defaults (52/17 method)
DEFAULT_WORK_MINUTES = 52
DEFAULT_BREAK_MINUTES = 17

# Disable guard settings
DEFAULT_COOLDOWN_MINUTES = 10
DEFAULT_TYPING_CHALLENGE_LENGTH = 1000

# Process blocker settings
PROCESS_CHECK_INTERVAL = 2  # seconds

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
