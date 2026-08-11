"""Build the Microsoft Store package from what PyInstaller produced.

    python tools/make_msix.py build/mas/MasterAudioSwitcher

The Store signs the package itself after certification, so nothing here needs a
certificate: that is the whole reason the Store build is a package and the
release build is an installer, which would need a paid one.

Identity and Publisher come from Partner Center — Product management → App
identity — through the environment, because a package whose identity does not
match the reserved app is refused at upload. Without them it still builds, with
values good enough to install on this machine for testing and no good at all
for submitting.

    set MSIX_IDENTITY_NAME=12345ElectronicMars.MasterAudioSwitcher
    set MSIX_PUBLISHER=CN=ABCD1234-...
    set MSIX_PUBLISHER_DISPLAY=electronic-mars
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mas import __version__  # noqa: E402

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


# Our own codes are what the interface files are named by. Windows wants proper
# tags, and refuses the package outright over one it does not know — "zh" is not
# a language to it, only "zh-Hans" or "zh-Hant" are. And our Portuguese is the
# Brazilian one, which is a different tag from plain "pt".
AS_WINDOWS_CALLS_IT = {"zh": "zh-Hans", "pt": "pt-BR"}


def languages() -> list[str]:
    """Every language the program is translated into, declared to the Store so
    the listing can be shown in them. Taken from the locale folder, so adding a
    language is still only dropping a file in."""
    import json
    index = ROOT / "src" / "mas" / "ui" / "locales" / "index.json"
    return [AS_WINDOWS_CALLS_IT.get(item["code"], item["code"])
            for item in json.loads(index.read_text(encoding="utf-8"))]


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
        ("@IDENTITY_NAME@", os.environ.get("MSIX_IDENTITY_NAME",
                                           "ElectronicMars.MasterAudioSwitcher")),
        ("@PUBLISHER@", os.environ.get("MSIX_PUBLISHER", "CN=electronic-mars")),
        ("@PUBLISHER_DISPLAY@", os.environ.get("MSIX_PUBLISHER_DISPLAY", "electronic-mars")),
        # The fourth number belongs to the Store and must be left at zero.
        ("@VERSION@", f"{__version__}.0"),
        ("@RESOURCES@", resources),
    ):
        manifest = manifest.replace(mark, value)
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
    if "MSIX_IDENTITY_NAME" not in os.environ:
        print("built with a stand-in identity: good enough to install here for "
              "testing, not good enough to upload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
