"""
Persistent free time bucket that tracks earned leisure time.
Users earn free time by completing pomodoro work sessions.
Time drains only when actively using blocklisted apps/websites during IDLE.
"""

import json
import threading
from typing import Callable, Optional

from src.utils.constants import FREE_TIME_BUCKET_FILE, APP_DATA_DIR, FREE_TIME_WARNING_SECONDS


class FreeTimeBucket:
    """
    Thread-safe persistent bucket for free time balance.
    Follows the same pattern as NSFWCache and UsageData.
    """

    def __init__(self, on_bucket_empty: Optional[Callable] = None,
                 on_warning: Optional[Callable] = None,
                 on_time_earned: Optional[Callable[[float], None]] = None):
        self._lock = threading.Lock()
        self.balance_seconds: float = 0.0
        self.total_earned_seconds: float = 0.0
        self.total_used_seconds: float = 0.0
        self.is_draining: bool = False
        self._dirty: bool = False
        self._warning_shown: bool = False  # one warning per drain-to-zero cycle

        # Callbacks
        self._on_bucket_empty = on_bucket_empty
        self._on_warning = on_warning
        self._on_time_earned = on_time_earned

    def has_time(self) -> bool:
        """Check if bucket has any free time remaining."""
        with self._lock:
            return self.balance_seconds > 0

    def get_balance(self) -> float:
        """Get current balance in seconds."""
        with self._lock:
            return self.balance_seconds

    def add_time(self, seconds: float) -> None:
        """Add earned free time to the bucket."""
        if seconds <= 0:
            return
        with self._lock:
            self.balance_seconds += seconds
            self.total_earned_seconds += seconds
            self._dirty = True
            # Reset warning flag when balance goes above threshold
            if self.balance_seconds > FREE_TIME_WARNING_SECONDS:
                self._warning_shown = False
        if self._on_time_earned:
            self._on_time_earned(seconds)

    def drain(self, seconds: float) -> None:
        """
        Drain free time from the bucket.
        Triggers warning callback at threshold and empty callback at zero.
        """
        if seconds <= 0:
            return

        trigger_warning = False
        trigger_empty = False

        with self._lock:
            if self.balance_seconds <= 0:
                return

            actual_drained = min(seconds, self.balance_seconds)
            self.balance_seconds = max(0.0, self.balance_seconds - seconds)
            self.total_used_seconds += actual_drained
            self._dirty = True

            # Check warning threshold
            if (self.balance_seconds <= FREE_TIME_WARNING_SECONDS
                    and self.balance_seconds > 0
                    and not self._warning_shown):
                self._warning_shown = True
                trigger_warning = True

            # Check empty
            if self.balance_seconds <= 0:
                self.balance_seconds = 0.0
                self.is_draining = False
                trigger_empty = True

        # Fire callbacks outside the lock to avoid deadlocks
        if trigger_warning and self._on_warning:
            self._on_warning()
        if trigger_empty and self._on_bucket_empty:
            self._on_bucket_empty()

    def set_draining(self, draining: bool) -> None:
        """Set whether the bucket is actively draining."""
        with self._lock:
            self.is_draining = draining

    def is_dirty(self) -> bool:
        """Check if bucket has unsaved changes."""
        return self._dirty

    def save(self) -> None:
        """Save bucket state to disk."""
        with self._lock:
            if not self._dirty:
                return

            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

            data = {
                "balance_seconds": self.balance_seconds,
                "total_earned_seconds": self.total_earned_seconds,
                "total_used_seconds": self.total_used_seconds,
            }

            try:
                with open(FREE_TIME_BUCKET_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                self._dirty = False
            except Exception as e:
                print(f"Error saving free time bucket: {e}")

    @classmethod
    def load(cls, on_bucket_empty: Optional[Callable] = None,
             on_warning: Optional[Callable] = None,
             on_time_earned: Optional[Callable[[float], None]] = None) -> 'FreeTimeBucket':
        """Load bucket state from disk. Falls back to zero on corruption."""
        instance = cls(on_bucket_empty=on_bucket_empty,
                       on_warning=on_warning,
                       on_time_earned=on_time_earned)

        if not FREE_TIME_BUCKET_FILE.exists():
            return instance

        try:
            with open(FREE_TIME_BUCKET_FILE, 'r') as f:
                data = json.load(f)

            instance.balance_seconds = max(0.0, float(data.get("balance_seconds", 0.0)))
            instance.total_earned_seconds = max(0.0, float(data.get("total_earned_seconds", 0.0)))
            instance.total_used_seconds = max(0.0, float(data.get("total_used_seconds", 0.0)))

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"Error loading free time bucket (corrupted file, resetting): {e}")
        except Exception as e:
            print(f"Error loading free time bucket: {e}")

        return instance

    def format_balance(self, draining: bool = False) -> str:
        """Format balance for display. HH:MM:SS when draining, Xh Ym when static."""
        with self._lock:
            total_seconds = int(self.balance_seconds)

        if total_seconds <= 0:
            return "0m" if not draining else "00:00:00"

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if draining:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            if hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
