"""One-time PWA icon and hero image generation script.

Generates the six static image assets required by the PWA manifest and the
login page redesign. Run once, commit the outputs — never run at Docker build
time or at application startup (D-15).

Usage (inside the running container, or locally with Pillow installed):
    python scripts/generate_pwa_icons.py

Source: app/static/img/snobbery-login.jpg
Outputs (app/static/img/):
    icon-192.png          — circular, 192×192 (standard PWA icon)
    icon-512.png          — circular, 512×512 (standard PWA icon)
    icon-512-maskable.png — maskable, 512×512, solid cream-50 background (purpose: maskable)
    apple-touch-icon.png  — circular, 180×180 (iOS home screen)
    logo-badge.png        — circular, 64×64 (in-app nav badge, 2× retina: renders at 32px)
    snobbery-login-hero.jpg — optimised JPEG ≤80KB for the login page hero

Pitfall 8: icon-512-maskable.png MUST have a solid (alpha=255) background in
the corners. Transparent corners fail Chrome's Lighthouse "Maskable icon" audit.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SRC = Path("app/static/img/snobbery-login.jpg")
OUT = Path("app/static/img")


def circular_crop(img: Image.Image, size: int) -> Image.Image:
    """Crop the image to a circle with a transparent background.

    Steps:
    1. Convert to RGBA and resize to (size, size) with LANCZOS resampling.
    2. Create a greyscale mask with a white-filled ellipse.
    3. Composite the resized image onto a transparent canvas using the mask.
    """
    img = img.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(img, mask=mask)
    return result


def maskable_icon(img: Image.Image, size: int) -> Image.Image:
    """Create a maskable icon with the circular image in the safe zone.

    The maskable safe zone is the central 80% of the image (40% radius circle).
    Content outside this zone may be clipped by the OS adaptive shape. We use
    10% padding on each side so the circle fits within the 80% safe zone.

    The background fill is cream-50 (#FAF7F2 = RGB 250, 247, 242) — solid
    and fully opaque (alpha=255). This satisfies the Lighthouse maskable icon
    audit which requires no transparency in the corners (Pitfall 8).
    """
    padding = int(size * 0.1)  # 10% each side → content in center 80%
    inner_size = size - 2 * padding
    circle = circular_crop(img, inner_size)
    # Cream-50 (#FAF7F2) solid background — no transparency in corners.
    result = Image.new("RGBA", (size, size), (250, 247, 242, 255))
    result.paste(circle, (padding, padding), mask=circle.split()[3])
    return result


if __name__ == "__main__":
    src = Image.open(SRC)

    # Standard circular icons.
    circular_crop(src, 192).save(OUT / "icon-192.png")
    print("  icon-192.png")

    circular_crop(src, 512).save(OUT / "icon-512.png")
    print("  icon-512.png")

    # Maskable icon — solid cream-50 background, content in center 80% safe zone.
    maskable_icon(src, 512).save(OUT / "icon-512-maskable.png")
    print("  icon-512-maskable.png")

    # Apple touch icon.
    circular_crop(src, 180).save(OUT / "apple-touch-icon.png")
    print("  apple-touch-icon.png")

    # Logo badge (renders at 32×32 on retina; stored at 64×64).
    circular_crop(src, 64).save(OUT / "logo-badge.png")
    print("  logo-badge.png")

    # Login hero: resize and compress — NOT a circular crop.
    # target ≤80KB at quality=75 + optimize=True.
    hero = src.convert("RGB")
    hero.thumbnail((720, 720), Image.LANCZOS)
    hero.save(OUT / "snobbery-login-hero.jpg", "JPEG", quality=75, optimize=True)
    print("  snobbery-login-hero.jpg")

    print("Icons generated successfully.")
