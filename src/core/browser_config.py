"""
Browser configuration module.
Disables DNS-over-HTTPS in Firefox-based browsers so hosts file blocking works.
"""

import os
import glob
from pathlib import Path
from typing import List, Tuple, Optional


# Firefox-based browsers and their profile locations
FIREFOX_BASED_BROWSERS = {
    "zen": [
        Path(os.environ.get("APPDATA", "")) / "zen" / "Profiles",
        Path(os.environ.get("APPDATA", "")) / "Zen Browser" / "Profiles",
        Path(os.environ.get("LOCALAPPDATA", "")) / "zen" / "Profiles",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Zen Browser" / "Profiles",
    ],
    "firefox": [
        Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox" / "Profiles",
    ],
    "librewolf": [
        Path(os.environ.get("APPDATA", "")) / "librewolf" / "Profiles",
        Path(os.environ.get("APPDATA", "")) / "LibreWolf" / "Profiles",
    ],
    "waterfox": [
        Path(os.environ.get("APPDATA", "")) / "Waterfox" / "Profiles",
    ],
    "floorp": [
        Path(os.environ.get("APPDATA", "")) / "Floorp" / "Profiles",
    ],
}

# user.js content to disable DoH and enforce hosts file
USER_JS_CONTENT = '''// Productivity Timer - Website Blocking Configuration
// This file disables DNS-over-HTTPS so the hosts file can block websites
// DO NOT MODIFY - This file is managed by Productivity Timer

// Disable DNS-over-HTTPS (Trusted Recursive Resolver)
user_pref("network.trr.mode", 5);  // 5 = Off (disable DoH completely)
user_pref("network.trr.uri", "");
user_pref("network.trr.bootstrapAddr", "");

// Disable DNS prefetching (can bypass hosts)
user_pref("network.dns.disablePrefetch", true);
user_pref("network.prefetch-next", false);

// Disable speculative connections
user_pref("network.http.speculative-parallel-limit", 0);

// Force DNS through system (uses hosts file)
user_pref("network.proxy.socks_remote_dns", false);

// Marker to identify our configuration
user_pref("productivity.timer.managed", true);
'''

USER_JS_MARKER = "productivity.timer.managed"


