"""
Disable guard - prevents easy disabling of the blocker.
User must either wait for cooldown OR type a long random string.
"""

import random
import string
import time
from typing import Optional, Tuple


class DisableGuard:
    """
    Guards against impulsive disabling of the blocker.
    Two ways to disable:
    1. Wait for cooldown period
    2. Type a long random string correctly
    """

    def __init__(self, cooldown_seconds: int = 600, challenge_length: int = 1000):
        """
        Initialize the disable guard.

        Args:
            cooldown_seconds: How long to wait before allowing easy disable (default 10 min)
            challenge_length: Number of characters in typing challenge (default 1000)
        """
        self.cooldown_seconds = cooldown_seconds
        self.challenge_length = challenge_length

        self._session_start_time: Optional[float] = None
        self._challenge_text: Optional[str] = None
        self._is_session_active = False

    def start_session(self) -> None:
        """Start a new blocking session - resets cooldown timer."""
        self._session_start_time = time.time()
        self._challenge_text = None
        self._is_session_active = True

    def end_session(self) -> None:
        """End the current session."""
        self._session_start_time = None
        self._challenge_text = None
        self._is_session_active = False

    def is_session_active(self) -> bool:
        """Check if a session is currently active."""
        return self._is_session_active

    def can_quick_disable(self) -> bool:
        """
        Check if cooldown has elapsed, allowing easy disable.

        Returns:
            True if cooldown period has passed
        """
        if self._session_start_time is None:
            return True

        elapsed = time.time() - self._session_start_time
        return elapsed >= self.cooldown_seconds

    def get_cooldown_remaining(self) -> int:
        """
        Get seconds remaining in cooldown.

        Returns:
            Seconds remaining (0 if cooldown complete)
        """
        if self._session_start_time is None:
            return 0

        elapsed = time.time() - self._session_start_time
        remaining = self.cooldown_seconds - elapsed
        return max(0, int(remaining))

    def generate_challenge_text(self) -> str:
        """
        Generate random text for typing challenge.
        Uses mix of letters and digits for difficulty.

        Returns:
            Random string of challenge_length characters
        """
        # Use a mix that's hard to type quickly
        chars = string.ascii_letters + string.digits
        self._challenge_text = ''.join(random.choices(chars, k=self.challenge_length))
        return self._challenge_text

    def get_challenge_text(self) -> Optional[str]:
        """Get the current challenge text, if generated."""
        return self._challenge_text

    def validate_typing(self, typed_text: str) -> Tuple[bool, int, int]:
        """
        Validate typed text against challenge.
        Validates character-by-character - first mistake stops progress.

        Args:
            typed_text: What the user has typed so far

        Returns:
            Tuple of (is_complete, correct_count, total_required)
        """
        if self._challenge_text is None:
            return False, 0, self.challenge_length

        correct = 0
        for i, char in enumerate(typed_text):
            if i < len(self._challenge_text) and char == self._challenge_text[i]:
                correct += 1
            else:
                break  # Stop at first mistake

        is_complete = correct >= self.challenge_length
        return is_complete, correct, self.challenge_length

    def get_visible_challenge_portion(self, typed_count: int, window_size: int = 50) -> str:
        """
        Get a portion of the challenge text visible to user.
        Shows upcoming characters to type.

        Args:
            typed_count: Number of characters already typed correctly
            window_size: How many characters to show

        Returns:
            Portion of challenge text to display
        """
        if self._challenge_text is None:
            return ""

        start = typed_count
        end = min(start + window_size, len(self._challenge_text))
        return self._challenge_text[start:end]

    def update_settings(self, cooldown_seconds: int, challenge_length: int) -> None:
        """Update guard settings (takes effect on next session)."""
        self.cooldown_seconds = cooldown_seconds
        self.challenge_length = challenge_length
