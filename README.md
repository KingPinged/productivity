# Productivity Timer

A desktop app for focused work sessions with app/website blocking. Available for Windows and macOS.

## Features

- **Pomodoro Timer**: 52/17 method (52 min work, 17 min break)
- **App Blocking**: Kills distracting processes (games, social media apps)
- **Website Blocking**: Blocks distracting websites via hosts file and browser extension
- **NSFW Detection**: Browser extension detects adult content and triggers punishment mode
- **Internet Punishment**: Disables network adapters when violations are detected
- **Hard to Disable**: 10-minute cooldown or type 1000 random characters to stop early
- **AFK Detection**: Automatically pauses timer when idle
- **Usage Tracking**: Tracks foreground app and website usage time
- **Desktop Stats Widget**: Floating widget showing hours worked, session history, and clean streak
- **System Tray**: Runs in background with tray icon
- **Auto-Start**: Launches at login (Task Scheduler on Windows, Launch Agents on macOS)
- **Process Guard**: Respawns app if killed during a work session
- **Whitelist**: Allow specific URLs while blocking the domain

## Installation

### Windows

1. Install Python 3.10+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app (requires admin for website blocking):
   ```bash
   python run.py
   ```

### macOS

1. Install Python 3.10+
2. Install dependencies:
   ```bash
   cd productivity-mac
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   python run.py
   ```
   The app will prompt for admin privileges when needed (for hosts file and network control).

## Browser Extension

For website blocking and NSFW detection in browsers (Firefox, Zen, etc.):

1. Open `about:debugging` in your browser
2. Click "Load Temporary Add-on"
3. Select `browser_extension/manifest.json`

The extension syncs with the desktop app automatically via a local HTTP server.

## Project Structure

```
productivity/
├── src/                    # Windows version
│   ├── core/               # Timer, blocking, AFK, usage tracking
│   ├── data/               # Config, blocklists, state persistence
│   ├── ui/                 # Tkinter/ttkbootstrap UI
│   └── utils/              # Constants, autostart, admin helpers
├── productivity-mac/       # macOS version (separate codebase)
│   └── src/                # Same structure, macOS-native APIs
├── browser_extension/      # Shared browser extension
└── run.py                  # Windows entry point
```

## Requirements

### Windows
- Windows 10/11
- Python 3.10+
- Administrator privileges (for hosts file and network control)

### macOS
- macOS 12+
- Python 3.10+
- `pyobjc-framework-Cocoa` and `pyobjc-framework-Quartz` (installed via requirements.txt)
- Administrator privileges (prompted via system dialog when needed)

## License

MIT
