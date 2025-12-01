"""
Admin privilege handling for Windows.
"""

import ctypes
import sys


def is_admin() -> bool:
    """
    Check if the current process has administrator privileges.

    Returns:
        True if running as admin, False otherwise
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_as_admin() -> bool:
    """
    Re-launch the current script with administrator privileges.
    The current process will exit if elevation is requested.

    Returns:
        True if already admin, False if elevation was requested (process will exit)
    """
    if is_admin():
        return True

    try:
        # Get the current script/executable
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            script = sys.executable
            params = " ".join(sys.argv[1:])
        else:
            # Running as script
            script = sys.executable
            params = f'"{sys.argv[0]}"'
            if len(sys.argv) > 1:
                params += " " + " ".join(f'"{arg}"' for arg in sys.argv[1:])

        # Request elevation
        result = ctypes.windll.shell32.ShellExecuteW(
            None,           # hwnd
            "runas",        # operation - request elevation
            script,         # file to execute
            params,         # parameters
            None,           # directory
            1               # SW_SHOWNORMAL
        )

        # If ShellExecute succeeds, result > 32
        if result > 32:
            sys.exit(0)  # Exit current non-elevated process
        else:
            return False  # User declined UAC or error

    except Exception:
        return False

    return False


def require_admin(func):
    """
    Decorator to ensure function only runs with admin privileges.
    Raises PermissionError if not running as admin.
    """
    def wrapper(*args, **kwargs):
        if not is_admin():
            raise PermissionError("This operation requires administrator privileges")
        return func(*args, **kwargs)
    return wrapper
