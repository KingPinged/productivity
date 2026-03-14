"""
Entry point for Productivity Timer.
Acts as a supervisor — spawns the app and 3 guard processes.
Copies pythonw.exe to disguised names so processes don't show as 'python' in Task Manager.
To kill the app you must kill ALL processes simultaneously.
"""

import sys
import os
import subprocess
import time
import ctypes
import shutil
import tempfile

NUM_GUARDS = 3
RESPAWN_DELAY = 0.3
POLL_INTERVAL = 0.1

# Disguised process names (without .exe) — look like Windows system processes
MAIN_APP_PROC_NAME = "RuntimeBroker"
GUARD_PROC_NAMES = ["SearchIndexer", "WmiPrvSE", "audiodg"]
SUPERVISOR_PROC_NAME = "csrss"

# Directory to store disguised copies of python executables
_DISGUISE_DIR = os.path.join(tempfile.gettempdir(), ".sysrt")


def _get_disguised_exe(name, source_exe=None):
    """Get path to a disguised copy of python. Creates it if missing."""
    os.makedirs(_DISGUISE_DIR, exist_ok=True)
    target = os.path.join(_DISGUISE_DIR, f"{name}.exe")
    if source_exe is None:
        source_exe = _get_pythonw()
    if not os.path.exists(target):
        shutil.copy2(source_exe, target)
    return target


def _acquire_supervisor_lock():
    """Ensure only one supervisor runs."""
    mutex_name = "ProductivityTimer_Supervisor_Mutex"
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, True, mutex_name)
    ERROR_ALREADY_EXISTS = 183
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        sys.exit(0)
    return handle


def _is_app_running():
    """Check if the main app is running by checking its mutex."""
    kernel32 = ctypes.windll.kernel32
    mutex_name = "ProductivityTimer_SingleInstance_Mutex"
    handle = kernel32.OpenMutexW(0x00100000, False, mutex_name)  # SYNCHRONIZE
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


def _get_pythonw():
    """Get path to pythonw.exe (windowless Python)."""
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(pythonw):
        return pythonw
    return sys.executable


def _start_app(script_dir):
    """Start the main app process with a disguised process name."""
    main_script = os.path.join(script_dir, "src", "main.py")
    exe = _get_disguised_exe(MAIN_APP_PROC_NAME)

    try:
        proc = subprocess.Popen(
            [exe, main_script],
            cwd=script_dir,
        )
        return proc
    except Exception as e:
        print(f"[Supervisor] Failed to start app: {e}")
        return None


def _start_guards(script_dir):
    """Start 3 guard processes with disguised process names."""
    guard_script = os.path.join(script_dir, "src", "core", "guard_runner.py")

    guards = []
    for i in range(NUM_GUARDS):
        guard_name = GUARD_PROC_NAMES[i] if i < len(GUARD_PROC_NAMES) else f"svchost_{i}"
        exe = _get_disguised_exe(guard_name)
        try:
            proc = subprocess.Popen(
                [exe, guard_script, str(i + 1)],
                cwd=script_dir,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            guards.append(proc)
            print(f"[Supervisor] Guard {i+1} started as {guard_name}.exe (PID {proc.pid})")
        except Exception as e:
            print(f"[Supervisor] Failed to start guard {i+1}: {e}")

    return guards


def _install_scheduled_task():
    """Install a Windows Scheduled Task that re-launches the supervisor every minute.
    Acts as a last-resort respawner if all processes are killed."""
    task_name = "SystemRuntimeBroker"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    run_script = os.path.join(script_dir, "run.py")
    pythonw = _get_pythonw()

    # Check if task already exists
    check = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name],
        capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if check.returncode == 0:
        return  # Already installed

    # Create task that runs every 1 minute
    try:
        subprocess.run([
            "schtasks", "/Create",
            "/TN", task_name,
            "/TR", f'"{pythonw}" "{run_script}"',
            "/SC", "MINUTE", "/MO", "1",
            "/F",  # Force overwrite
            "/RL", "HIGHEST",
        ], capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception:
        pass  # Non-critical — works without admin too, just no scheduled task


def run_supervisor():
    """
    Main supervisor loop.
    - Installs a scheduled task as last-resort respawner
    - Starts the app and 3 guards with disguised process names
    - Polls every 100ms to respawn anything killed
    """
    _lock = _acquire_supervisor_lock()

    # Install scheduled task fallback (runs every 1 min)
    _install_scheduled_task()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Start app
    print("[Supervisor] Starting app...")
    app_proc = _start_app(script_dir)

    # Give app time to initialize before starting guards
    time.sleep(3)

    # Start guards
    print("[Supervisor] Starting guards...")
    guard_procs = _start_guards(script_dir)

    # Supervisor watch loop — poll every 0.5s for fast respawn
    while True:
        # Check if app is still running
        if app_proc is None or app_proc.poll() is not None:
            time.sleep(RESPAWN_DELAY)
            if not _is_app_running():
                print("[Supervisor] App died! Respawning...")
                app_proc = _start_app(script_dir)
            else:
                app_proc = None  # Already respawned by a guard

        # Check all guards every cycle — respawn any dead ones immediately
        for i, proc in enumerate(guard_procs):
            if proc.poll() is not None:
                guard_name = GUARD_PROC_NAMES[i] if i < len(GUARD_PROC_NAMES) else f"svchost_{i}"
                print(f"[Supervisor] Guard {i+1} died, restarting as {guard_name}.exe...")
                guard_script = os.path.join(script_dir, "src", "core", "guard_runner.py")
                exe = _get_disguised_exe(guard_name)
                try:
                    guard_procs[i] = subprocess.Popen(
                        [exe, guard_script, str(i + 1)],
                        cwd=script_dir,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    )
                except Exception as e:
                    print(f"[Supervisor] Failed to restart guard {i+1}: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_supervisor()
