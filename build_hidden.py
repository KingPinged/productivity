"""
Build script to compile Productivity Timer with disguised process names.
Creates two executables:
1. Main app - disguised as a Windows system process
2. Guard process - watches and respawns the main app if killed

Makes it much harder to identify and kill in Task Manager.
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

# Disguised names - look like Windows system processes
# The guard and main app use different names so killing one doesn't kill both
MAIN_APP_NAME = "RuntimeBroker"      # Main app - looks like Windows Runtime Broker
GUARD_NAMES = [
    "SearchIndexer",   # Guard 1 - looks like Windows Search Indexer
    "WmiPrvSE",        # Guard 2 - looks like Windows Management Instrumentation
    "audiodg",         # Guard 3 - looks like Windows Audio Device Graph
]


def install_pyinstaller():
    """Ensure PyInstaller is installed."""
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)


def build_main_app():
    """Build the main application with hidden name."""
    print(f"\n{'='*50}")
    print(f"Building main app as '{MAIN_APP_NAME}.exe'...")
    print('='*50)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", MAIN_APP_NAME,
        "--onefile",
        "--windowed",  # No console window
        "--uac-admin",  # Request admin on launch
        "--add-data", "src;src",
        "--hidden-import", "ttkbootstrap",
        "--hidden-import", "PIL",
        "--hidden-import", "pystray",
        "--hidden-import", "psutil",
        "--clean",
        "-y",  # Overwrite without asking
        "run.py"
    ]

    subprocess.run(cmd, check=True)
    print(f"Main app built: dist/{MAIN_APP_NAME}.exe")


def build_guards():
    """Build 3 guard processes with different hidden names."""
    for i, guard_name in enumerate(GUARD_NAMES, 1):
        print(f"\n{'='*50}")
        print(f"Building guard {i} as '{guard_name}.exe'...")
        print('='*50)

        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name", guard_name,
            "--onefile",
            "--windowed",  # No console window - completely hidden
            "--uac-admin",  # Request admin on launch
            "--hidden-import", "psutil",
            "--clean",
            "-y",
            "src/core/guard_runner.py"
        ]

        subprocess.run(cmd, check=True)
        print(f"Guard {i} built: dist/{guard_name}.exe")


def create_launcher():
    """Create a launcher script that starts all processes."""
    guard_lines = "\n".join(
        f'start "" /B "%~dp0{name}.exe" {i}'
        for i, name in enumerate(GUARD_NAMES, 1)
    )
    launcher_content = f'''@echo off
:: Productivity Timer Hidden Launcher
:: Starts the main app and 3 guard processes with different names

:: Start main app
start "" /B "%~dp0{MAIN_APP_NAME}.exe"

:: Start guards (each monitors and respawns main app if killed)
{guard_lines}
'''

    launcher_path = Path("dist") / "Start_Hidden.bat"
    launcher_path.write_text(launcher_content)
    print(f"Launcher created: {launcher_path}")


def create_startup_task():
    """Create a Windows scheduled task for autostart (optional)."""
    task_xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>System Runtime Service</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>%INSTALL_PATH%\\{GUARD_NAMES[0]}.exe</Command>
    </Exec>
  </Actions>
</Task>
'''
    task_path = Path("dist") / "scheduled_task.xml"
    task_path.write_text(task_xml, encoding='utf-16')
    print(f"Scheduled task template: {task_path}")
    print("  To install: schtasks /create /tn \"System Runtime\" /xml scheduled_task.xml")


def build():
    """Build everything."""
    print("="*60)
    print("PRODUCTIVITY TIMER - STEALTH BUILD")
    print("="*60)
    print(f"\nMain app will appear as: {MAIN_APP_NAME}.exe")
    print(f"Guards will appear as:   {', '.join(n + '.exe' for n in GUARD_NAMES)}")
    print("\nThese look like normal Windows system processes.")

    install_pyinstaller()
    build_main_app()
    build_guards()
    create_launcher()
    create_startup_task()

    guard_names_str = ", ".join(f"{n}.exe" for n in GUARD_NAMES)

    print("\n" + "="*60)
    print("BUILD COMPLETE!")
    print("="*60)
    print(f"\nFiles in dist/ folder:")
    print(f"  - {MAIN_APP_NAME}.exe  (main app)")
    for i, name in enumerate(GUARD_NAMES, 1):
        print(f"  - {name}.exe         (guard {i} - respawns main if killed)")
    print(f"  - Start_Hidden.bat     (launcher)")
    print(f"\nTo use:")
    print(f"  1. Run Start_Hidden.bat")
    print(f"\nAll 3 guards independently monitor and respawn the main app.")
    print(f"To fully stop: Kill ALL 4 processes simultaneously:")
    print(f"  {MAIN_APP_NAME}.exe + {guard_names_str}")


if __name__ == "__main__":
    build()
