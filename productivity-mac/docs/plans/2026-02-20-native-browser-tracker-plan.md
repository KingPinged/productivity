# Native Browser Tracker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add extension-free browser URL tracking and tab-level block enforcement using macOS AppleScript and Accessibility APIs.

**Architecture:** A `BrowserTracker` class polls the active browser's URL bar every 5 seconds (piggybacking on `UsageTracker`'s existing tick). It uses AppleScript for Chrome-family/Safari browsers and the macOS Accessibility API for Firefox. When the extension is connected (detected via ping heartbeat), the tracker defers to it. When blocking is active, it redirects blocked tabs via AppleScript.

**Tech Stack:** Python 3, PyObjC (ApplicationServices for AXUIElement), subprocess + osascript (AppleScript), urllib.parse

---

### Task 1: Add extension heartbeat tracking to ExtensionServer

**Files:**
- Modify: `src/core/extension_server.py`

**Step 1: Add last-ping timestamp to ExtensionRequestHandler**

In `ExtensionRequestHandler`, add a class-level timestamp field and update it on every `/status` GET:

```python
# Add to class-level state at line 28 (after existing class variables)
import time as _time

# In ExtensionRequestHandler class body, after nsfw_cache_callback:
last_extension_ping: float = 0.0
```

Then in `_handle_status()`, record the ping time:

```python
def _handle_status(self):
    """Return current blocking status."""
    ExtensionRequestHandler.last_extension_ping = _time.time()
    # ... rest unchanged
```

**Step 2: Add `is_extension_connected()` to ExtensionServer**

```python
def is_extension_connected(self, timeout: float = 10.0) -> bool:
    """Check if the browser extension has pinged recently."""
    if ExtensionRequestHandler.last_extension_ping == 0.0:
        return False
    import time
    return (time.time() - ExtensionRequestHandler.last_extension_ping) < timeout
```

**Step 3: Verify it runs**

Run: `python -c "from src.core.extension_server import ExtensionServer; s = ExtensionServer(); print(s.is_extension_connected())"`
Expected: `False` (no extension pinging)

**Step 4: Commit**

```bash
git add src/core/extension_server.py
git commit -m "feat: add extension heartbeat detection to ExtensionServer"
```

---

### Task 2: Create BrowserTracker with URL detection

**Files:**
- Create: `src/core/browser_tracker.py`

**Step 1: Create the file with AppleScript URL detection**

