"""
Process guard - monitors and respawns the app if killed (macOS).
Runs as a separate process to make the app harder to terminate.
"""

import subprocess
import sys
import os
import time
import psutil
import threading
from pathlib import Path


def is_process_running(process_name: str) -> bool:
    """Check if a process with given name is running."""
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def get_process_by_name(process_name: str) -> psutil.Process:
    """Get process by name."""
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def set_process_priority_low():
    """Set this process to low priority to stay unobtrusive."""
    try:
        os.nice(19)
    except Exception:
        pass


class ProcessGuard:
    """
    Watches the main app and respawns it if killed.
    """

    def __init__(self, main_app_path: str, check_interval: int = 3):
        """
        Initialize the process guard.

        Args:
            main_app_path: Path to the main app executable/script
            check_interval: Seconds between checks
        """
        self.main_app_path = Path(main_app_path)
        self.check_interval = check_interval
        self._running = False
        self._main_process = None

    def start_main_app(self) -> bool:
        """Start the main application."""
        try:
            if self.main_app_path.suffix == '.py':
                # Running as Python script
                self._main_process = subprocess.Popen(
                    [sys.executable, str(self.main_app_path)]
                )
            elif self.main_app_path.suffix == '.app':
                # Running as macOS .app bundle
                self._main_process = subprocess.Popen(
                    ['open', '-a', str(self.main_app_path)]
                )
            else:
                # Running as compiled binary
                self._main_process = subprocess.Popen(
                    [str(self.main_app_path)]
                )
            return True
        except Exception as e:
            print(f"Failed to start main app: {e}")
            return False

    def is_main_app_running(self) -> bool:
        """Check if main app is still running."""
        if self._main_process is None:
            return False

        return self._main_process.poll() is None

    def watch(self):
        """Main watch loop - respawns app if killed."""
        self._running = True
        set_process_priority_low()

        # Initial launch
        self.start_main_app()
        time.sleep(2)  # Give it time to start

        while self._running:
            try:
                if not self.is_main_app_running():
                    print("Main app terminated. Respawning...")
                    time.sleep(1)
                    self.start_main_app()

                time.sleep(self.check_interval)

            except Exception as e:
                print(f"Guard error: {e}")
                time.sleep(self.check_interval)

    def stop(self):
        """Stop the guard."""
        self._running = False


def find_main_app() -> Path:
    """Find the main app executable or script."""
    if getattr(sys, 'frozen', False):
        # Running as compiled binary
        exe_dir = Path(sys.executable).parent
        # Look for the main app
        for name in ["ProductivityTimer", "main"]:
            candidate = exe_dir / name
            if candidate.exists():
                return candidate
        # Fall back to any binary that's not us
        for f in exe_dir.iterdir():
            if f.is_file() and f.name != Path(sys.executable).name and not f.suffix:
                return f
    else:
        # Running as Python script
        script_dir = Path(__file__).parent.parent.parent
        return script_dir / "run.py"

    return None


def run_guard():
    """Entry point for running as guard process."""
    main_app = find_main_app()

    if main_app is None:
        print("Could not find main application!")
        return

    print(f"Guard starting. Watching: {main_app}")
    guard = ProcessGuard(str(main_app))
    guard.watch()


if __name__ == "__main__":
    run_guard()
