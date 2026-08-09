"""One-off extraction of the icons we need from the Hugeicons package.

The package weighs a hundred-odd megabytes and has no place in the project, while
fifty-odd SVG files do. After this the icon build depends on neither the network
nor npm.

    npm pack @hugeicons/core-free-icons && tar -xzf hugeicons-core-free-icons-*.tgz
    python tools/vendor_icons.py <path to the unpacked package>
"""
import re
import sys
from pathlib import Path

from icon_map import ALL

OUT = Path(__file__).resolve().parents[1] / "assets" / "icons-src"
# The author's stroke of 1.5 is meant for 24 points; the tray needs half that
# size, and there it thins out past recognition. 1.9 — checked at 16 and 20.
STROKE = "1.9"


def to_svg(js: str) -> str:
    parts = []
    for tag, attrs in re.findall(r'\["(\w+)",\s*\{(.+?)\}\]', js, re.S):
        out = []
        for key, val in re.findall(r'(\w+):\s*"([^"]*)"', attrs):
            if key == "key":
                continue
            dashed = re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), key)
            out.append(f'{dashed}="{val}"')
        parts.append(f"<{tag} {' '.join(out)}/>")
    if not parts:
        raise ValueError("the file has no paths at all")
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" '
            f'viewBox="0 0 24 24" fill="none" stroke-width="{STROKE}">'
            + "".join(parts) + "</svg>\n")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    pkg = Path(sys.argv[1]) / "dist" / "cjs"
    if not pkg.is_dir():
        print(f"not found: {pkg}")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    missing = []
    for name, source in sorted(ALL.items()):
        src = pkg / f"{source}Icon.js"
        if not src.is_file():
            missing.append(f"{name} -> {source}")
            continue
        (OUT / f"{name}.svg").write_text(to_svg(src.read_text(encoding="utf-8")),
                                         encoding="utf-8")
    print(f"laid out {len(ALL) - len(missing)} icons into {OUT}")
    if missing:
        print("NOT FOUND:", ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
