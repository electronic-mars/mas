"""Checks over the icon set.

We catch what has already broken before: a missing size, a lost name (and a name
is a key in the device config), the palette drifting out of sync with the files,
an icon of the wrong size in the tray, and semi-transparent mush instead of a
silhouette.
"""
import re
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from icon_map import DEVICES, MARKS, UI  # noqa: E402

ICONS = ROOT / "src" / "mas" / "ui" / "icons" / "devices"
UI_ICONS = ROOT / "src" / "mas" / "ui" / "icons" / "ui"
SRC = ROOT / "assets" / "icons-src"
APP_JS = ROOT / "src" / "mas" / "ui" / "app.js"
SIZES = (16, 20, 24, 32, 40, 48, 64)
NAMES = sorted({**DEVICES, **MARKS})

# Names that made it into device configs over past versions. They are not
# allowed to vanish: a device would silently be left without an icon.
LEGACY = ("speakers", "headphones", "headset", "earbuds", "soundbar", "tv",
          "monitor", "laptop", "hdmi", "usb", "bluetooth", "microphone",
          "sony-xm5", "galaxy-buds", "thinkpad", "alienware-m18-r2",
          "razer-kraken", "powerbeats-pro-2", "hyperx-cloud",
          "edifier-r1700bts", "jbl-charge", "homepod-mini",
          "marshall-emberton-ii", "sonos-era-100")


class IconSet(unittest.TestCase):
    def test_legacy_names_survive(self):
        for name in LEGACY:
            with self.subTest(name=name):
                self.assertIn(name, DEVICES)

    def test_every_size_and_theme_exists(self):
        for name in NAMES:
            for size in SIZES:
                for theme in ("dark", "light"):
                    path = ICONS / f"{name}_{theme}_{size}.png"
                    with self.subTest(name=name, size=size, theme=theme):
                        self.assertTrue(path.is_file(), f"no file {path.name}")
                        with Image.open(path) as image:
                            self.assertEqual(image.size, (size, size))
                            self.assertEqual(image.mode, "RGBA")

    def test_svg_for_window_exists(self):
        for name in NAMES:
            with self.subTest(name=name):
                self.assertTrue((ICONS / f"{name}.svg").is_file())

    def test_no_stray_files(self):
        """The old set is fully deleted, nothing extra is left in the folder."""
        expected = {f"{n}_{t}_{s}.png" for n in NAMES for s in SIZES
                    for t in ("dark", "light")} | {f"{n}.svg" for n in NAMES}
        actual = {p.name for p in ICONS.iterdir()}
        self.assertEqual(actual - expected, set(), "foreign files left behind")

    def test_palette_matches_files(self):
        text = APP_JS.read_text(encoding="utf-8")
        block = re.search(r"const GLYPHS = \[(.+?)\];", text, re.S)
        self.assertIsNotNone(block, "GLYPHS list not found in app.js")
        listed = re.findall(r"'([a-z0-9-]+)'", block.group(1))
        self.assertEqual(sorted(listed), NAMES,
                         "the palette in the window drifted from the file set")

    def test_dark_is_white_and_light_is_ink(self):
        for name in NAMES:
            for theme, want in (("dark", (255, 255, 255)), ("light", (27, 30, 35))):
                path = ICONS / f"{name}_{theme}_24.png"
                with self.subTest(name=name, theme=theme):
                    with Image.open(path) as image:
                        pixels = [p for p in image.convert("RGBA").getdata() if p[3] > 200]
                        self.assertTrue(pixels, f"{path.name} is empty")
                        self.assertEqual(pixels[0][:3], want)

    def test_icon_is_not_a_faint_smudge(self):
        """The silhouette must fill a noticeable part of the cell and have a dense core.

        The previous set failed exactly here: at 20 points what was left was a
        semi-transparent haze that a person could not name.
        """
        for name in NAMES:
            with self.subTest(name=name):
                with Image.open(ICONS / f"{name}_dark_20.png") as image:
                    alpha = list(image.convert("RGBA").getchannel("A").getdata())
                ink = [v for v in alpha if v > 0]
                self.assertGreaterEqual(len(ink) * 100 // 400, 12,
                                        f"{name}: ink covers less than 12% of the cell")
                # The threshold is set well below the measured minimum of the set
                # (42%). The previous set scored 15-23% here — that same haze.
                solid = sum(1 for v in ink if v >= 200)
                self.assertGreaterEqual(solid * 100 // len(ink), 35,
                                        f"{name}: fewer than a third of the dots are dense")

    def test_ui_icons_exist(self):
        for name in UI:
            with self.subTest(name=name):
                self.assertTrue((UI_ICONS / f"{name}.svg").is_file())

    def test_sources_are_vendored(self):
        """The build must not depend on the network or on npm."""
        for name in list(DEVICES) + list(MARKS) + list(UI):
            with self.subTest(name=name):
                self.assertTrue((SRC / f"{name}.svg").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=1)
