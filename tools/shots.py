"""Screenshots of every program screen and notification — into docs/screens.

The program window is not needed for the screenshots: the interface lives on the
same bridge, so we bring the bridge up with fake data and open the page in Edge
without a window, using the same engine as the program itself (WebView2 is the
Chromium from Edge). The data is fake on purpose: the screenshots must not depend
on which speakers happen to be plugged into the machine where they are taken.

Notifications are drawn by the overlay module itself — we take its image as is.

    python tools/shots.py
"""
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mas.bridge import Bridge          # noqa: E402
from mas import overlay                # noqa: E402

OUT = ROOT / "docs" / "screens"
SCALE = 2                              # double-resolution shots — more readable
# The page is scaled up with `html{zoom:1.1}`. WebView2 gives it 10% less room in
# layout units, headless Chromium does not, and the content spills over the edge.
# So for the screenshots we drop the zoom and give the same 10% back with the
# device scale factor: the window is set in layout units, and the image comes out
# at the size of the real window (440×772 at SCALE=1).
ZOOM = 1.1
WIN_W, WIN_H = 400, 702                # 440×772 of the real window, divided by the zoom
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

SPK = "{0.0.0.00000000}.{aaaa1111-0000-0000-0000-000000000001}"
HP = "{0.0.0.00000000}.{aaaa1111-0000-0000-0000-000000000002}"
HDMI = "{0.0.0.00000000}.{aaaa1111-0000-0000-0000-000000000003}"
MIC_HP = "{0.0.1.00000000}.{bbbb2222-0000-0000-0000-000000000001}"
MIC_ARR = "{0.0.1.00000000}.{bbbb2222-0000-0000-0000-000000000002}"

OUTPUTS = [
    {"id": HP, "name": "Headphones (HyperX Cloud Flight S)", "kind": "Headset",
     "icon": "headset", "in_cycle": True, "is_default": True},
    {"id": SPK, "name": "Speakers (Realtek(R) Audio)", "kind": "Speakers",
     "icon": "laptop", "in_cycle": True, "is_default": False},
    {"id": HDMI, "name": "LG HDR 4K (AMD High Definition Audio)", "kind": "Monitor",
     "icon": "monitor", "in_cycle": False, "is_default": False},
]
INPUTS = [
    {"id": MIC_HP, "name": "Microphone (HyperX Cloud Flight S)", "kind": "Microphone",
     "icon": "microphone", "in_cycle": False, "is_default": True},
    {"id": MIC_ARR, "name": "Microphone Array (Realtek(R) Audio)", "kind": "Microphone",
     "icon": "microphone", "in_cycle": False, "is_default": False},
]
KNOWN = [
    {"id": HP, "name": "Headphones (HyperX Cloud Flight S)", "active": True},
    {"id": SPK, "name": "Speakers (Realtek(R) Audio)", "active": True},
    {"id": HDMI, "name": "LG HDR 4K (AMD High Definition Audio)", "active": True},
    {"id": "absent-1", "name": "Digital Audio (S/PDIF)", "active": False},
    {"id": "absent-2", "name": "Headphones (Powerbeats Pro)", "active": False},
]
SESSIONS = [
    {"key": "System sounds", "name": "System sounds", "volume": 0.6,
     "muted": False, "icon": None},
    {"key": "spotify.exe", "name": "Spotify", "volume": 0.74, "muted": False, "icon": None},
    {"key": "discord.exe", "name": "Discord", "volume": 1.0, "muted": False, "icon": None},
    {"key": "chrome.exe", "name": "Google Chrome", "volume": 0.35, "muted": True, "icon": None},
]


