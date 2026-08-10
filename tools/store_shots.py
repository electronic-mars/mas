"""Store-sized screenshots: the window placed on a wide backdrop.

The Microsoft Store asks for at least 1366x768, and the program's window is a
narrow 440x772 — 880x1544 at the double resolution we shoot at. Uploading that
gets it rejected for width, and stretching it would look terrible.

So the window is laid on a plain backdrop of the right shape, centred, with a
soft shadow. Nothing is invented and nothing is added: it is the real window,
just given room. Store listings that use mocked-up marketing art convert worse
than ones showing the actual program, so there is no reason to draw anything.

    python tools/store_shots.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "screens"
OUT = ROOT / "docs" / "store"

CANVAS = (1920, 1080)
BACK_DARK = (24, 26, 30)
BACK_LIGHT = (233, 231, 227)

# Which shots to offer, in the order the Store shows them. The first one is what
# most people ever look at.
SHOTS = [
    ("01-devices-dark", "dark"),
    ("04-mixer-dark", "dark"),
    ("06-settings-dark", "dark"),
    ("02-devices-light", "light"),
    ("17-about-dark", "dark"),
]


def compose(name: str, theme: str) -> Path:
    window = Image.open(SRC / f"{name}.png").convert("RGBA")
    # Fit the window to the canvas height with a margin, keeping its proportions.
    margin = 60
    scale = (CANVAS[1] - margin * 2) / window.height
    size = (round(window.width * scale), round(window.height * scale))
    window = window.resize(size, Image.LANCZOS)

    canvas = Image.new("RGBA", CANVAS,
                       (*(BACK_DARK if theme == "dark" else BACK_LIGHT), 255))
    x = (CANVAS[0] - window.width) // 2
    y = (CANVAS[1] - window.height) // 2

    # A shadow, so the window sits on the backdrop instead of floating in a void.
    shadow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 150), (x + 6, y + 14, x + window.width + 6, y + window.height + 14))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(28)))
    canvas.alpha_composite(window, (x, y))

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}-store.png"
    canvas.convert("RGB").save(path, optimize=True)
    return path


def main() -> int:
    for name, theme in SHOTS:
        if not (SRC / f"{name}.png").is_file():
            print(f"  {name}: no such screenshot, skipped")
            continue
        path = compose(name, theme)
        with Image.open(path) as image:
            print(f"  {path.name}  {image.width}x{image.height}, "
                  f"{path.stat().st_size // 1024} KB")
    print(f"done, in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
