"""
Entry point for Productivity Timer.
Handles admin elevation and application startup.
"""

import sys
import os

# Add parent directory to path for imports when running as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tkinter import messagebox
import ttkbootstrap as ttk

from src.utils.admin import is_admin, run_as_admin
from src.data.config import Config
from src.app import ProductivityApp


def _acquire_single_instance_lock():
    """Ensure only one instance of the app runs. Returns lock handle or exits."""
    import ctypes
    mutex_name = "ProductivityTimer_SingleInstance_Mutex"
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, True, mutex_name)
    ERROR_ALREADY_EXISTS = 183
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        print("Another instance is already running. Exiting.")
        sys.exit(0)
    return handle


def main():
    """Main entry point."""
    # Ensure single instance
    _lock = _acquire_single_instance_lock()

    # Check for admin privileges
    has_admin = is_admin()

    if not has_admin:
        # Create a temporary root for the dialog
        temp_root = ttk.Window(themename="darkly")
        temp_root.withdraw()

        response = messagebox.askyesno(
            "Administrator Required",
            "Productivity Timer needs administrator privileges to:\n\n"
            "• Block websites by modifying the hosts file\n"
            "• Prevent tampering with blocking\n\n"
            "Would you like to restart with admin rights?\n\n"
            "Selecting 'No' will run without website blocking.",
            parent=temp_root
        )

        temp_root.destroy()

        if response:
            # User wants admin - relaunch elevated
            run_as_admin()
            return  # This process will exit

        # User declined - run without website blocking
        has_admin = False

    # Load configuration
    config = Config.load()

    # Create and run the application
    app = ProductivityApp(config, has_admin=has_admin)
    app.run()


if __name__ == "__main__":
    main()
