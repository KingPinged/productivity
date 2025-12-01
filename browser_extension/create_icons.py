"""
Create icons for the browser extension.
"""

from PIL import Image, ImageDraw
import os

def create_icon(size, color, filename):
    """Create a simple circular icon."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw circle
    margin = size // 8
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
        outline="#ffffff",
        width=max(1, size // 16)
    )

    # Save
    image.save(filename, "PNG")
    print(f"Created {filename}")

# Create icons directory
os.makedirs("icons", exist_ok=True)

# Normal icons (gray)
create_icon(16, "#555555", "icons/icon16.png")
create_icon(48, "#555555", "icons/icon48.png")
create_icon(128, "#555555", "icons/icon128.png")

# Active icons (red)
create_icon(16, "#e74c3c", "icons/icon16-active.png")
create_icon(48, "#e74c3c", "icons/icon48-active.png")
create_icon(128, "#e74c3c", "icons/icon128-active.png")

print("All icons created!")
