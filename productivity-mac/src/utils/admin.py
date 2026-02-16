"""
Admin privilege handling for macOS.
Uses osascript for privilege escalation when needed.
"""

import os
import sys
import subprocess


def is_admin() -> bool:
    """
    Check if the current process has root privileges.

    Returns:
        True if running as root, False otherwise
    """
    return os.geteuid() == 0


def run_as_admin() -> bool:
    """
    Re-launch the current script with administrator privileges via osascript.
    The current process will exit if elevation is requested.

    Returns:
        True if already admin, False if elevation was requested
    """
    if is_admin():
        return True

    try:
        if getattr(sys, 'frozen', False):
            script = sys.executable
            args = ' '.join(f'\\"{a}\\"' for a in sys.argv[1:])
            cmd = f'\\"{script}\\" {args}'.strip()
        else:
            script = sys.executable
            argv0 = sys.argv[0]
            args = ' '.join(f'\\"{a}\\"' for a in sys.argv[1:])
            cmd = f'\\"{script}\\" \\"{argv0}\\" {args}'.strip()

        result = subprocess.run(
            [
                'osascript', '-e',
                f'do shell script "{cmd}" with administrator privileges',
            ],
            capture_output=True,
        )

        if result.returncode == 0:
            sys.exit(0)
        else:
            return False

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
