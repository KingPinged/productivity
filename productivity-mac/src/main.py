"""
Entry point for Productivity Timer (macOS).
"""

import subprocess
import signal
import sys
import os
import resource

# Add parent directory to path for imports when running as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.admin import is_admin
from src.utils.constants import CLEAN_EXIT_FILE
from src.data.config import Config
from src.app import ProductivityApp


def _launch_guard() -> None:
    """Spawn two process guards that watch our PID and each other."""
    from src.core.process_guard import count_running_guards

    existing = count_running_guards(exclude_pid=os.getpid())
    if existing >= 2:
        print(f"Both guards already running ({existing} found) — skipping spawn")
        return

    guard_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "core", "process_guard.py"
    )
    my_pid = str(os.getpid())

    for guard_id in (1, 2):
        # Skip if we already have enough guards
        if existing >= guard_id:
            continue
        try:
            subprocess.Popen(
                [sys.executable, guard_script,
                 "--watch-pid", my_pid,
                 "--guard-id", str(guard_id)],
                start_new_session=True,
            )
            print(f"Guard-{guard_id} launched (watching PID {my_pid})")
        except Exception as e:
            print(f"Failed to launch guard-{guard_id}: {e}")


def _suppress_crash_reporter() -> None:
    """Disable macOS 'Python quit unexpectedly' dialog.

    Sets the process core-dump size to 0, which tells macOS CrashReporter
    there is nothing to report — so no dialog is shown on abnormal exit.
    """
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except Exception:
        pass

    # Also ignore SIGABRT so abort() doesn't trigger the reporter
    try:
        signal.signal(signal.SIGABRT, signal.SIG_IGN)
    except Exception:
        pass


def main():
    """Main entry point."""
    _suppress_crash_reporter()

    # Remove clean exit sentinel from previous run
    CLEAN_EXIT_FILE.unlink(missing_ok=True)

    # On macOS, we don't try to relaunch as admin — osascript's
    # "do shell script" runs without WindowServer access, so Tkinter
    # can't create windows in an elevated process.
    # Instead, individual operations (hosts file) use per-operation
    # osascript elevation when needed.
    has_admin = is_admin()

    # Load configuration
    config = Config.load()

    # Spawn process guard (auto-restart layer)
    _launch_guard()

    # Create and run the application.
    # Wrap in a top-level handler so crashes exit silently (code 1)
    # instead of aborting with a signal, which triggers macOS crash reporter.
    try:
        app = ProductivityApp(config, has_admin=has_admin)
        app.run()
    except Exception as e:
        print(f"[FATAL] Unhandled exception: {e}")
        os._exit(1)


if __name__ == "__main__":
    main()