class FakeApi:
    """The same set of methods as the real Api, but with made-up data."""

    def __init__(self):
        self.tab = "devices"
        self.settings = {
            "language": "en", "autostart": True, "switch_communications": True,
            "sound_on_switch": False, "notify_on_switch": True, "theme": "dark",
            "switch_button": "left", "hotkey": "Ctrl+Alt+H", "hotkey_ok": True,
            "auto_device": HP, "switch_microphone": True, "watch_dongle": True,
            "learn_dongle": False, "mics_expanded": False, "onboarded": True,
            "version": __import__("mas").__version__,
            "dongle_name": "HyperX Cloud Flight S", "dongle_usb": None,
        }

    # --- what the interface reads -------------------------------------
    def selfcheck(self, **kw):
        return {"python": sys.version.split()[0], "frozen": False, "log": "—"}

    def get_state(self):
        return {"outputs": OUTPUTS, "inputs": INPUTS, "known_outputs": KNOWN,
                "settings": dict(self.settings)}

    def get_mixer(self):
        return {"master": {"volume": 0.62, "muted": False},
                "device": "Headphones (HyperX Cloud Flight S)", "sessions": SESSIONS}

    def get_meter(self):
        return {"volume": 0.62, "muted": False, "peak": 0.22,
                "device": "Headphones (HyperX Cloud Flight S)",
                "tab": self.tab, "rev": 1}

    # --- what the interface tries to change ----------------------------
    def set_setting(self, key, value):
        self.settings[key] = value
        return self.get_state()

    def toggle_cycle(self, **kw):
        return self.get_state()

    def switch_to(self, **kw):
        return self.get_state()

    def reorder(self, **kw):
        return self.get_state()

    def set_icon(self, **kw):
        return self.get_state()

    def set_master(self, **kw):
        return True

    def set_master_mute(self, **kw):
        return True

    def set_app_volume(self, **kw):
        return True

    def set_app_mute(self, **kw):
        return True

    def complete_onboarding(self):
        return True

    def media(self, **kw):
        return True

    def set_mini(self, **kw):
        return True


# An action that cannot be expressed through settings: a button click. The script
# waits for the element to appear, because the interface is built after page load.
INJECT = """
<style>
  /* We drop the page zoom: the device scale factor gives it back, otherwise the
     layout thinks there is 10% more room than there is. The window size cannot
     be given to the browser — Windows will not let a window be narrower than 500
     points, so we hold the program body as an exact box right in the layout and
     cut off the excess afterwards. */
  html{zoom:1 !important}
  html,body{width:var(--shot-w);height:var(--shot-h);overflow:hidden}
  /* The icon palette and the welcome screen are stretched to the browser window,
     but they must be stretched to the program body. */
  body{position:relative}
  #overlays{position:absolute;inset:0}
  .sheet,.welcome{position:absolute !important}
</style>
<script>
(() => {
  const q = new URLSearchParams(location.search);
  const root = document.documentElement.style;
  root.setProperty('--shot-w', (q.get('w') || 400) + 'px');
  root.setProperty('--shot-h', (q.get('h') || 702) + 'px');
  const act = q.get('act');
  const wanted = { icons: '.row [data-act="icon"]', hotkey: '#hk-capture',
                   mini: '#btn-mini' }[act];
  if (!wanted) return;
  const tick = setInterval(() => {
    const el = document.querySelector(wanted);
    if (!el) return;
    clearInterval(tick);
    el.click();
  }, 50);
})();
</script>
"""


def ui_copy() -> Path:
    """A copy of the interface folder with the clicker script added."""
    tmp = Path(tempfile.mkdtemp(prefix="mas-shots-"))
    dst = tmp / "ui"
    shutil.copytree(ROOT / "src" / "mas" / "ui", dst)
    index = dst / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace("</html>", INJECT + "</html>"),
                     encoding="utf-8")
    return dst


def edge() -> str:
    for path in EDGE_CANDIDATES:
        if Path(path).is_file():
            return path
    raise SystemExit("Edge not found — nothing to take page screenshots with")


def shoot(browser: str, base: str, out: Path, height: int, act: str) -> None:
    """Screenshot of the program body: a window with slack, the excess cut off."""
    from PIL import Image

    profile = Path(tempfile.mkdtemp(prefix="mas-edge-"))
    url = f"{base}?w={WIN_W}&h={height}" + (f"&act={act}" if act else "")
    subprocess.run(
        [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--force-device-scale-factor={SCALE * ZOOM}",
         f"--window-size={WIN_W + 160},{height + 160}",
         f"--screenshot={out}", f"--user-data-dir={profile}",
         "--virtual-time-budget=3000", "--no-first-run", "--disable-extensions",
         "--disable-features=Translate,MediaRouter", url],
        capture_output=True, timeout=90)
    shutil.rmtree(profile, ignore_errors=True)
    if not out.is_file():
        raise SystemExit(f"screenshot failed: {out.name}")

    box = (round(WIN_W * ZOOM * SCALE), round(height * ZOOM * SCALE))
    with Image.open(out) as img:
        if img.width < box[0] or img.height < box[1]:
            raise SystemExit(f"{out.name}: window smaller than body, {img.size} < {box}")
        img.crop((0, 0, *box)).save(out)
    print(f"  {out.name}  {box[0]}×{box[1]}, {out.stat().st_size // 1024} KB")


