"""Light version of the silhouettes from the dark one: a recolour, not a redraw.

The silhouette is single-colour, so the variant for a light taskbar is the same
drawing in another colour. Asking the artist for both sets would double the file
count and create a chance for the versions to drift apart in shape.

Takes every `*_dark_*.png` in the device icon folder and makes `*_light_*.png`
next to it.

    python tools/make_icon_variants.py
"""
import sys
from pathlib import Path

from PIL import Image

DEVICES = Path(__file__).resolve().parents[1] / "src" / "mas" / "ui" / "icons" / "devices"
LIGHT_INK = (27, 30, 35)        # silhouette for a light taskbar


def main() -> int:
    made = 0
    for src in sorted(DEVICES.glob("*_dark_*.png")):
        with Image.open(src) as raw:
            img = raw.convert("RGBA")
        # We change the colour only and leave transparency as it is — the edge
        # antialiasing rests on it, and it must not be touched.
        ink = Image.new("RGBA", img.size, LIGHT_INK + (255,))
        ink.putalpha(img.getchannel("A"))
        ink.save(DEVICES / src.name.replace("_dark_", "_light_"))
        made += 1
    print(f"recoloured: {made} files in {DEVICES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
