"""
Persistent storage for adult site punishment state.
Stored separately from main config to prevent tampering.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import List

from src.utils.constants import APP_DATA_DIR, PUNISHMENT_STATE_FILE


@dataclass
class PunishmentState:
    """Tracks adult site punishment state."""

    # Strike counter - resets after punishment ends
    strike_count: int = 0

    # Lock state
    is_locked: bool = False
    lock_end_timestamp: float = 0.0  # Unix timestamp when lock ends

    # Track which adapters were disabled so we can re-enable them
    disabled_adapters: List[str] = field(default_factory=list)

    # Track last adult site access attempt (for stats display)
    last_strike_timestamp: float = 0.0  # Unix timestamp of last strike

    # Track when the user started being "clean" (no adult site visits)
    # Set on first run, reset whenever a strike occurs
    clean_since_timestamp: float = 0.0

    def save(self) -> None:
        """Save punishment state to file."""
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(PUNISHMENT_STATE_FILE, 'w') as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> 'PunishmentState':
        """Load punishment state from file, or create default if not exists."""
        if PUNISHMENT_STATE_FILE.exists():
            try:
                with open(PUNISHMENT_STATE_FILE, 'r') as f:
                    data = json.load(f)
                return cls(**data)
            except (json.JSONDecodeError, TypeError, KeyError):
                # Invalid state file, return default
                return cls()
        return cls()

    def reset(self) -> None:
        """Reset all state (called after punishment ends)."""
        self.strike_count = 0
        self.is_locked = False
        self.lock_end_timestamp = 0.0
        self.disabled_adapters = []
        self.save()

    def add_strike(self) -> int:
        """Add a strike and save. Returns new strike count."""
        import time
        self.strike_count += 1
        self.last_strike_timestamp = time.time()
        # Reset clean timer - user is no longer clean
        self.clean_since_timestamp = time.time()
        self.save()
        return self.strike_count

    def initialize_clean_since(self) -> None:
        """Initialize clean_since_timestamp if not set (first run)."""
        import time
        if self.clean_since_timestamp == 0.0:
            self.clean_since_timestamp = time.time()
            self.save()

    def get_seconds_since_clean(self) -> int:
        """Get seconds since the user has been clean."""
        import time
        if self.clean_since_timestamp == 0.0:
            return 0
        return int(time.time() - self.clean_since_timestamp)

    def start_lock(self, end_timestamp: float, adapters: List[str]) -> None:
        """Start the punishment lock."""
        self.is_locked = True
        self.lock_end_timestamp = end_timestamp
        self.disabled_adapters = adapters
        self.save()

    def end_lock(self) -> None:
        """End the punishment lock and reset strikes."""
        self.reset()