# Screens: file name, what to show, window size. Height 772 is that of the real
# window; for long tabs we take a tall window so the whole page fits.
TALL = 1180                            # tall window: the long tab in full
TALLER = 1400                          # the same, but with the diagnostics section

SCREENS = [
    ("01-devices-dark", {"tab": "devices", "theme": "dark"}, WIN_H, ""),
    ("02-devices-light", {"tab": "devices", "theme": "light"}, WIN_H, ""),
    ("03-devices-mics", {"tab": "devices", "theme": "dark", "mics_expanded": True}, WIN_H, ""),
    ("04-mixer-dark", {"tab": "mixer", "theme": "dark"}, WIN_H, ""),
    ("05-mixer-light", {"tab": "mixer", "theme": "light"}, WIN_H, ""),
    ("06-settings-dark", {"tab": "settings", "theme": "dark"}, WIN_H, ""),
    ("07-settings-light", {"tab": "settings", "theme": "light"}, WIN_H, ""),
    ("08-settings-full-dark", {"tab": "settings", "theme": "dark"}, TALL, ""),
    ("09-settings-full-light", {"tab": "settings", "theme": "light"}, TALL, ""),
    ("10-settings-learn", {"tab": "settings", "theme": "dark", "dongle_name": None,
                           "dongle_usb": "046D:0A5B", "learn_dongle": True}, TALLER, ""),
    ("11-hotkey-capture", {"tab": "settings", "theme": "dark"}, TALL, "hotkey"),
    ("12-hotkey-empty", {"tab": "settings", "theme": "dark", "hotkey": ""}, TALL, ""),
    ("13-icons-sheet", {"tab": "devices", "theme": "dark"}, WIN_H, "icons"),
    ("14-icons-sheet-light", {"tab": "devices", "theme": "light"}, WIN_H, "icons"),
    ("15-welcome", {"tab": "devices", "theme": "dark", "onboarded": False}, WIN_H, ""),
    ("16-welcome-light", {"tab": "devices", "theme": "light", "onboarded": False}, WIN_H, ""),
    ("17-about-dark", {"tab": "about", "theme": "dark"}, WIN_H, ""),
    ("18-about-light", {"tab": "about", "theme": "light"}, WIN_H, ""),
    # Mini view: the same height the interface asks Python for.
    ("25-mini-dark", {"tab": "devices", "theme": "dark"}, 250, "mini"),
    ("26-mini-light", {"tab": "devices", "theme": "light"}, 250, "mini"),
]

# Notifications: icon, caption, whether the theme is light.
NOTES = [
    ("19-notify-headset-dark", "headset", "Headphones (HyperX Cloud Flight S)", False),
    ("20-notify-headset-light", "headset", "Headphones (HyperX Cloud Flight S)", True),
    ("21-notify-speakers-dark", "laptop", "Speakers (Realtek(R) Audio)", False),
    ("22-notify-speakers-light", "laptop", "Speakers (Realtek(R) Audio)", True),
    ("23-notify-long-dark", "monitor", "LG HDR 4K (AMD High Definition Audio)", False),
    ("24-notify-mic-dark", "microphone", "Microphone (HyperX Cloud Flight S)", False),
]


def notifications() -> None:
    """Notification panels: as-is with transparency, and on a backdrop to show it."""
    from PIL import Image
    for name, glyph, text, light in NOTES:
        img = overlay._render(glyph, text, light)
        img.save(OUT / f"{name}.png")
        # The backdrop is there so the rounded corners and the semi-transparency
        # are visible against the white background of an image viewer.
        back = Image.new("RGBA", (img.width + 48, img.height + 48),
                         (228, 226, 222, 255) if light else (18, 20, 23, 255))
        back.alpha_composite(img, (24, 24))
        back.save(OUT / f"{name}-on-desktop.png")
        print(f"  {name}.png  {img.width}×{img.height}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    api = FakeApi()
    bridge = Bridge(api, ui_dir_override=ui_copy())
    bridge.start()
    browser = edge()
    print(f"bridge at {bridge.url}, screenshots into {OUT}")

    try:
        for name, over, height, act in SCREENS:
            api.tab = over.get("tab", "devices")
            api.settings.update({k: v for k, v in over.items() if k != "tab"})
            shoot(browser, bridge.url, OUT / f"{name}.png", height, act)
            # Put the settings back to normal so tweaks made for one screenshot
            # do not leak into the next one.
            api.__init__()
            time.sleep(0.1)
    finally:
        bridge.stop()

    notifications()
    print(f"done: {len(list(OUT.glob('*.png')))} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
