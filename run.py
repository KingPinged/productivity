"""
Development entry point for Productivity Timer.
Acts as a supervisor — runs the app as a subprocess and respawns it if killed.
"""

import sys
import os
import subprocess
import time
import ctypes

RESPAWN_DELAY = 2  # seconds to wait before respawning


def _acquire_supervisor_lock():
    """Ensure only one supervisor runs. Returns mutex handle or exits."""
    mutex_name = "ProductivityTimer_Supervisor_Mutex"
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, True, mutex_name)
    ERROR_ALREADY_EXISTS = 183
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        print("Supervisor already running. Exiting.")
        sys.exit(0)
    return handle


def run_supervisor():
    """Run the app in a respawn loop. If the app dies for any reason, restart it."""
    _lock = _acquire_supervisor_lock()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(script_dir, "src", "main.py")

    while True:
        print(f"[Supervisor] Starting app...")
        try:
            process = subprocess.Popen(
                [sys.executable, main_script],
                cwd=script_dir,
            )
            process.wait()  # Block until process exits
            exit_code = process.returncode
            print(f"[Supervisor] App exited with code {exit_code}")
        except Exception as e:
            print(f"[Supervisor] Error running app: {e}")

        print(f"[Supervisor] Respawning in {RESPAWN_DELAY}s...")
        time.sleep(RESPAWN_DELAY)


if __name__ == "__main__":
    run_supervisor()
