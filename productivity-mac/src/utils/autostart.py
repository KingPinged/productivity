"""
macOS auto-start registration using Launch Agents.
Creates a plist in ~/Library/LaunchAgents to run the app at login.
"""

import plistlib
import subprocess
import sys
import os
from pathlib import Path

from src.utils.constants import APP_NAME

PLIST_LABEL = f"com.{APP_NAME.lower()}.plist"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / PLIST_LABEL


def _get_command_args() -> list[str]:
    """Get the command to run for the launch agent."""
    if getattr(sys, 'frozen', False):
        return [sys.executable]
    else:
        script = os.path.abspath(sys.argv[0])
        if not os.path.exists(script):
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            script = os.path.join(project_dir, 'run.py')
        return [sys.executable, script]


def enable_autostart() -> bool:
    """
    Register app to run at login via Launch Agents.
    Creates a plist at ~/Library/LaunchAgents/.
    """
    try:
        program_args = _get_command_args()

        plist_data = {
            'Label': PLIST_LABEL,
            'ProgramArguments': program_args,
            'RunAtLoad': True,
            'KeepAlive': False,
        }

        # Ensure LaunchAgents directory exists
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Write plist file
        with open(PLIST_PATH, 'wb') as f:
            plistlib.dump(plist_data, f)

        # Load the launch agent
        subprocess.run(
            ['launchctl', 'load', str(PLIST_PATH)],
            capture_output=True,
        )

        print(f"Autostart enabled via Launch Agent")
        return True

    except Exception as e:
        print(f"Error enabling autostart: {e}")
        return False


def disable_autostart() -> bool:
    """Unload and remove the launch agent plist."""
    try:
        if PLIST_PATH.exists():
            # Unload the launch agent
            subprocess.run(
                ['launchctl', 'unload', str(PLIST_PATH)],
                capture_output=True,
            )

            # Delete the plist file
            PLIST_PATH.unlink()

        print("Autostart disabled")
        return True

    except Exception as e:
        print(f"Error disabling autostart: {e}")
        return False


def is_autostart_enabled() -> bool:
    """Check if the launch agent plist exists."""
    return PLIST_PATH.exists()
