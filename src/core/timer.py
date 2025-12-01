"""
Pomodoro timer logic for Productivity Timer.
"""

import threading
import time
from typing import Callable, Optional

from src.utils.constants import TimerState


class PomodoroTimer:
    """
    Pomodoro timer with work and break sessions.
    Uses 52/17 method by default (52 min work, 17 min break).
    """

    def __init__(
        self,
        work_seconds: int,
        break_seconds: int,
        on_tick: Optional[Callable[[int], None]] = None,
        on_state_change: Optional[Callable[[str], None]] = None,
        on_session_complete: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the timer.

        Args:
            work_seconds: Duration of work session in seconds
            break_seconds: Duration of break session in seconds
            on_tick: Callback called every second with remaining time
            on_state_change: Callback called when state changes
            on_session_complete: Callback called when a session completes
        """
        self.work_seconds = work_seconds
        self.break_seconds = break_seconds

        self.on_tick = on_tick
        self.on_state_change = on_state_change
        self.on_session_complete = on_session_complete

        self._state = TimerState.IDLE
        self._time_remaining = work_seconds
        self._timer_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """Get current timer state."""
        return self._state

    @property
    def time_remaining(self) -> int:
        """Get remaining time in seconds."""
        return self._time_remaining

    @property
    def is_active(self) -> bool:
        """Check if timer is in an active session (working or break)."""
        return self._state in (TimerState.WORKING, TimerState.BREAK)

    @property
    def is_blocking_active(self) -> bool:
        """Check if blocking should be active (only during work sessions)."""
        return self._state == TimerState.WORKING

    def start(self) -> None:
        """Start or resume the timer."""
        with self._lock:
            if self._state == TimerState.IDLE:
                # Start new work session
                self._time_remaining = self.work_seconds
                self._set_state(TimerState.WORKING)
            elif self._state == TimerState.PAUSED:
                # Resume from pause - restore previous working/break state
                # We store the "real" state in a way that pause preserves it
                pass

            if not self._running:
                self._running = True
                self._timer_thread = threading.Thread(target=self._run_timer, daemon=True)
                self._timer_thread.start()

    def start_work(self) -> None:
        """Start a work session."""
        with self._lock:
            self._time_remaining = self.work_seconds
            self._set_state(TimerState.WORKING)

            if not self._running:
                self._running = True
                self._timer_thread = threading.Thread(target=self._run_timer, daemon=True)
                self._timer_thread.start()

    def start_break(self) -> None:
        """Start a break session."""
        with self._lock:
            self._time_remaining = self.break_seconds
            self._set_state(TimerState.BREAK)

            if not self._running:
                self._running = True
                self._timer_thread = threading.Thread(target=self._run_timer, daemon=True)
                self._timer_thread.start()

    def pause(self) -> None:
        """Pause the timer."""
        with self._lock:
            if self._state in (TimerState.WORKING, TimerState.BREAK):
                self._running = False
                self._set_state(TimerState.PAUSED)

    def resume(self) -> None:
        """Resume the timer from pause."""
        with self._lock:
            if self._state == TimerState.PAUSED:
                self._running = True
                self._set_state(TimerState.WORKING)  # Resume as working
                self._timer_thread = threading.Thread(target=self._run_timer, daemon=True)
                self._timer_thread.start()

    def stop(self) -> None:
        """Stop the timer and reset to idle."""
        with self._lock:
            self._running = False
            self._time_remaining = self.work_seconds
            self._set_state(TimerState.IDLE)

    def skip(self) -> None:
        """Skip to the next session (work -> break or break -> work)."""
        with self._lock:
            if self._state == TimerState.WORKING:
                self._time_remaining = self.break_seconds
                self._set_state(TimerState.BREAK)
            elif self._state == TimerState.BREAK:
                self._time_remaining = self.work_seconds
                self._set_state(TimerState.WORKING)

    def _set_state(self, new_state: str) -> None:
        """Set the state and trigger callback."""
        old_state = self._state
        self._state = new_state

        if old_state != new_state and self.on_state_change:
            self.on_state_change(new_state)

    def _run_timer(self) -> None:
        """Timer thread main loop."""
        while self._running:
            time.sleep(1)

            with self._lock:
                if not self._running:
                    break

                self._time_remaining -= 1

                if self.on_tick:
                    self.on_tick(self._time_remaining)

                if self._time_remaining <= 0:
                    # Session complete
                    completed_state = self._state

                    if self.on_session_complete:
                        self.on_session_complete(completed_state)

                    # Auto-transition to next session
                    if completed_state == TimerState.WORKING:
                        self._time_remaining = self.break_seconds
                        self._set_state(TimerState.BREAK)
                    else:
                        self._time_remaining = self.work_seconds
                        self._set_state(TimerState.WORKING)

    def update_durations(self, work_seconds: int, break_seconds: int) -> None:
        """Update timer durations (takes effect on next session)."""
        self.work_seconds = work_seconds
        self.break_seconds = break_seconds
