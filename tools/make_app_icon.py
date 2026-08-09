"""Builds the app icon and the tray glyphs from the logo drawn by Codex.

The logo arrives as a square image with no transparency. Here the tile is cut out
along its edge, the corners are rounded into the alpha, and a multi-size .ico is
assembled. The tray glyph is made separately from the black-and-white variant of
the logo: the tray needs a single-colour silhouette, not a shrunken copy of the
3D render.

THIS IS THE OLD LOGO. The current one is built by `tools/export_logo_variants.py`
and placed into `assets/icon_concepts/`. A run without `--force` now overwrites
nothing: this script once wiped the working icon already, and the project has no
change history to get it back from.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

CODEX = Path("C:/Users/user/.codex/generated_images/019f331d-0a68-77f3-b68e-613e204510e0")
LOGO_TILE = "exec-edb95e33-a52a-44be-a7f3-e47f63312921.png"   # finished tile
LOGO_FLAT = "exec-5faf79e1-bd5c-471f-940c-ae220f95b7c8.png"   # flat black-and-white

OUT = Path(__file__).resolve().parents[1] / "src" / "mas" / "ui" / "icons"
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
DARK_GLYPH = (27, 30, 35, 255)
LIGHT_GLYPH = (255, 255, 255, 255)


def tile_bounds(img: Image.Image) -> tuple[int, int, int, int]:
    """The tile is lighter than the background around it — that finds its edge."""
    g = img.convert("L")
    bg = g.getpixel((2, 2))
    w, h = g.size
    px = g.load()
    thr = bg + 6

    def scan(rng, fixed, horizontal):
        for i in rng:
            v = px[i, fixed] if horizontal else px[fixed, i]
            if v > thr:
                return i
        return 0

    cy, cx = h // 2, w // 2
    left = scan(range(w), cy, True)
    right = scan(range(w - 1, -1, -1), cy, True)
    top = scan(range(h), cx, False)
    bottom = scan(range(h - 1, -1, -1), cx, False)

    # The tile is square. The vertical scan catches the shadow under the speaker,
    # so we take the side horizontally and build a square from the tile centre.
    side = right + 1 - left
    ccx, ccy = (left + right + 1) // 2, (top + bottom + 1) // 2
    half = side // 2
    ccy = max(half, min(h - half, ccy))
    return ccx - half, ccy - half, ccx + half, ccy + half


def rounded_alpha(size: int, radius_ratio: float = 0.225) -> Image.Image:
    """Draw the rounding oversized and shrink it — otherwise the edge is ragged."""
    ss = 8
    m = Image.new("L", (size * ss, size * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [0, 0, size * ss - 1, size * ss - 1],
        radius=int(size * ss * radius_ratio), fill=255)
    return m.resize((size, size), Image.LANCZOS)


SMALL = 24          # up to this size we draw a simplified glyph
TILE_BG = (34, 35, 38)
CONE = (242, 106, 33)
CENTER = (30, 31, 34)


def small_icon(size: int) -> Image.Image:
    """Small sizes are drawn separately instead of scaled down from a large one.

    The 3D render shrunk to 16 px turns into a dirty blob: the bevel, the
    highlights and the thin ring take up less than a pixel. Only what stays
    readable is left here — the orange cone, a dark centre and one ring.
    """
    ss = 16
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.225), fill=TILE_BG + (255,))

    # At small sizes we do not draw the ring at all: it is either thinner than a
    # pixel or it runs past the tile and gets clipped by the rounding, leaving
    # "ears" at the sides. The speaker is left — that is the recognisable shape.
    pad = S * 0.19
    d.ellipse([pad, pad, S - pad, S - pad], fill=CONE + (255,))
    r = S * 0.135
    c = S / 2
    d.ellipse([c - r, c - r, c + r, c + r], fill=CENTER + (255,))

    out = img.resize((size, size), Image.LANCZOS)
    out.putalpha(rounded_alpha(size))
    return out


def build_app_icon() -> list[Image.Image]:
    src = Image.open(CODEX / LOGO_TILE).convert("RGB")
    box = tile_bounds(src)
    tile = src.crop(box)
    print(f"  tile cut out: {box} -> {tile.size}")

    frames = []
    for s in ICO_SIZES:
        if s <= SMALL:
            frames.append(small_icon(s))
            continue
        img = tile.resize((s, s), Image.LANCZOS).convert("RGBA")
        img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=3))
        img.putalpha(rounded_alpha(s))
        frames.append(img)
    return frames


def build_tray_glyphs() -> int:
    """Tray silhouette from the flat black-and-white logo."""
    src = Image.open(CODEX / LOGO_FLAT).convert("L")
    mask = src.point(lambda v: 255 if v < 128 else 0)     # black -> opaque
    bbox = mask.getbbox()
    mask = mask.crop(bbox)

    n = 0
    (OUT / "app").mkdir(parents=True, exist_ok=True)
    for size in (16, 32):
        side = int(size * 0.94)
        m = mask.resize((side, side), Image.LANCZOS)
        # Threshold after shrinking: midtones turn into mud in the tray.
        m = m.point(lambda v: 255 if v > (96 if size == 16 else 80) else 0)
        for theme, color in (("light", DARK_GLYPH), ("dark", LIGHT_GLYPH)):
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            layer = Image.new("RGBA", (side, side), color)
            layer.putalpha(m)
            img.alpha_composite(layer, ((size - side) // 2, (size - side) // 2))
            img.save(OUT / "app" / f"tray_{theme}_{size}.png")
            n += 1
    return n


def main() -> int:
    if (OUT / "app" / "icon.ico").is_file() and "--force" not in sys.argv:
        print("icon already built from the new logo — overwrite only with --force")
        return 1
    if not (CODEX / LOGO_TILE).is_file():
        print(f"no logo file: {CODEX / LOGO_TILE}")
        return 1

    (OUT / "app").mkdir(parents=True, exist_ok=True)
    frames = build_app_icon()
    # The base frame for the .ico must be the LARGEST one, otherwise Pillow
    # squeezes every size down to the base — the file ends up with one 16×16.
    frames = sorted(frames, key=lambda f: -f.width)
    frames[0].save(OUT / "app" / "icon.ico", format="ICO",
                   sizes=[(f.width, f.height) for f in frames],
                   append_images=frames[1:])
    Image.open(CODEX / LOGO_TILE).convert("RGB").resize((512, 512), Image.LANCZOS) \
        .convert("RGBA").save(OUT / "app" / "icon_512.png")
    n = build_tray_glyphs()
    print(f"  icon.ico: {len(frames)} sizes; tray glyphs: {n}")
    print(f"  folder: {OUT / 'app'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
