# Productivity Timer Browser Extension

This browser extension blocks distracting websites from within the browser itself.
It works with Firefox-based browsers including **Zen Browser**, Firefox, LibreWolf, Waterfox, and Floorp.

## Installation

### Method 1: Temporary Installation (for testing)

1. Open Zen Browser
2. Go to `about:debugging#/runtime/this-firefox`
3. Click "Load Temporary Add-on"
4. Navigate to this folder and select `manifest.json`

### Method 2: Permanent Installation

1. Open Zen Browser
2. Go to `about:addons`
3. Click the gear icon → "Install Add-on From File"
4. Select the `.xpi` file (if packaged) or use temporary installation

### Creating Icons

Run the icon creation script first:

```
cd browser_extension
python create_icons.py
```

## Usage

1. Click the extension icon in the toolbar
2. Click "Start Blocking" to enable website blocking
3. When you try to visit a blocked site, you'll see a "Site Blocked" page
4. Click "Stop Blocking" to disable

## Integration with Desktop App

The desktop app will automatically:
1. Configure your browser to disable DNS-over-HTTPS (so hosts file blocking works)
2. You may need to restart your browser after running the app for the first time

## Blocked Sites

Default blocked sites include:
- Social Media: Facebook, Twitter/X, Instagram, TikTok, Reddit, etc.
- Video Streaming: YouTube, Netflix, Twitch, etc.
- Gaming: Steam, Epic Games, Discord, etc.
- Messaging: WhatsApp Web, Telegram Web, etc.

You can customize the blocklist through the extension popup or by modifying `background.js`.
