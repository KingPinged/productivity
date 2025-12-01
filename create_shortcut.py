"""
Create a desktop shortcut for Productivity Timer.
"""

import os
import sys
from pathlib import Path

def create_shortcut():
    """Create a desktop shortcut using PowerShell."""

    # Get paths - check OneDrive desktop first, then regular desktop
    onedrive_desktop = Path(os.environ["USERPROFILE"]) / "OneDrive" / "Desktop"
    regular_desktop = Path(os.environ["USERPROFILE"]) / "Desktop"

    if onedrive_desktop.exists():
        desktop = onedrive_desktop
    else:
        desktop = regular_desktop
    app_dir = Path(__file__).parent.resolve()
    python_exe = sys.executable
    main_script = app_dir / "main.py"
    icon_path = app_dir / "assets" / "icon.ico"

    shortcut_path = desktop / "Productivity Timer.lnk"

    # PowerShell script to create shortcut
    # Using pythonw.exe to avoid console window (if available)
    pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
    if not Path(pythonw_exe).exists():
        pythonw_exe = python_exe

    ps_script = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "{pythonw_exe}"
$Shortcut.Arguments = '"{main_script}"'
$Shortcut.WorkingDirectory = "{app_dir}"
$Shortcut.Description = "Productivity Timer - Focus & Block Distractions"
'''

    # Add icon if it exists
    if icon_path.exists():
        ps_script += f'$Shortcut.IconLocation = "{icon_path}"\n'

    ps_script += '$Shortcut.Save()\n'

    # Run PowerShell to create shortcut
    import subprocess
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f"Shortcut created: {shortcut_path}")
        print("\nTo run as Administrator (required for website blocking):")
        print("  Right-click the shortcut > Properties > Advanced > Run as administrator")
    else:
        print(f"Error creating shortcut: {result.stderr}")


if __name__ == "__main__":
    create_shortcut()
