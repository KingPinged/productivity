# Productivity Timer

A Windows desktop app for focused work sessions with app/website blocking.

## Features

- **Pomodoro Timer**: 52/17 method (52 min work, 17 min break)
- **App Blocking**: Kills distracting processes (games, social media apps)
- **Website Blocking**: Blocks distracting websites via browser extension
- **Hard to Disable**: 10-minute cooldown or type 1000 random characters to stop early
- **System Tray**: Runs in background with tray icon
- **Whitelist**: Allow specific URLs while blocking the domain

## Installation

1. Install Python 3.10+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   python main.py
   ```

Or use `install.bat` and `start.bat` on Windows.

## Browser Extension

For website blocking in browsers (Firefox, Zen, etc.):

1. Open `about:debugging` in your browser
2. Click "Load Temporary Add-on"
3. Select `browser_extension/manifest.json`

The extension syncs with the desktop app automatically.

## Requirements

- Windows 10/11
- Python 3.10+
- Administrator privileges (for hosts file blocking)

## License

MIT