class BrowserConfig:
    """
    Configures Firefox-based browsers to respect the hosts file.
    """

    def __init__(self):
        self._configured_profiles: List[Path] = []
        self._errors: List[str] = []

    def find_browser_profiles(self) -> List[Tuple[str, Path]]:
        """
        Find all Firefox-based browser profile directories.

        Returns:
            List of (browser_name, profile_path) tuples
        """
        profiles = []

        for browser, possible_paths in FIREFOX_BASED_BROWSERS.items():
            for base_path in possible_paths:
                if base_path.exists():
                    # Find all profile folders (they usually have random names)
                    for profile_dir in base_path.iterdir():
                        if profile_dir.is_dir():
                            profiles.append((browser, profile_dir))

        return profiles

    def disable_doh_all_browsers(self) -> Tuple[int, List[str]]:
        """
        Disable DoH in all found Firefox-based browsers.

        Returns:
            Tuple of (success_count, list of errors)
        """
        profiles = self.find_browser_profiles()
        success_count = 0
        errors = []

        for browser, profile_path in profiles:
            success, error = self._configure_profile(browser, profile_path)
            if success:
                success_count += 1
                self._configured_profiles.append(profile_path)
            else:
                errors.append(f"{browser} ({profile_path.name}): {error}")

        self._errors = errors
        return success_count, errors

    def _configure_profile(self, browser: str, profile_path: Path) -> Tuple[bool, str]:
        """
        Configure a single browser profile to disable DoH.

        Args:
            browser: Browser name
            profile_path: Path to profile directory

        Returns:
            Tuple of (success, error_message)
        """
        user_js_path = profile_path / "user.js"

        try:
            # Check if already configured
            if user_js_path.exists():
                content = user_js_path.read_text(encoding='utf-8')
                if USER_JS_MARKER in content:
                    # Already configured, update it
                    pass
                else:
                    # Has existing user.js, append our config
                    content = content.rstrip() + "\n\n" + USER_JS_CONTENT
                    user_js_path.write_text(content, encoding='utf-8')
                    return True, ""

            # Create new user.js
            user_js_path.write_text(USER_JS_CONTENT, encoding='utf-8')
            return True, ""

        except PermissionError:
            return False, "Permission denied"
        except Exception as e:
            return False, str(e)

    def restore_all_browsers(self) -> Tuple[int, List[str]]:
        """
        Remove our DoH configuration from all browsers.

        Returns:
            Tuple of (success_count, list of errors)
        """
        profiles = self.find_browser_profiles()
        success_count = 0
        errors = []

        for browser, profile_path in profiles:
            success, error = self._restore_profile(profile_path)
            if success:
                success_count += 1
            elif error:  # Only add if there was an actual error
                errors.append(f"{browser} ({profile_path.name}): {error}")

        return success_count, errors

    def _restore_profile(self, profile_path: Path) -> Tuple[bool, str]:
        """
        Remove our configuration from a browser profile.

        Args:
            profile_path: Path to profile directory

        Returns:
            Tuple of (success, error_message)
        """
        user_js_path = profile_path / "user.js"

        try:
            if not user_js_path.exists():
                return True, ""

            content = user_js_path.read_text(encoding='utf-8')

            if USER_JS_MARKER not in content:
                # Not our config
                return True, ""

            # Remove our configuration block
            lines = content.split('\n')
            new_lines = []
            skip_until_empty = False
            in_our_block = False

            for line in lines:
                if "Productivity Timer" in line:
                    in_our_block = True
                    continue
                if in_our_block:
                    if line.strip() == "" or not line.startswith("user_pref"):
                        in_our_block = False
                        if line.strip():
                            new_lines.append(line)
                    continue
                if USER_JS_MARKER in line:
                    continue
                new_lines.append(line)

            new_content = '\n'.join(new_lines).strip()

            if new_content:
                user_js_path.write_text(new_content + '\n', encoding='utf-8')
            else:
                # File is empty, delete it
                user_js_path.unlink()

            return True, ""

        except PermissionError:
            return False, "Permission denied"
        except Exception as e:
            return False, str(e)

    def get_status(self) -> dict:
        """
        Get status of browser configurations.

        Returns:
            Dictionary with browser status information
        """
        profiles = self.find_browser_profiles()
        status = {
            "found_browsers": [],
            "configured_browsers": [],
            "unconfigured_browsers": [],
        }

        for browser, profile_path in profiles:
            browser_info = f"{browser} ({profile_path.name})"
            status["found_browsers"].append(browser_info)

            user_js_path = profile_path / "user.js"
            if user_js_path.exists():
                try:
                    content = user_js_path.read_text(encoding='utf-8')
                    if USER_JS_MARKER in content:
                        status["configured_browsers"].append(browser_info)
                    else:
                        status["unconfigured_browsers"].append(browser_info)
                except:
                    status["unconfigured_browsers"].append(browser_info)
            else:
                status["unconfigured_browsers"].append(browser_info)

        return status


def disable_doh_in_browsers() -> Tuple[bool, str]:
    """
    Convenience function to disable DoH in all browsers.

    Returns:
        Tuple of (any_success, status_message)
    """
    config = BrowserConfig()
    count, errors = config.disable_doh_all_browsers()

    if count > 0:
        msg = f"Configured {count} browser profile(s) to use hosts file blocking."
        if errors:
            msg += f" {len(errors)} error(s) occurred."
        return True, msg
    elif errors:
        return False, f"Failed to configure browsers: {'; '.join(errors)}"
    else:
        return False, "No Firefox-based browsers found."


def restore_browser_settings() -> Tuple[bool, str]:
    """
    Convenience function to restore browser settings.

    Returns:
        Tuple of (any_success, status_message)
    """
    config = BrowserConfig()
    count, errors = config.restore_all_browsers()

    if count > 0:
        return True, f"Restored {count} browser profile(s)."
    elif errors:
        return False, f"Errors: {'; '.join(errors)}"
    else:
        return True, "No browsers needed restoration."