```python
"""
Native browser URL tracker for macOS.
Detects the active browser tab's URL using AppleScript (Chrome-family, Safari)
and the Accessibility API (Firefox). Falls back gracefully when unavailable.
"""

import subprocess
import time
from typing import Optional, Callable, Set
from urllib.parse import urlparse


# Chrome-family browsers share the same AppleScript syntax
APPLESCRIPT_CHROME_BROWSERS = {
    "google chrome", "brave browser", "microsoft edge",
    "vivaldi", "chromium", "arc",
}

APPLESCRIPT_SAFARI_BROWSERS = {"safari"}

# All browsers we can get URLs from (superset)
SUPPORTED_BROWSERS = APPLESCRIPT_CHROME_BROWSERS | APPLESCRIPT_SAFARI_BROWSERS | {"firefox"}


class BrowserTracker:
    """
    Tracks the active browser tab URL natively on macOS.
    Used as a fallback when the browser extension is not connected.
    """

    def __init__(
        self,
        on_website_usage: Optional[Callable[[str, str, int], None]] = None,
        is_extension_connected: Optional[Callable[[], bool]] = None,
        is_blocking: Optional[Callable[[], bool]] = None,
        get_blocked_sites: Optional[Callable[[], Set[str]]] = None,
        get_always_blocked_sites: Optional[Callable[[], Set[str]]] = None,
        blocked_page_path: Optional[str] = None,
    ):
        """
        Args:
            on_website_usage: Callback(category, domain, seconds) for usage reporting
            is_extension_connected: Returns True if extension is active (skip tracking)
            is_blocking: Returns True if work session blocking is active
            get_blocked_sites: Returns set of domains blocked during work sessions
            get_always_blocked_sites: Returns set of always-blocked domains (adult)
            blocked_page_path: File path to blocked.html for redirects
        """
        self.on_website_usage = on_website_usage
        self.is_extension_connected = is_extension_connected
        self.is_blocking = is_blocking
        self.get_blocked_sites = get_blocked_sites
        self.get_always_blocked_sites = get_always_blocked_sites
        self.blocked_page_path = blocked_page_path

        self._current_domain: Optional[str] = None
        self._current_browser: Optional[str] = None
        self._domain_start: float = 0.0

        # Accessibility API availability (for Firefox)
        self._ax_available = False
        try:
            from ApplicationServices import AXUIElementCreateApplication
            self._ax_available = True
        except ImportError:
            pass

    def on_tick(self, app_name: str, interval_seconds: int) -> None:
        """
        Called every tick from UsageTracker when foreground app is detected.
        Only acts when the app is a browser and no extension is connected.

        Args:
            app_name: Name of the foreground application
            interval_seconds: Seconds since last tick
        """
        name_lower = app_name.lower()

        # Not a supported browser — nothing to do
        if name_lower not in SUPPORTED_BROWSERS:
            self._flush_domain(interval_seconds)
            self._current_domain = None
            self._current_browser = None
            return

        # Extension is handling it — defer
        if self.is_extension_connected and self.is_extension_connected():
            return

        # Get the current URL
        url = self._get_url(name_lower)
        domain = self._extract_domain(url) if url else None

        if domain:
            if domain != self._current_domain:
                # Domain changed — flush old, start new
                self._flush_domain(interval_seconds)
                self._current_domain = domain
                self._current_browser = name_lower
                self._domain_start = time.time()
            # else: same domain, accumulate time (reported on next change or flush)

            # Check blocking
            if self.is_blocking and self.is_blocking():
                self._check_and_enforce_block(name_lower, domain)
        else:
            self._flush_domain(interval_seconds)
            self._current_domain = None
            self._current_browser = None

    def _flush_domain(self, interval_seconds: int) -> None:
        """Report accumulated time on the current domain."""
        if self._current_domain and self.on_website_usage:
            self.on_website_usage('website', self._current_domain, interval_seconds)

    def _get_url(self, browser_name_lower: str) -> Optional[str]:
        """Get the current tab URL from the given browser."""
        if browser_name_lower in APPLESCRIPT_CHROME_BROWSERS:
            return self._get_url_applescript_chrome(browser_name_lower)
        elif browser_name_lower in APPLESCRIPT_SAFARI_BROWSERS:
            return self._get_url_applescript_safari()
        elif browser_name_lower == "firefox" and self._ax_available:
            return self._get_url_accessibility_firefox()
        return None

    def _get_url_applescript_chrome(self, browser_name_lower: str) -> Optional[str]:
        """Get URL from a Chrome-family browser via AppleScript."""
        # AppleScript needs the proper application name (title case)
        app_name = self._applescript_app_name(browser_name_lower)
        script = (
            f'tell application "{app_name}"\n'
            f'  if (count of windows) > 0 then\n'
            f'    return URL of active tab of front window\n'
            f'  end if\n'
            f'end tell'
        )
        return self._run_applescript(script)

    def _get_url_applescript_safari(self) -> Optional[str]:
        """Get URL from Safari via AppleScript."""
        script = (
            'tell application "Safari"\n'
            '  if (count of documents) > 0 then\n'
            '    return URL of front document\n'
            '  end if\n'
            'end tell'
        )
        return self._run_applescript(script)

    def _get_url_accessibility_firefox(self) -> Optional[str]:
        """Get URL from Firefox using the macOS Accessibility API."""
        try:
            from ApplicationServices import (
                AXUIElementCreateApplication,
                AXUIElementCopyAttributeValue,
                kAXErrorSuccess,
            )
            import AppKit

            # Find Firefox PID
            apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(
                "org.mozilla.firefox"
            )
            if not apps or apps.count() == 0:
                return None

            pid = apps[0].processIdentifier()
            app_ref = AXUIElementCreateApplication(pid)

            # Get focused window
            err, window = AXUIElementCopyAttributeValue(app_ref, "AXFocusedWindow", None)
            if err != kAXErrorSuccess or window is None:
                return None

            # Search for the URL bar (AXComboBox or AXTextField with address-like description)
            return self._find_url_in_ax_tree(window, depth=0)

        except Exception:
            return None

    def _find_url_in_ax_tree(self, element, depth: int = 0, max_depth: int = 8) -> Optional[str]:
        """Recursively search AX tree for the browser address bar."""
        if depth > max_depth:
            return None

        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXErrorSuccess,
            )

            def ax_get(el, attr):
                err, val = AXUIElementCopyAttributeValue(el, attr, None)
                return val if err == kAXErrorSuccess else None

            role = ax_get(element, "AXRole")
            desc = (ax_get(element, "AXDescription") or "").lower()
            role_desc = (ax_get(element, "AXRoleDescription") or "").lower()

            # Firefox: AXComboBox or AXTextField with "address" or "location" in description
            if role in ("AXComboBox", "AXTextField"):
                if any(kw in desc or kw in role_desc for kw in ("address", "location", "url")):
                    value = ax_get(element, "AXValue")
                    if value and isinstance(value, str):
                        return value

            # Recurse into children
            children = ax_get(element, "AXChildren")
            if children:
                for child in children:
                    result = self._find_url_in_ax_tree(child, depth + 1, max_depth)
                    if result:
                        return result

        except Exception:
            pass

        return None

    def _check_and_enforce_block(self, browser_name_lower: str, domain: str) -> None:
        """If the domain is blocked, redirect the tab."""
        blocked = set()
        if self.get_blocked_sites:
            blocked |= self.get_blocked_sites()
        if self.get_always_blocked_sites:
            blocked |= self.get_always_blocked_sites()

        if domain in blocked:
            self._redirect_tab(browser_name_lower, domain)

    def _redirect_tab(self, browser_name_lower: str, blocked_domain: str) -> bool:
        """Redirect the active tab to the blocked page via AppleScript."""
        # Build target URL
        if self.blocked_page_path:
            target = f"file://{self.blocked_page_path}?domain={blocked_domain}"
        else:
            target = "about:blank"

        # Firefox: no AppleScript redirect support
        if browser_name_lower == "firefox":
            return False

        app_name = self._applescript_app_name(browser_name_lower)

        if browser_name_lower in APPLESCRIPT_CHROME_BROWSERS:
            script = (
                f'tell application "{app_name}"\n'
                f'  if (count of windows) > 0 then\n'
                f'    set URL of active tab of front window to "{target}"\n'
                f'  end if\n'
                f'end tell'
            )
        elif browser_name_lower in APPLESCRIPT_SAFARI_BROWSERS:
            script = (
                f'tell application "Safari"\n'
                f'  if (count of documents) > 0 then\n'
                f'    set URL of document 1 to "{target}"\n'
                f'  end if\n'
                f'end tell'
            )
        else:
            return False

        result = self._run_applescript(script)
        if result is not None:
            print(f"[BrowserTracker] Blocked {blocked_domain} in {app_name}")
            return True
        return False

    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        """Extract domain from a URL string."""
        if not url:
            return None
        try:
            # Handle URLs that may not have a scheme
            if not url.startswith(('http://', 'https://', 'file://')):
                url = 'https://' + url
            parsed = urlparse(url)
            domain = parsed.hostname
            if domain:
                # Strip www. prefix
                if domain.startswith('www.'):
                    domain = domain[4:]
                return domain.lower()
        except Exception:
            pass
        return None

    @staticmethod
    def _applescript_app_name(browser_name_lower: str) -> str:
        """Convert lowercase browser name to proper AppleScript application name."""
        names = {
            "google chrome": "Google Chrome",
            "brave browser": "Brave Browser",
            "microsoft edge": "Microsoft Edge",
            "vivaldi": "Vivaldi",
            "chromium": "Chromium",
            "arc": "Arc",
            "safari": "Safari",
        }
        return names.get(browser_name_lower, browser_name_lower.title())

    @staticmethod
    def _run_applescript(script: str) -> Optional[str]:
        """Run an AppleScript and return stdout, or None on failure."""
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, Exception):
            pass
        return None
```

