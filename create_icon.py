"""
Create application icon for Productivity Timer.
Run this script once to generate the icon file.
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    """Create a simple productivity timer icon."""
    # Create a 256x256 image with transparency
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw background circle (dark theme)
    margin = 10
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill="#2C3E50",  # Dark blue-gray
        outline="#3498DB",  # Blue
        width=8
    )

    # Draw inner circle (timer face)
    inner_margin = 40
    draw.ellipse(
        [inner_margin, inner_margin, size - inner_margin, size - inner_margin],
        fill="#34495E",  # Slightly lighter
        outline="#2C3E50",
        width=4
    )

    # Draw timer hand (pointing up - like at 12 o'clock for focus)
    center = size // 2
    hand_length = 60
    draw.line(
        [center, center, center, center - hand_length],
        fill="#E74C3C",  # Red
        width=8
    )

    # Draw center dot
    dot_radius = 12
    draw.ellipse(
        [center - dot_radius, center - dot_radius,
         center + dot_radius, center + dot_radius],
        fill="#E74C3C"
    )

    # Draw hour markers
    import math
    for i in range(12):
        angle = math.radians(i * 30 - 90)
        outer_r = size // 2 - margin - 10
        inner_r = outer_r - 15

        x1 = center + outer_r * math.cos(angle)
        y1 = center + outer_r * math.sin(angle)
        x2 = center + inner_r * math.cos(angle)
        y2 = center + inner_r * math.sin(angle)

        width = 6 if i % 3 == 0 else 3
        draw.line([x1, y1, x2, y2], fill="#3498DB", width=width)

    # Create assets directory if it doesn't exist
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(assets_dir, exist_ok=True)

    # Save as ICO file with multiple sizes
    icon_path = os.path.join(assets_dir, "icon.ico")

    # Create multiple sizes for ICO
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    for s in sizes:
        resized = image.resize((s, s), Image.Resampling.LANCZOS)
        images.append(resized)

    # Save as ICO
    images[0].save(
        icon_path,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )

    print(f"Icon created at: {icon_path}")

    # Also save as PNG for reference
    png_path = os.path.join(assets_dir, "icon.png")
    image.save(png_path, "PNG")
    print(f"PNG version saved at: {png_path}")


if __name__ == "__main__":
    create_icon()
