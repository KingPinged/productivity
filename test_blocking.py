"""
Test script to verify website blocking is working.
Run as Administrator to test hosts file modification.
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.admin import is_admin
from src.utils.constants import HOSTS_PATH
from src.core.website_blocker import WebsiteBlocker


def main():
    print("=" * 60)
    print("Website Blocking Test")
    print("=" * 60)

    # Check admin status
    admin = is_admin()
    print(f"\nRunning as Administrator: {admin}")
    if not admin:
        print("WARNING: Not running as admin. Website blocking will fail!")
        print("Right-click this script and 'Run as administrator'")

    # Check hosts file
    print(f"\nHosts file path: {HOSTS_PATH}")
    print(f"Hosts file exists: {HOSTS_PATH.exists()}")

    if HOSTS_PATH.exists():
        print(f"\nCurrent hosts file content (first 20 lines):")
        print("-" * 40)
        try:
            with open(HOSTS_PATH, 'r') as f:
                lines = f.readlines()[:20]
                for line in lines:
                    print(line.rstrip())
        except Exception as e:
            print(f"Error reading hosts file: {e}")

    # Test blocking
    print("\n" + "=" * 60)
    print("Testing website blocker...")
    print("=" * 60)

    test_sites = {"youtube.com", "reddit.com", "twitter.com"}
    blocker = WebsiteBlocker(test_sites)

    print(f"\nBlocking test sites: {test_sites}")
    success, error = blocker.block()

    if success:
        print("SUCCESS: Websites blocked!")

        # Verify
        is_active, status = blocker.verify_blocking_active()
        print(f"Verification: {status}")

        # Show what was added
        print("\nHosts file now contains:")
        print("-" * 40)
        try:
            with open(HOSTS_PATH, 'r') as f:
                content = f.read()
                # Find our section
                start = content.find("# === PRODUCTIVITY")
                if start != -1:
                    print(content[start:])
        except Exception as e:
            print(f"Error: {e}")

        # Ask to unblock
        print("\n" + "=" * 60)
        input("Press Enter to UNBLOCK and restore hosts file...")

        success, error = blocker.unblock()
        if success:
            print("SUCCESS: Websites unblocked!")
        else:
            print(f"FAILED to unblock: {error}")

    else:
        print(f"FAILED: {error}")
        print("\nMake sure to:")
        print("1. Run this script as Administrator")
        print("2. Check that antivirus isn't blocking hosts file access")
        print("3. Verify the hosts file path is correct")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
