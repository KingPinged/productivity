"""
Package the browser extension as an .xpi file for permanent installation.
"""

import zipfile
import os
from pathlib import Path

def package_extension():
    """Create an .xpi file from the extension files."""

    extension_dir = Path(__file__).parent
    output_file = extension_dir / "productivity_timer_blocker.xpi"

    # Files to include in the extension
    files_to_include = [
        "manifest.json",
        "background.js",
        "popup.html",
        "popup.js",
        "blocked.html",
        "icons/icon16.png",
        "icons/icon48.png",
        "icons/icon128.png",
        "icons/icon16-active.png",
        "icons/icon48-active.png",
        "icons/icon128-active.png",
    ]

    # Create the .xpi file (which is just a zip file)
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as xpi:
        for file_path in files_to_include:
            full_path = extension_dir / file_path
            if full_path.exists():
                xpi.write(full_path, file_path)
                print(f"  Added: {file_path}")
            else:
                print(f"  Warning: {file_path} not found, skipping")

    print(f"\nExtension packaged: {output_file}")
    print(f"File size: {output_file.stat().st_size / 1024:.1f} KB")

    return output_file


if __name__ == "__main__":
    print("Packaging Productivity Timer Blocker extension...")
    print()

    xpi_path = package_extension()

    print()
    print("=" * 60)
    print("INSTALLATION INSTRUCTIONS FOR ZEN BROWSER")
    print("=" * 60)
    print()
    print("Option 1: Install as unsigned extension (Recommended)")
    print("-" * 60)
    print("1. Open Zen browser")
    print("2. Go to: about:config")
    print("3. Search for: xpinstall.signatures.required")
    print("4. Set it to: false")
    print("5. Go to: about:addons")
    print("6. Click the gear icon > 'Install Add-on From File...'")
    print(f"7. Select: {xpi_path}")
    print()
    print("Option 2: Drag and drop")
    print("-" * 60)
    print("1. First do steps 1-4 from Option 1")
    print(f"2. Drag the .xpi file into your Zen browser window")
    print("3. Click 'Add' when prompted")
    print()
