"""
Session state persistence for auto-resume after force-kill.
"""

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from src.utils.constants import SESSION_STATE_FILE

# Sessions older than 24 hours are considered stale
MAX_AGE_SECONDS = 24 * 60 * 60


@dataclass
class SessionState:
    is_active: bool
    timer_state: str  # "working" or "break"
    seconds_remaining: int
    sets_completed: int
    sets_total: int
    is_blocking: bool
    timestamp: float  # time.time() when saved

    def save(self) -> None:
        """Write session state to disk."""
        self.timestamp = time.time()
        SESSION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_STATE_FILE.write_text(json.dumps(asdict(self)))

    @staticmethod
    def load() -> Optional['SessionState']:
        """Load session state from disk, returning None if missing or stale."""
        try:
            if not SESSION_STATE_FILE.exists():
                return None
            data = json.loads(SESSION_STATE_FILE.read_text())
            state = SessionState(**data)
            if time.time() - state.timestamp > MAX_AGE_SECONDS:
                SessionState.clear()
                return None
            return state
        except Exception:
            return None

    @staticmethod
    def clear() -> None:
        """Delete the session state file."""
        try:
            SESSION_STATE_FILE.unlink(missing_ok=True)
        except Exception:
            pass