**Step 2: Verify import works**

Run: `cd /Users/mason/Documents/GitHub/productivity/productivity-mac && python -c "from src.core.browser_tracker import BrowserTracker; bt = BrowserTracker(); print('BrowserTracker created OK')"`
Expected: `BrowserTracker created OK`

**Step 3: Verify domain extraction works**

Run: `python -c "from src.core.browser_tracker import BrowserTracker; print(BrowserTracker._extract_domain('https://www.reddit.com/r/python')); print(BrowserTracker._extract_domain('github.com/user/repo'))"`
Expected:
```
reddit.com
github.com
```

**Step 4: Commit**

```bash
git add src/core/browser_tracker.py
git commit -m "feat: add BrowserTracker with AppleScript and AX API URL detection"
```

---

### Task 3: Integrate BrowserTracker into UsageTracker

**Files:**
- Modify: `src/core/usage_tracker.py`

**Step 1: Add browser_tracker parameter to UsageTracker.__init__**

Add an optional `browser_tracker` parameter:

```python
# In __init__ signature, add after root=None:
from src.core.browser_tracker import BrowserTracker
# ...
def __init__(
    self,
    on_usage_tick=None,
    afk_check=None,
    root=None,
    browser_tracker: Optional['BrowserTracker'] = None,
):
```

And store it:
```python
self.browser_tracker = browser_tracker
```

Note: Use a string forward reference or import inside the method to avoid circular imports. Preferred approach: accept `Optional[object]` and rely on duck typing, or import at top of file since `browser_tracker.py` doesn't import `usage_tracker.py`.

