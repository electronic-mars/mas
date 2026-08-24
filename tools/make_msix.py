"""Build the Microsoft Store package from what PyInstaller produced.

    python tools/make_msix.py build/mas/MasterAudioSwitcher

The Store signs the package itself after certification, so nothing here needs a
certificate: that is the whole reason the Store build is a package and the
release build is an installer, which would need a paid one.

Identity and Publisher are assigned by Partner Center when the app name is
reserved — Product management → App identity — and a package whose identity does
not match is refused at upload. They are written in below rather than kept
somewhere private: they are printed inside every copy of the published package,
so there is nothing to protect, and a build that needs no setting up is a build
that cannot be run wrong. The environment still overrides them, which is what a
second app or a test identity would use.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mas import __version__  # noqa: E402

# Assigned by Partner Center for this app and never changing.
IDENTITY_NAME = "ElectronicMARS.MasterAudioSwitcher"
PUBLISHER = "CN=952B5818-8749-4493-B354-6D30C3A586B7"
PUBLISHER_DISPLAY = "Electronic MARS"
STORE_ID = "9N9J77WKQ4X6"          # the address the app will live at once live

TEMPLATE = ROOT / "build" / "msix" / "AppxManifest.xml.in"
SOURCE_ICON = ROOT / "src" / "mas" / "ui" / "icons" / "app" / "icon_512.png"
OUT = ROOT / "build" / "msix-out"

# What the Store shows, and where. The scaled copies matter: without them
# Windows stretches one bitmap everywhere and the icon looks soft in the one
# place people see it most, the taskbar.
TILES = {
    "Square44x44Logo.png": 44,
    "Square150x150Logo.png": 150,
    "Wide310x150Logo.png": (310, 150),
    "SmallTile.png": 71,
    "LargeTile.png": 310,
    "StoreLogo.png": 50,
}
SCALES = (100, 125, 150, 200, 400)
# The taskbar and the start list ask for these by name, unplated so the icon
# sits on the taskbar rather than on a coloured square.
TARGET_SIZES = (16, 24, 32, 48, 256)


def sdk_tool(name: str) -> str:
    bins = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    found = sorted(bins.glob(f"*/x64/{name}.exe")) if bins.is_dir() else []
    if not found:
        raise SystemExit(f"{name}.exe not found — install the Windows SDK")
    return str(found[-1])


def draw(image, size, out: Path) -> None:
    from PIL import Image
    if isinstance(size, int):
        size = (size, size)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    # Wide and small tiles are not square: the logo keeps its proportions and
    # sits in the middle rather than being stretched to fill.
    side = min(size)
    logo = image.resize((side, side), Image.LANCZOS)
    canvas.paste(logo, ((size[0] - side) // 2, (size[1] - side) // 2), logo)
    canvas.save(out)


def assets(into: Path) -> None:
    from PIL import Image
    into.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE_ICON) as src:
        src = src.convert("RGBA")
        for name, size in TILES.items():
            stem = name[:-len(".png")]
            for scale in SCALES:
                if isinstance(size, int):
                    scaled = max(1, round(size * scale / 100))
                else:
                    scaled = tuple(max(1, round(v * scale / 100)) for v in size)
                draw(src, scaled, into / f"{stem}.scale-{scale}.png")
            draw(src, size, into / name)
        for px in TARGET_SIZES:
            draw(src, px, into / f"Square44x44Logo.targetsize-{px}.png")
            draw(src, px, into / f"Square44x44Logo.targetsize-{px}_altform-unplated.png")


# The languages the Store listing is written in — not the languages the program
# speaks. Declaring all fifteen here asks Partner Center for fifteen store
# listings, one per language, and the submission stays incomplete until every
# one of them is written. Deleting them on the languages page does not help:
# that list is rebuilt from the package on every visit.
#
# The program is unaffected either way. It picks its language from Windows and
# reads its own files in the package; these declarations are for Windows'
# resource system, which the interface does not use.
#
# Add a tag here when a store listing in that language actually exists.
LISTING_LANGUAGES = ("en-us",)


def languages() -> list[str]:
    return list(LISTING_LANGUAGES)


def setting(name: str, fallback: str) -> str:
    """An override from the environment, but only a real one.

    os.environ.get(name, fallback) hands back the fallback when the variable is
    absent and the empty string when it is present and empty — and a workflow
    that writes an undefined repository variable into the environment produces
    exactly that. It cost a build: the identity went into the manifest empty,
    and makeappx refused a package whose Name violated a minimum length of three.
    """
    return os.environ.get(name) or fallback


def main() -> int:
    payload = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "mas" / "MasterAudioSwitcher"
    if not (payload / "MasterAudioSwitcher.exe").is_file():
        raise SystemExit(f"no program built at {payload}")

    layout = OUT / "layout"
    if layout.exists():
        shutil.rmtree(layout)
    shutil.copytree(payload, layout)
    assets(layout / "Assets")

    resources = "\n".join(f'    <Resource Language="{code}" />' for code in languages())
    manifest = TEMPLATE.read_text(encoding="utf-8")
    for mark, value in (
        ("@IDENTITY_NAME@", setting("MSIX_IDENTITY_NAME", IDENTITY_NAME)),
        ("@PUBLISHER@", setting("MSIX_PUBLISHER", PUBLISHER)),
        ("@PUBLISHER_DISPLAY@", setting("MSIX_PUBLISHER_DISPLAY", PUBLISHER_DISPLAY)),
        # The fourth number belongs to the Store and must be left at zero.
        ("@VERSION@", f"{__version__}.0"),
        ("@RESOURCES@", resources),
    ):
        manifest = manifest.replace(mark, value)
    # Said here rather than by makeappx, which reports it as a schema violation
    # on a line number and leaves you to work out which value went missing.
    for mark in ("@IDENTITY_NAME@", "@PUBLISHER@", "@PUBLISHER_DISPLAY@",
                 "@VERSION@", "@RESOURCES@"):
        if mark in manifest:
            raise SystemExit(f"{mark} was never filled in")
    if '=""' in manifest:
        raise SystemExit("the manifest has an empty attribute — a setting resolved "
                         "to nothing, and makeappx would refuse the package")
    (layout / "AppxManifest.xml").write_text(manifest, encoding="utf-8")

    package = OUT / f"MasterAudioSwitcher-{__version__}.msix"
    package.unlink(missing_ok=True)
    done = subprocess.run([sdk_tool("makeappx"), "pack", "/d", str(layout),
                           "/p", str(package), "/o"], capture_output=True, text=True)
    if done.returncode != 0:
        print(done.stdout[-4000:], done.stderr[-2000:])
        raise SystemExit("makeappx refused the package")
    print(f"{package.name}: {package.stat().st_size / 1024 / 1024:.1f} MB, "
          f"{len(languages())} languages")
    print(f"identity: {setting('MSIX_IDENTITY_NAME', IDENTITY_NAME)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
