"""
Process blocker for killing distracting applications.
"""

import threading
import time
from typing import Set, Optional

import psutil

from src.utils.constants import PROCESS_CHECK_INTERVAL


class ProcessBlocker:
    """
    Monitors running processes and kills blocked applications.
    """

    def __init__(self, blocked_apps: Set[str]):
        """
        Initialize the process blocker.

        Args:
            blocked_apps: Set of process names to block (lowercase)
        """
        self.blocked_apps = {app.lower() for app in blocked_apps}
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._kill_count = 0

    def start(self) -> None:
        """Start monitoring and killing blocked processes."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._kill_count = 0
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()

    def stop(self) -> None:
        """Stop monitoring processes."""
        with self._lock:
            self._running = False

    def update_blocked_apps(self, blocked_apps: Set[str]) -> None:
        """Update the set of blocked applications."""
        with self._lock:
            self.blocked_apps = {app.lower() for app in blocked_apps}

    @property
    def kill_count(self) -> int:
        """Get the number of processes killed in this session."""
        return self._kill_count

    def _monitor_loop(self) -> None:
        """Main monitoring loop - runs in background thread."""
        while self._running:
            self._kill_blocked_processes()
            time.sleep(PROCESS_CHECK_INTERVAL)

    def _kill_blocked_processes(self) -> None:
        """Find and kill all blocked processes."""
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                proc_name = proc.info['name']
                if proc_name and proc_name.lower() in self.blocked_apps:
                    self._kill_process(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # Process already gone or we don't have access
                pass

    def _kill_process(self, proc: psutil.Process) -> None:
        """Kill a single process, trying graceful termination first."""
        try:
            proc.terminate()  # Graceful termination (SIGTERM)
            try:
                proc.wait(timeout=3)  # Wait up to 3 seconds
                self._kill_count += 1
            except psutil.TimeoutExpired:
                # Process didn't terminate gracefully, force kill
                proc.kill()  # Force kill (SIGKILL)
                self._kill_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process already gone or we don't have access
            pass

    def is_running(self) -> bool:
        """Check if the blocker is currently running."""
        return self._running
