"""Demo clips of Master Audio Switcher, recorded from the program's demo mode.

    python tools/demo/mas.py hero            one clip, into tools/demo/out/hero.mp4
    python tools/demo/mas.py all             hero, tour and compact
    python tools/demo/mas.py shots           stills without the cursor, into tools/demo/out/shots/mas
    python tools/demo/mas.py pose [seconds]  stage and program only, for measuring

MAS_DEMO=1 gives the program made-up devices, applications and player, every
volume at 21, and a settings folder of its own (src/mas/core/demo.py). The
installed copy holds the single-instance lock, so it is asked to quit through
its own bridge first - the way the dock talks to it - and started again at the
end.

The clip is the program's window and nothing else: its own size, no stage
around it. Coordinates are in the window, in pixels at this machine's scale.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import ctypes
import math

from democap import Clip, place_window, pointer, user32, wait_for_line, window_of

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
PYTHON = ROOT / ".venv/Scripts/pythonw.exe"
INSTALLED = Path(os.environ["LOCALAPPDATA"]) / "Programs/MasterAudioSwitcher/MasterAudioSwitcher.exe"
NOTE = Path(os.environ["LOCALAPPDATA"]) / "MasterAudioSwitcher/bridge.json"



def ask(note: Path, call: str) -> bool:
    """One call to a running copy's bridge, as the dock makes it."""
    try:
        n = json.loads(note.read_text(encoding="utf-8"))
        req = urllib.request.Request(n["url"] + "api/" + call, data=b"{}", method="POST",
                                     headers={"X-MAS-Token": n["token"], "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as answer:
            return json.loads(answer.read().decode("utf-8")).get("ok") is True
    except (OSError, ValueError, KeyError):
        return False


def installed_running() -> bool:
    out = subprocess.run(["powershell", "-NoProfile", "-c",
                          "Get-Process MasterAudioSwitcher -ErrorAction SilentlyContinue | % Id"],
                         capture_output=True, text=True).stdout
    return bool(out.strip())


def start_demo() -> Path:
    data = Path(tempfile.mkdtemp(prefix="mas-demo-"))
    env = dict(os.environ, MAS_DEMO="1", MAS_DEMO_DATA=str(data))
    subprocess.Popen([str(PYTHON), str(ROOT / "src/run_mas.py")], env=env, cwd=ROOT)
    wait_for_line(data / "MasterAudioSwitcher/mas.log", "meter bound", timeout=40)
    time.sleep(2.0)
    return data


def stop_demo(data: Path) -> None:
    ask(data / "MasterAudioSwitcher/bridge.json", "quit")
    time.sleep(2.0)


def bounds(hwnd: int) -> tuple[int, int, int, int]:
    """Where the window shows, without the invisible frame around it."""
    import ctypes.wintypes as wt
    r = wt.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(wt.HWND(hwnd), 9, ctypes.byref(r), ctypes.sizeof(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def open_window(data: Path) -> int:
    """Opens the program's window, as the dock does, where the program puts
    it: by the tray. The switch card lines up with its bottom right corner
    there, and moved anywhere else the window cut the card off."""
    ask(data / "MasterAudioSwitcher/bridge.json", "bring_forward")
    time.sleep(1.5)
    hwnd = window_of("pythonw.exe", min_width=300, topmost=True)
    x, y, _, _ = bounds(hwnd)
    place_window(hwnd, x, y)              # the same place, only kept on top
    return hwnd


# --- the clips -----------------------------------------------------------------
# Points in the full window (440 x 772 at 125 %), measured on this machine.
DEVICES, MIXER, SETTINGS = (80, 110), (204, 110), (327, 110)
HEADPHONES_ROW = (250, 538)
PARK = (300, 30)                          # on the title: rows that come and go stay clear of it
KNOB = (121, 267)                         # the knob's centre
MUSIC, GAME = (181, 377), (181, 540)      # slider thumbs at 21
SLIDER_END = 506                          # past 100 on every slider
LIST = (266, 600)
MATCH, DARK, LIGHT = (108, 660), (264, 660), (422, 660)    # with the settings scrolled to the end
COMPACT = (481, 33)
# In the compact window (440 x 234 at 125 %).
MINI_KNOB, MUTE = (120, 172), (480, 239)


def angle_point(c: Clip, centre: tuple[int, int], degrees: float, radius: float = 40) -> tuple[int, int]:
    a = math.radians(degrees)
    return int(centre[0] + radius * math.sin(a)), int(centre[1] - radius * math.cos(a))


def turn(c: Clip, centre: tuple[int, int], seconds: float = 1.3, back: bool = True) -> None:
    """The knob from 21 to 100 and back, by its rim.

    It follows the angle of the hand from where it was taken: 0 at -135
    degrees, 100 at +135 (ui/app.js). Taken where 21 points and brought back
    to the same place, it is at 21 again, exactly - the wheel moves in twos
    and cannot land there from 100.
    """
    start, end = -135 + 2.7 * 21, 135 + 6     # a little past the stop, within its slack
    c.move(*angle_point(c, centre, start), 0.5)
    c.down()
    for a0, a1 in ((start, end), (end, start))[:2 if back else 1]:
        steps = int(seconds * 120)
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3 - 2 * t)
            pointer(*c.at(*angle_point(c, centre, a0 + (a1 - a0) * e)))
            time.sleep(seconds / steps)
        c.wait(0.3)
    c.up()


def slide(c: Clip, thumb: tuple[int, int]) -> None:
    c.move(*thumb, 0.5)
    c.down()
    c.move(SLIDER_END, thumb[1], 0.7)
    c.wait(0.25)
    c.move(*thumb, 0.7)
    c.up()


def headset(data: Path, on: bool) -> None:
    """Switches the made-up wireless headset on or off (demo.HEADSET)."""
    flag = data / "MasterAudioSwitcher/demo-headset"
    flag.touch() if on else flag.unlink(missing_ok=True)


def hero(c: Clip, data: Path) -> None:
    """Switching by hand with its card, the volume 21 -> 100 -> 21, and the
    wireless headset taking the sound and the microphone when it comes and
    giving them back when it goes."""
    c.wait(1.0)
    c.move(*HEADPHONES_ROW, 0.7)
    c.click()
    c.move(*PARK, 0.5)
    c.wait(1.8)                           # "Sound switched"
    turn(c, KNOB)
    c.move(*PARK, 0.4)
    c.wait(0.8)
    headset(data, True)                   # switched on: the sound and the microphone go to it
    c.wait(4.5)                           # the card covers the microphone row for a while
    headset(data, False)                  # off again: both come back
    c.wait(4.5)


def tour(c: Clip, data: Path) -> None:
    """The mixer, an application at a time, and the light and dark themes."""
    c.wait(0.8)
    c.move(*MIXER, 0.6)
    c.click()
    c.wait(1.0)
    slide(c, MUSIC)
    c.wait(0.3)
    slide(c, GAME)
    c.wait(0.5)
    c.move(*SETTINGS, 0.6)
    c.click()
    c.wait(0.8)
    c.move(*LIST, 0.4)
    c.wheel(-20, 1.2)
    c.wait(0.5)
    for button in (LIGHT, DARK, MATCH):
        c.move(*button, 0.6)
        c.click()
        c.wait(1.6)


def compact(c: Clip, data: Path) -> None:
    """The compact window: the knob, and the sound off and on."""
    c.wait(0.8)
    turn(c, MINI_KNOB, 1.1)
    c.wait(0.4)
    c.move(*MUTE, 0.5)
    c.click()
    c.wait(1.0)
    c.click()
    c.move(c.w // 2, 20, 0.5)             # away, before the button's tooltip comes up
    c.wait(0.8)


CLIPS = {"hero": hero, "tour": tour, "compact": compact}


def rounded(png: Path) -> None:
    """The corners outside the window are the desktop behind it: made transparent.
    Windows 11 rounds a window by 8 px at 100 %, 9 here at 125 %; drawn at 4x for a smooth edge."""
    from PIL import Image, ImageDraw
    im = Image.open(png).convert("RGBA")
    mask = Image.new("L", (im.width * 4, im.height * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), 36, fill=255)
    im.putalpha(mask.resize(im.size, Image.LANCZOS))
    im.save(png, optimize=True)


def shots() -> None:
    """Stills for the READMEs and the site, into tools/demo/out/shots/mas: the
    same scenes as the clips, taken from the screen itself without the cursor,
    which rests on the title before each one so nothing wears a hover."""
    to = OUT / "shots/mas"
    data = start_demo()
    try:
        hwnd = open_window(data)
        c = Clip(0, 0, 0, 0, to / "unused.mp4")
        c.x, c.y, c.w, c.h = bounds(hwnd)

        def snap(name: str, settle: float = 0.8) -> None:
            c.place(*PARK)
            c.wait(settle)
            c.snap(to / f"{name}.png")
            rounded(to / f"{name}.png")

        c.place(*PARK)
        c.click()                         # the first press after the window came forward was lost
        c.wait(0.8)
        c.move(*MIXER, 0.4)
        c.click()
        c.wait(1.0)
        c.move(*GAME, 0.3)
        c.down()
        c.move(SLIDER_END, GAME[1], 0.6)
        c.up()
        snap("mixer")                     # one program at 100, the rest at 21
        c.place(*DEVICES)
        c.click()
        c.wait(1.0)
        c.place(*HEADPHONES_ROW)
        c.click()
        snap("switch", 1.2)               # the card saying where the sound went
        c.wait(6.0)                       # until the card has gone
        turn(c, KNOB, 1.0, back=False)
        snap("devices")                   # the headphones at 100
        headset(data, True)
        c.wait(7.0)                       # the sound and the microphone move; the card comes and goes
        snap("headset")
        headset(data, False)
        c.wait(3.0)
        c.place(*SETTINGS)
        c.click()
        c.wait(1.0)
        c.place(*LIST)
        c.wheel(-20, 1.0)
        c.wait(0.5)
        c.place(*LIGHT)
        c.click()
        snap("light", 1.5)
        c.place(*MATCH)
        c.click()
        c.wait(1.0)
        c.place(*COMPACT)
        c.click()
        c.wait(1.5)
        c.x, c.y, c.w, c.h = bounds(hwnd)
        snap("compact")                   # the headphones still at 100
    finally:
        stop_demo(data)


def record(name: str) -> None:
    data = start_demo()
    try:
        hwnd = open_window(data)
        c = Clip(0, 0, 0, 0, OUT / f"{name}.mp4")
        c.x, c.y, c.w, c.h = bounds(hwnd)
        if name == "compact":
            c.place(*COMPACT)
            c.click()
            time.sleep(1.5)
            c.x, c.y, c.w, c.h = bounds(hwnd)
        c.w -= c.w % 2                    # the encoder wants even sides
        c.h -= c.h % 2
        c.place(*PARK if name != "compact" else (c.w // 2, 20))
        try:
            c.start()
            CLIPS[name](c, data)
        finally:
            c.stop()
    finally:
        stop_demo(data)


def main() -> int:
    what = sys.argv[1] if len(sys.argv) > 1 else "hero"
    was = installed_running()
    if was:
        ask(NOTE, "quit")
        for _ in range(50):
            if not installed_running():
                break
            time.sleep(0.2)
    try:
        if what == "pose":
            data = start_demo()
            try:
                print("demo data:", data, "window:", bounds(open_window(data)), flush=True)
                time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 120)
            finally:
                stop_demo(data)
            return 0
        if what == "shots":
            shots()
            print("stills in", OUT / "shots/mas", flush=True)
            return 0
        for name in (CLIPS if what == "all" else [what]):
            record(name)
            print("recorded", OUT / f"{name}.mp4", flush=True)
    finally:
        if was:
            subprocess.Popen([str(INSTALLED)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