**Step 2: Call browser_tracker.on_tick() in _tick()**

After the existing `on_usage_tick` call, add the browser tracker call:

```python
def _tick(self) -> None:
    if not self._running:
        return
    try:
        if not (self.afk_check and self.afk_check()):
            app_name = self.get_foreground_app()
            if app_name and self.on_usage_tick:
                self.on_usage_tick(app_name, 'app', USAGE_TRACKING_INTERVAL)
                self._current_app = app_name

            # Native browser tracking fallback
            if app_name and self.browser_tracker:
                self.browser_tracker.on_tick(app_name, USAGE_TRACKING_INTERVAL)

    except Exception as e:
        print(f"Usage tracker error: {e}")

    if self._running and self._root:
        self._after_id = self._root.after(
            USAGE_TRACKING_INTERVAL * 1000, self._tick
        )
```

**Step 3: Verify import chain works**

Run: `python -c "from src.core.usage_tracker import UsageTracker; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/core/usage_tracker.py
git commit -m "feat: integrate BrowserTracker into UsageTracker tick loop"
```

---

### Task 4: Wire everything up in app.py

**Files:**
- Modify: `src/app.py`

**Step 1: Add BrowserTracker import**

At the top of `app.py`, add:

```python
from src.core.browser_tracker import BrowserTracker
```

**Step 2: Create BrowserTracker in _init_usage_tracking()**

In `_init_usage_tracking()`, after creating `UsageTracker` and before `self.usage_tracker.start()`, create the `BrowserTracker` and pass it in:

```python
def _init_usage_tracking(self) -> None:
    """Initialize usage tracking for apps and websites."""
    import atexit

    self.usage_data = UsageData.load()

    # Resolve blocked page path for native browser blocking
    import os
    blocked_html = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'browser_extension', 'blocked.html'
    )

    # Native browser tracker (fallback when extension is absent)
    self.browser_tracker = BrowserTracker(
        on_website_usage=self._on_website_usage,
        is_extension_connected=self.extension_server.is_extension_connected,
        is_blocking=lambda: self._is_blocking,
        get_blocked_sites=lambda: ExtensionRequestHandler.blocked_sites,
        get_always_blocked_sites=lambda: ExtensionRequestHandler.always_blocked_sites,
        blocked_page_path=blocked_html,
    )

    # Initialize app tracker with AFK integration (polls on main thread)
    self.usage_tracker = UsageTracker(
        on_usage_tick=self._on_usage_tick,
        afk_check=self.afk_detector.is_afk,
        root=self.root,
        browser_tracker=self.browser_tracker,
    )
    self.usage_tracker.start()

    # Set up extension server callback for website tracking
    self.extension_server.set_usage_callback(self._on_website_usage)

    atexit.register(self._save_usage_data_sync)
```

**Step 3: Verify the app starts without errors**

Run: `cd /Users/mason/Documents/GitHub/productivity/productivity-mac && python -c "from src.app import ProductivityApp; print('Import OK')"`
Expected: `Import OK` (just testing the import chain, not actually running the app)

**Step 4: Commit**

```bash
git add src/app.py
git commit -m "feat: wire BrowserTracker into app with blocking and usage callbacks"
```

---

### Task 5: Manual integration test

**Step 1: Start the app and verify browser tracking works**

Run the app normally. Open a browser (Chrome or Safari). Visit a few websites. Check the console output for lines like:
```
Website usage: github.com - 5s
```

These should appear every 5 seconds while a browser is in focus and no extension is connected.

**Step 2: Verify extension deference**

Install/enable the browser extension. Verify that the native tracker stops reporting (console logs from `[EXTENSION]` prefix instead of `Website usage:` from the native path). Wait 10+ seconds after extension pings stop, verify native tracker resumes.

**Step 3: Verify blocking enforcement**

Start a work session. Navigate to a blocked site in Chrome. Verify the tab redirects to the blocked page within 5 seconds.

**Step 4: Verify Firefox URL detection (if Firefox installed)**

Open Firefox, navigate to a site. Check console output for domain tracking. Note: redirect blocking will not work for Firefox (expected — relies on /etc/hosts only).

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues found during integration testing"
```

---

## Summary of all changes

| File | Action | Purpose |
|------|--------|---------|
| `src/core/browser_tracker.py` | Create | AppleScript + AX API URL detection, domain extraction, tab redirect |
| `src/core/extension_server.py` | Modify | Add `last_extension_ping` timestamp, `is_extension_connected()` method |
| `src/core/usage_tracker.py` | Modify | Accept `browser_tracker` param, call `on_tick()` in polling loop |
| `src/app.py` | Modify | Instantiate `BrowserTracker`, wire callbacks and blocking state |
