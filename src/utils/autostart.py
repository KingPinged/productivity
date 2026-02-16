"""
Windows auto-start registration using Task Scheduler.
Runs the app at logon with admin privileges (no UAC prompt on each login).
"""

import subprocess
import sys
import os

from src.utils.constants import APP_NAME

TASK_NAME = APP_NAME


def _get_command_args() -> tuple[str, str]:
    """Get the executable and arguments for the scheduled task."""
    if getattr(sys, 'frozen', False):
        return sys.executable, ''
    else:
        # Find run.py relative to the package
        # sys.argv[0] might be relative, so resolve it
        script = os.path.abspath(sys.argv[0])
        # If run.py doesn't exist at argv[0], try finding it from the project root
        if not os.path.exists(script):
            # Fallback: look for run.py in the project directory
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            script = os.path.join(project_dir, 'run.py')
        return sys.executable, script


def enable_autostart() -> bool:
    """
    Register app to run at logon with admin privileges via Task Scheduler.
    Requires the current process to be running as admin to create the task.
    """
    try:
        exe, script = _get_command_args()

        # Build schtasks command
        # /RL HIGHEST = run with highest privileges (admin)
        # /SC ONLOGON = trigger at user logon
        # /F = force overwrite if exists
        if script:
            # Running as script: pythonw.exe run.py
            # Use pythonw to avoid console window
            pythonw = exe.replace('python.exe', 'pythonw.exe')
            if not os.path.exists(pythonw):
                pythonw = exe
            cmd = [
                'schtasks', '/Create',
                '/TN', TASK_NAME,
                '/TR', f'"{pythonw}" "{script}"',
                '/SC', 'ONLOGON',
                '/RL', 'HIGHEST',
                '/F',
            ]
        else:
            # Running as compiled exe
            cmd = [
                'schtasks', '/Create',
                '/TN', TASK_NAME,
                '/TR', f'"{exe}"',
                '/SC', 'ONLOGON',
                '/RL', 'HIGHEST',
                '/F',
            ]

        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )

        if result.returncode == 0:
            print(f"Autostart enabled via Task Scheduler (admin)")
            return True
        else:
            print(f"Failed to create scheduled task: {result.stderr.strip()}")
            return False

    except Exception as e:
        print(f"Error enabling autostart: {e}")
        return False


def disable_autostart() -> bool:
    """Remove the scheduled task."""
    try:
        result = subprocess.run(
            ['schtasks', '/Delete', '/TN', TASK_NAME, '/F'],
            capture_output=True, text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode == 0:
            print("Autostart disabled")

        # Also clean up old registry entry if it exists
        _remove_registry_entry()

        return True
    except Exception as e:
        print(f"Error disabling autostart: {e}")
        return False


def is_autostart_enabled() -> bool:
    """Check if the scheduled task exists."""
    try:
        result = subprocess.run(
            ['schtasks', '/Query', '/TN', TASK_NAME],
            capture_output=True, text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return result.returncode == 0
    except Exception:
        return False


def _remove_registry_entry() -> None:
    """Clean up legacy registry Run key if it exists."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        print("Cleaned up old registry autostart entry")
    except Exception:
        pass  # Doesn't exist, that's fine
