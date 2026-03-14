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

# All browsers we can get URLs from
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

        # Not a supported browser — flush any tracked domain and return
        if name_lower not in SUPPORTED_BROWSERS:
            self._flush_domain(interval_seconds)
            self._current_domain = None
            self._current_browser = None
            return

        # Extension is handling it — flush any tracked time and defer
        if self.is_extension_connected and self.is_extension_connected():
            self._flush_domain(interval_seconds)
            self._current_domain = None
            self._current_browser = None
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
            else:
                # Same domain — report this tick's time
                self._flush_domain(interval_seconds)

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

            apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(
                "org.mozilla.firefox"
            )
            if not apps or apps.count() == 0:
                return None

            pid = apps[0].processIdentifier()
            app_ref = AXUIElementCreateApplication(pid)

            err, window = AXUIElementCopyAttributeValue(app_ref, "AXFocusedWindow", None)
            if err != kAXErrorSuccess or window is None:
                return None

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

            if role in ("AXComboBox", "AXTextField"):
                if any(kw in desc or kw in role_desc for kw in ("address", "location", "url")):
                    value = ax_get(element, "AXValue")
                    if value and isinstance(value, str):
                        return value

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
        """If the domain (or a parent domain) is blocked, redirect the tab."""
        blocked = set()
        if self.get_blocked_sites:
            blocked |= self.get_blocked_sites()
        if self.get_always_blocked_sites:
            blocked |= self.get_always_blocked_sites()

        if self._is_domain_blocked(domain, blocked):
            self._redirect_tab(browser_name_lower, domain)

    @staticmethod
    def _is_domain_blocked(domain: str, blocked: set) -> bool:
        """Check if domain or any parent domain is in the blocked set."""
        if domain in blocked:
            return True
        for blocked_domain in blocked:
            if domain.endswith('.' + blocked_domain):
                return True
        return False

    @staticmethod
    def _applescript_escape(s: str) -> str:
        """Escape a string for safe interpolation into AppleScript."""
        return s.replace('\\', '\\\\').replace('"', '\\"')

    def _redirect_tab(self, browser_name_lower: str, blocked_domain: str) -> bool:
        """Redirect the active tab to the blocked page via AppleScript."""
        safe_domain = self._applescript_escape(blocked_domain)
        if self.blocked_page_path:
            safe_path = self._applescript_escape(self.blocked_page_path)
            target = f"file://{safe_path}?url={safe_domain}"
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

        if self._run_applescript_command(script):
            print(f"[BrowserTracker] Blocked {blocked_domain} in {app_name}")
            return True
        return False

    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        """Extract domain from a URL string."""
        if not url:
            return None
        try:
            # Ignore internal browser pages (about:blank, chrome://, etc.)
            if url.startswith(('about:', 'chrome://', 'edge://', 'brave://', 'vivaldi://')):
                return None
            if not url.startswith(('http://', 'https://', 'file://')):
                url = 'https://' + url
            parsed = urlparse(url)
            domain = parsed.hostname
            if domain:
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
        """Run an AppleScript and return stdout, or None on failure/empty output."""
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

    @staticmethod
    def _run_applescript_command(script: str) -> bool:
        """Run an AppleScript command that produces no output. Returns True on success."""
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=3,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False
