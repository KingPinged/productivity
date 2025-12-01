"""
Restore DNS-over-HTTPS in Firefox-based browsers.
This script removes any user.js modifications made by Productivity Timer.

Run this script to re-enable DoH in Zen, Firefox, and other Firefox-based browsers.
"""

import os
from pathlib import Path

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

MARKER = "productivity.timer.managed"


def find_browser_profiles():
    """Find all Firefox-based browser profile directories."""
    profiles = []

    for browser, possible_paths in FIREFOX_BASED_BROWSERS.items():
        for base_path in possible_paths:
            if base_path.exists():
                for profile_dir in base_path.iterdir():
                    if profile_dir.is_dir():
                        profiles.append((browser, profile_dir))

    return profiles


def restore_profile(browser: str, profile_path: Path) -> tuple:
    """
    Remove Productivity Timer configuration from a browser profile.

    Returns:
        Tuple of (was_modified, error_message)
    """
    user_js_path = profile_path / "user.js"

    if not user_js_path.exists():
        return False, None

    try:
        content = user_js_path.read_text(encoding='utf-8')

        if MARKER not in content:
            return False, None

        # Remove our configuration block
        lines = content.split('\n')
        new_lines = []
        in_our_block = False

        for line in lines:
            # Skip our header comments
            if "Productivity Timer" in line:
                in_our_block = True
                continue

            # Skip our user_pref lines
            if in_our_block and line.strip().startswith("user_pref"):
                continue

            # Empty line ends our block
            if in_our_block and not line.strip():
                in_our_block = False
                continue

            # Skip lines with our marker
            if MARKER in line:
                continue

            new_lines.append(line)

        new_content = '\n'.join(new_lines).strip()

        if new_content:
            user_js_path.write_text(new_content + '\n', encoding='utf-8')
            return True, None
        else:
            # File is empty after removing our config, delete it
            user_js_path.unlink()
            return True, None

    except PermissionError:
        return False, "Permission denied"
    except Exception as e:
        return False, str(e)


def main():
    print("=" * 60)
    print("Restore DNS-over-HTTPS (DoH) in Browsers")
    print("=" * 60)
    print()
    print("This will remove any DoH-disabling configuration added by")
    print("Productivity Timer, restoring your browser's default DoH settings.")
    print()

    profiles = find_browser_profiles()

    if not profiles:
        print("No Firefox-based browser profiles found.")
        return

    print(f"Found {len(profiles)} browser profile(s):")
    for browser, path in profiles:
        print(f"  - {browser}: {path.name}")
    print()

    restored_count = 0
    errors = []

    for browser, profile_path in profiles:
        was_modified, error = restore_profile(browser, profile_path)

        if was_modified:
            print(f"[RESTORED] {browser} ({profile_path.name})")
            restored_count += 1
        elif error:
            print(f"[ERROR] {browser} ({profile_path.name}): {error}")
            errors.append(f"{browser}: {error}")

    print()
    print("=" * 60)

    if restored_count > 0:
        print(f"Successfully restored {restored_count} profile(s).")
        print()
        print("IMPORTANT: Restart your browser(s) for changes to take effect!")
        print("DoH will be re-enabled after restart.")
    else:
        print("No profiles needed restoration (no Productivity Timer config found).")

    if errors:
        print()
        print("Errors occurred:")
        for error in errors:
            print(f"  - {error}")

    print("=" * 60)


if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
