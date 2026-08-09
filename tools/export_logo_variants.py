"""Export the selected Saturn-speaker logo in project-ready variants."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance


ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "assets" / "icon_concepts" / "selected_variant_04" / "export"
MASTER = EXPORT / "masters" / "selected_04_full_color_source.png"

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

GRAPHITE = (27, 30, 35, 255)
WHITE = (247, 247, 245, 255)
ORANGE = (242, 106, 33, 255)
BLUE = (78, 168, 255, 255)
CREAM = (248, 246, 240, 255)

MONO = {
    "graphite": GRAPHITE,
    "white": WHITE,
    "orange": ORANGE,
    "blue": BLUE,
}

TILES = {
    "light": (CREAM, "original"),
    "dark": (GRAPHITE, "white"),
    "orange": (ORANGE, "white"),
    "blue": (BLUE, "white"),
    "dark_orange": (GRAPHITE, "orange"),
}


def ink_mask(image: Image.Image) -> Image.Image:
    """Keep dark logo ink; make warm-white fills and holes transparent."""
    rgba = image.convert("RGBA")
    lum = rgba.convert("L")
    alpha = rgba.getchannel("A")
    strength = bytearray(
        lum.point(lambda value: max(0, min(255, round((225 - value) * 255 / 185)))).tobytes()
    )
    for index, (red, green, blue, _) in enumerate(rgba.getdata()):
        if green > 120 and green > red * 1.4 and green > blue * 1.4:
            strength[index] = 0
    return Image.frombytes(
        "L",
        rgba.size,
        bytes(a * s // 255 for a, s in zip(alpha.tobytes(), strength)),
    )


def recolor(mask: Image.Image, color: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGBA", mask.size, color)
    image.putalpha(mask)
    return image


def normalized(image: Image.Image, coverage: float = 0.90) -> Image.Image:
    alpha = image.getchannel("A")
    box = alpha.getbbox()
    if not box:
        raise ValueError("Logo master has an empty alpha channel")
    cropped = image.crop(box)
    side = 1024
    max_w = round(side * coverage)
    max_h = round(side * coverage)
    scale = min(max_w / cropped.width, max_h / cropped.height)
    size = (round(cropped.width * scale), round(cropped.height * scale))
    cropped = cropped.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(cropped, ((side - size[0]) // 2, (side - size[1]) // 2))
    return canvas


def resize_icon(master: Image.Image, size: int) -> Image.Image:
    icon = master.resize((size, size), Image.Resampling.LANCZOS)
    alpha = icon.getchannel("A").point(lambda value: 0 if value < 4 else value)
    icon.putalpha(alpha)
    if size <= 64:
        rgb = ImageEnhance.Sharpness(icon.convert("RGB")).enhance(1.15)
        rgb.putalpha(icon.getchannel("A"))
        icon = rgb
    return icon


def strip_background_pixels(image: Image.Image) -> Image.Image:
    """Remove residual warm-white or chroma-key pixels after resizing."""
    rgba = image.convert("RGBA")
    alpha = bytearray(rgba.getchannel("A").tobytes())
    for index, (red, green, blue) in enumerate(rgba.convert("RGB").getdata()):
        is_light = red > 230 and green > 230 and blue > 230
        is_green_key = green > 120 and green > red * 1.4 and green > blue * 1.4
        if is_light or is_green_key:
            alpha[index] = 0
    rgba.putalpha(Image.frombytes("L", rgba.size, bytes(alpha)))
    return rgba


def rounded_tile(background: tuple[int, int, int, int], foreground: Image.Image) -> Image.Image:
    side = 1024
    scale = 4
    mask = Image.new("L", (side * scale, side * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, side * scale - 1, side * scale - 1),
        radius=round(side * scale * 0.225),
        fill=255,
    )
    mask = mask.resize((side, side), Image.Resampling.LANCZOS)
    tile = Image.new("RGBA", (side, side), background)
    tile.putalpha(mask)
    mark = foreground.resize((880, 880), Image.Resampling.LANCZOS)
    tile.alpha_composite(mark, (72, 72))
    return tile


def save_set(
    folder: Path,
    stem: str,
    master: Image.Image,
    strip_light: bool = False,
) -> list[Image.Image]:
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    for size in SIZES:
        frame = resize_icon(master, size)
        if strip_light:
            frame = strip_background_pixels(frame)
        frame.save(folder / f"{stem}_{size}.png", optimize=True)
        if size in ICO_SIZES:
            frames.append(frame)
    return frames


def save_ico(path: Path, frames: list[Image.Image]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = sorted(frames, key=lambda image: -image.width)
    frames[0].save(
        path,
        format="ICO",
        sizes=[(frame.width, frame.height) for frame in frames],
        append_images=frames[1:],
    )


def checker(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size), (238, 238, 238))
    draw = ImageDraw.Draw(image)
    cell = max(8, size // 16)
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(211, 211, 211))
    return image.convert("RGBA")


def preview_sheet(items: list[tuple[str, Image.Image]], path: Path) -> None:
    cell = 300
    label_h = 42
    cols = 5
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (250, 250, 248))
    draw = ImageDraw.Draw(sheet)
    for index, (label, icon) in enumerate(items):
        x = (index % cols) * cell
        y = (index // cols) * (cell + label_h)
        backdrop = checker(cell)
        sample = icon.resize((250, 250), Image.Resampling.LANCZOS)
        backdrop.alpha_composite(sample, (25, 25))
        sheet.paste(backdrop.convert("RGB"), (x, y))
        draw.text((x + 12, y + cell + 10), label, fill=(27, 30, 35))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)


def size_preview(master: Image.Image, small_master: Image.Image, path: Path) -> None:
    scale = 8
    gap = 48
    cells = []
    for size in SIZES[:-2]:
        source = small_master if size <= 64 else master
        icon = resize_icon(source, size)
        display = icon.resize((size * scale, size * scale), Image.Resampling.NEAREST)
        cells.append((size, display))
    width = sum(display.width for _, display in cells) + gap * (len(cells) + 1)
    height = max(display.height for _, display in cells) + 90
    sheet = Image.new("RGB", (width, height), (247, 247, 245))
    draw = ImageDraw.Draw(sheet)
    x = gap
    baseline = height - 58
    for size, display in cells:
        y = baseline - display.height
        checker_bg = checker(display.width)
        checker_bg.alpha_composite(display)
        sheet.paste(checker_bg.convert("RGB"), (x, y))
        draw.text((x, baseline + 14), f"{size}px", fill=(27, 30, 35))
        x += display.width + gap
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)


def main() -> None:
    source = Image.open(MASTER).convert("RGBA")
    original = normalized(source)
    mask = ink_mask(original)
    original_cutout = original.copy()
    original_cutout.putalpha(mask.point(lambda value: 0 if value < 4 else value))
    mono = {name: recolor(mask, color) for name, color in MONO.items()}

    transparent_masters = {"original": original_cutout, **mono}
    tile_foregrounds = {"original": original, **mono}
    preview_items = []
    for name, image in transparent_masters.items():
        frames = save_set(
            EXPORT / "transparent" / name,
            f"mas_{name}",
            image,
            strip_light=name == "original",
        )
        save_ico(EXPORT / "ico" / f"mas_{name}.ico", frames)
        image.save(EXPORT / "masters" / f"mas_{name}_1024.png", optimize=True)
        preview_items.append((f"transparent / {name}", image))

    original_cutout.save(EXPORT / "masters" / "selected_04_transparent.png", optimize=True)
    original_cutout.save(EXPORT / "masters" / "selected_04_chromakey.png", optimize=True)

    for name, (background, foreground_name) in TILES.items():
        foreground = tile_foregrounds[foreground_name]
        tile = rounded_tile(background, foreground)
        frames = save_set(EXPORT / "tiles" / name, f"mas_tile_{name}", tile)
        save_ico(EXPORT / "ico" / f"mas_tile_{name}.ico", frames)
        tile.save(EXPORT / "masters" / f"mas_tile_{name}_1024.png", optimize=True)
        preview_items.append((f"tile / {name}", tile))

    preview_sheet(preview_items, EXPORT / "previews" / "color_variants.png")
    size_preview(
        original_cutout,
        original_cutout,
        EXPORT / "previews" / "transparent_size_preview.png",
    )
    print(f"Exported {len(preview_items) * len(SIZES)} PNG files")
    print(f"Exported {len(preview_items)} ICO files")
    print(f"Output: {EXPORT}")


if __name__ == "__main__":
    main()
