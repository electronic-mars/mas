"""Builds every program icon from the sources in assets/icons-src.

We rasterise with a headless browser straight to the size needed: drawing large
and scaling down is not allowed — that is exactly how the previous set turned
into grey mush. The light variant is a recolour of the dark one, their shape is
the same.

    python tools/make_icons.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from icon_map import DEVICES, MARKS, UI

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "icons-src"
DEV_OUT = ROOT / "src" / "mas" / "ui" / "icons" / "devices"
UI_OUT = ROOT / "src" / "mas" / "ui" / "icons" / "ui"
SIZES = (16, 20, 24, 32, 40, 48, 64)
# Stroke width in units of the 24 canvas. The author's 1.9 is meant for large
# display; the smaller the cell, the thicker the stroke has to be, otherwise it
# smears into a semi-transparent haze and the silhouette disappears. The values
# were picked by eye from a check sheet at 16, 20 and 24 points.
STROKE = {16: 2.9, 20: 2.5, 24: 2.2, 32: 2.0, 40: 1.9, 48: 1.9, 64: 1.8}
LIGHT_INK = (27, 30, 35, 255)
WHITE = (255, 255, 255, 255)
EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
COLS = 10


def browser() -> str:
    for path in EDGE:
        if Path(path).is_file():
            return path
    raise SystemExit("Microsoft Edge not found — the icons are rasterised with it")


def render(names: list[str], size: int) -> dict[str, Image.Image]:
    """All icons of one size in a single shot: starting the browser is costly."""
    cell, pad = size + 24, 12
    cells = []
    for name in names:
        svg = (SRC / f"{name}.svg").read_text(encoding="utf-8")
        svg = svg.replace('width="1em" height="1em"', f'width="{size}" height="{size}"')
        svg = re.sub(r'stroke-width="[\d.]+"', f'stroke-width="{STROKE[size]}"', svg)
        cells.append(f"<i>{svg}</i>")
    html = ("<!doctype html><meta charset=utf-8><style>"
            "html,body{margin:0;padding:0;background:#000}"
            f"body{{width:{cell * COLS}px}}"
            f"i{{display:block;float:left;width:{cell}px;height:{cell}px;padding:{pad}px;"
            "box-sizing:border-box;line-height:0;color:#fff}"
            "svg{display:block}</style>" + "".join(cells))
    tmp = Path(tempfile.mkdtemp(prefix="mas-icons-"))
    (tmp / "p.html").write_text(html, encoding="utf-8")
    lines = (len(names) + COLS - 1) // COLS
    # We take the window with slack: the frame of the headless window eats about
    # a hundred points of height, and the bottom grid rows miss the shot entirely.
    subprocess.run([browser(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1",
                    f"--window-size={cell * COLS + 160},{cell * lines + 220}",
                    f"--screenshot={tmp / 's.png'}", f"--user-data-dir={tmp / 'prof'}",
                    "--virtual-time-budget=5000", "--no-first-run", "--disable-extensions",
                    (tmp / "p.html").as_uri()], capture_output=True, timeout=180)
    shot_path = tmp / "s.png"
    if not shot_path.is_file():
        raise SystemExit(f"screenshot failed for size {size}")
    shot = Image.open(shot_path).convert("L")
    need_w, need_h = cell * COLS, cell * lines
    if shot.width < need_w or shot.height < need_h:
        raise SystemExit(f"screenshot clipped: {shot.size}, need {need_w}x{need_h}")
    out = {}
    for i, name in enumerate(names):
        x, y = (i % COLS) * cell + pad, (i // COLS) * cell + pad
        image = Image.new("RGBA", (size, size), WHITE)
        image.putalpha(shot.crop((x, y, x + size, y + size)))
        out[name] = image
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def recolour(image: Image.Image, ink) -> Image.Image:
    out = Image.new("RGBA", image.size, ink)
    out.putalpha(image.getchannel("A"))
    return out


def main() -> int:
    names = sorted({**DEVICES, **MARKS})
    for path in DEV_OUT.glob("*"):
        path.unlink()
    DEV_OUT.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        for name, image in render(names, size).items():
            image.save(DEV_OUT / f"{name}_dark_{size}.png", optimize=True)
            recolour(image, LIGHT_INK).save(DEV_OUT / f"{name}_light_{size}.png",
                                            optimize=True)
        print(f"  {size} px done")
    for name in names:
        shutil.copyfile(SRC / f"{name}.svg", DEV_OUT / f"{name}.svg")

    UI_OUT.mkdir(parents=True, exist_ok=True)
    for path in UI_OUT.glob("*.svg"):
        path.unlink()
    for name in UI:
        shutil.copyfile(SRC / f"{name}.svg", UI_OUT / f"{name}.svg")

    print(f"devices and marks: {len(names)}, sizes: {len(SIZES)}, "
          f"interface icons: {len(UI)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
