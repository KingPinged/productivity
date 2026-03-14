# Native Browser Tracker (Extension-Free Fallback)

**Date:** 2026-02-20

## Problem

The app relies on a Chrome extension to track which websites the user visits and enforce blocking. If the user deletes the extension, disables it, or uses a different browser, the app is blind to browser activity.

## Solution

A native `BrowserTracker` that uses macOS AppleScript (and Accessibility API for Firefox) to:
1. Detect the current URL from any browser's address bar
2. Report website usage (same data path as the extension)
3. Enforce blocking by redirecting tabs via AppleScript when a blocked site is detected

## Architecture

### New file: `src/core/browser_tracker.py`

A `BrowserTracker` class with these responsibilities:

- **URL detection:** Get current URL from the active browser tab
  - AppleScript for Chrome, Safari, Arc, Brave, Edge, Vivaldi (covers ~95% of users)
  - Accessibility API (AXUIElement) for Firefox (no AppleScript dictionary)
- **Domain extraction:** Parse domain from URL
- **Dwell time tracking:** Track seconds spent on each domain, report via the same `_on_website_usage()` callback the extension uses
- **Block enforcement:** When blocking is active and a blocked domain is detected, redirect the tab to a blocked page via AppleScript

### Key methods

```
check_active_browser(app_name) -> Optional[str]   # returns domain if browser is in focus
_get_url_applescript(browser_name) -> Optional[str] # AppleScript URL fetch
_get_url_accessibility(browser_name) -> Optional[str] # AX API fallback (Firefox)
_extract_domain(url) -> str                         # parse domain from URL
enforce_blocking(browser_name, domain) -> None      # redirect if domain is blocked
_redirect_tab(browser_name, url) -> bool            # AppleScript redirect
```

### Browser support matrix

| Browser | Get URL | Redirect Tab | Method |
|---------|---------|-------------|--------|
| Google Chrome | Yes | Yes | AppleScript |
| Safari | Yes | Yes | AppleScript |
| Arc | Yes | Yes | AppleScript |
| Brave Browser | Yes | Yes | AppleScript |
| Microsoft Edge | Yes | Yes | AppleScript |
| Vivaldi | Yes | Yes | AppleScript |
| Firefox | Yes | No | Accessibility API |

### Integration with UsageTracker

The `BrowserTracker` is called from `UsageTracker._tick()`. When the foreground app is a browser:

```python
app_name = self.get_foreground_app()
if app_name:
    self.on_usage_tick(app_name, 'app', USAGE_TRACKING_INTERVAL)
    if self.browser_tracker:
        self.browser_tracker.on_tick(app_name, USAGE_TRACKING_INTERVAL)
```

### Extension detection (avoid double-reporting)

The extension pings `/status` every 2 seconds. `ExtensionServer` tracks the last ping timestamp. If no ping in 10 seconds, the extension is considered absent and `BrowserTracker` activates.

`BrowserTracker` checks `extension_server.is_extension_connected()` before reporting.

### Blocking enforcement

When `is_blocking=True` and a blocked domain is detected:
1. Redirect the active tab via AppleScript: `set URL of active tab of front window to "<blocked_page>"`
2. The blocked page is a `file://` URL pointing to the existing `blocked.html`
3. Firefox: no redirect (no AppleScript support), rely on /etc/hosts blocking only

### What this doesn't cover (vs extension)

| Feature | Extension | Native Tracker |
|---------|-----------|---------------|
| Exact URL + domain | Yes | Yes |
| Page content for NSFW | Yes | No |
| URL-level whitelisting | Yes | No (domain-level only) |
| Tab switch detection | Instant | 5s poll |
| Firefox redirect | Yes | No |

## Files to modify

1. **New:** `src/core/browser_tracker.py` - The main tracker class
2. **Modify:** `src/core/usage_tracker.py` - Integrate BrowserTracker into tick loop
3. **Modify:** `src/core/extension_server.py` - Add `is_extension_connected()` method with last-ping tracking
4. **Modify:** `src/app.py` - Wire up BrowserTracker with callbacks and blocking state
5. **Modify:** `src/core/productivity_monitor.py` - Export BROWSERS set for reuse (already accessible)

## No new dependencies

- AppleScript: uses `subprocess` + `osascript` (already used elsewhere in the codebase)
- Accessibility API: uses `ApplicationServices` from `pyobjc-framework-Quartz` (already in requirements)
