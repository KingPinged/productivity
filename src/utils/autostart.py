"""
Windows auto-start (startup) registration.
"""

import sys
import winreg

from src.utils.constants import APP_NAME


REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_executable_path() -> str:
    """
    Get the path to the current executable/script.

    Returns:
        Path string suitable for registry
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return f'"{sys.executable}"'
    else:
        # Running as script
        return f'"{sys.executable}" "{sys.argv[0]}"'


def enable_autostart() -> bool:
    """
    Add application to Windows startup.

    Returns:
        True if successful, False otherwise
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_PATH,
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(
            key,
            APP_NAME,
            0,
            winreg.REG_SZ,
            get_executable_path()
        )
        winreg.CloseKey(key)
        return True
    except WindowsError:
        return False


def disable_autostart() -> bool:
    """
    Remove application from Windows startup.

    Returns:
        True if successful, False otherwise
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_PATH,
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except WindowsError:
        return False


def is_autostart_enabled() -> bool:
    """
    Check if application is set to start with Windows.

    Returns:
        True if auto-start is enabled, False otherwise
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_PATH,
            0,
            winreg.KEY_READ
        )
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except WindowsError:
        return False
