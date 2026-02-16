"""
Entry point for Productivity Timer (macOS).
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


def main():
    """Main entry point."""
    # Check for admin privileges
    has_admin = is_admin()

    if not has_admin:
        # Create a temporary root for the dialog
        temp_root = ttk.Window(themename="darkly")
        temp_root.withdraw()

        response = messagebox.askyesno(
            "Administrator Required",
            "Productivity Timer needs administrator privileges to:\n\n"
            "\u2022 Block websites by modifying the hosts file\n"
            "\u2022 Disable network adapters for punishment system\n\n"
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
