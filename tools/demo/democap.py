"""Scripted screen recordings for the READMEs and the site.

One clip is: a plain stage drawn over the desk, the program started in its demo
mode, the mouse moved by a script along a smooth path, and ffmpeg recording the
stage with the cursor drawn in. The same script gives the same clip every time.

    python tools/demo/democap.py stage X Y W H     (the stage on its own, used internally)

Everything here works in physical pixels: the process declares itself
per-monitor DPI aware before it measures or moves anything, and so does ffmpeg's
gdigrab. A rectangle taken in one awareness and used in another lands somewhere
else without a word.
"""
import ctypes
import math
import subprocess
import sys
import time
from pathlib import Path

user32 = ctypes.windll.user32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # per-monitor v2

LEFTDOWN, LEFTUP, WHEEL = 0x0002, 0x0004, 0x0800
MOVE, ABSOLUTE, VIRTUALDESK = 0x0001, 0x8000, 0x4000


def pointer(x: int, y: int) -> None:
    """Moves the cursor as a mouse would: as input, not with SetCursorPos.

    SetCursorPos moves the arrow and nothing else - a slider held by its thumb
    saw no movement at all, and stayed where it was through a whole drag.
    """
    vx, vy, vw, vh = (user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))
    nx = round((x - vx) * 65535 / (vw - 1))
    ny = round((y - vy) * 65535 / (vh - 1))
    user32.mouse_event(MOVE | ABSOLUTE | VIRTUALDESK, nx, ny, 0, 0)


def ffmpeg() -> str:
    """The full build first: the essentials build has no libvpx for WebM."""
    import shutil
    winget = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    for found in sorted(winget.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"), reverse=True):
        return str(found)
    return shutil.which("ffmpeg") or "ffmpeg"


class Clip:
    """A stage, a recording of it, and a mouse that moves like a hand."""

    def __init__(self, x: int, y: int, w: int, h: int, out: Path, fps: int = 30, corner: str = "br"):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.corner = corner
        self.out = out
        self.fps = fps
        self.stage = None
        self.rec = None

    # --- the stage ------------------------------------------------------------
    def show_stage(self) -> None:
        self.stage = subprocess.Popen(
            [sys.executable, __file__, "stage", str(self.x), str(self.y), str(self.w), str(self.h), self.corner],
            stdin=subprocess.PIPE)
        time.sleep(1.5)

    # --- the recording --------------------------------------------------------
    def start(self) -> None:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.rec = subprocess.Popen(
            [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "gdigrab", "-framerate", str(self.fps), "-draw_mouse", "1",
             "-offset_x", str(self.x), "-offset_y", str(self.y),
             "-video_size", f"{self.w}x{self.h}", "-i", "desktop",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "10", "-pix_fmt", "yuv420p",
             str(self.out)],
            stdin=subprocess.PIPE)
        time.sleep(0.8)   # gdigrab's first frames come late
        self.began = time.time()

    def stop(self) -> None:
        """Ends the recording and notes how long the scripted part lasted.

        The encoder keeps that much from the end of the file: the end is exact,
        because ffmpeg stops on 'q' at once, while the start waits on gdigrab.
        """
        if self.rec:
            self.out.with_suffix(".json").write_text(
                '{"seconds": %.2f}' % (time.time() - self.began), encoding="utf-8")
            self.rec.communicate(b"q", timeout=30)
            self.rec = None
        if self.stage:
            self.stage.terminate()
            self.stage = None

    # --- the hand -------------------------------------------------------------
    def at(self, sx: int, sy: int) -> tuple[int, int]:
        """A point on the stage, in screen pixels."""
        return self.x + sx, self.y + sy

    def place(self, sx: int, sy: int) -> None:
        pointer(*self.at(sx, sy))

    def move(self, sx: int, sy: int, seconds: float = 0.6) -> None:
        """Eased, along a slight arc - a straight constant-speed line reads as a robot."""
        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        x0, y0 = pt.x, pt.y
        x1, y1 = self.at(sx, sy)
        steps = max(2, int(seconds * 120))
        bow = 0.08 * math.hypot(x1 - x0, y1 - y0)
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3 - 2 * t)
            lift = math.sin(math.pi * e) * bow
            pointer(int(x0 + (x1 - x0) * e), int(y0 + (y1 - y0) * e - lift))
            time.sleep(seconds / steps)

    def click(self, pause: float = 0.12) -> None:
        user32.mouse_event(LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.07)
        user32.mouse_event(LEFTUP, 0, 0, 0, 0)
        time.sleep(pause)

    def down(self) -> None:
        user32.mouse_event(LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.1)

    def up(self) -> None:
        user32.mouse_event(LEFTUP, 0, 0, 0, 0)
        time.sleep(0.1)

    def wheel(self, notches: int, seconds: float = 1.0) -> None:
        step = 1 if notches > 0 else -1
        for _ in range(abs(notches)):
            user32.mouse_event(WHEEL, 0, 0, ctypes.c_uint32(120 * step).value, 0)
            time.sleep(seconds / abs(notches))

    @staticmethod
    def wait(seconds: float) -> None:
        time.sleep(seconds)


def window_of(exe_name: str, min_width: int = 400, topmost: bool = False) -> int:
    """The program's largest visible window - its settings or main window.

    Topmost ones are left out unless asked for: a dock bar is one, and it is
    wider than any window it opens."""
    import ctypes.wintypes as wt
    found: list[tuple[int, int]] = []
    kernel32 = ctypes.windll.kernel32

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def each(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or (not topmost and user32.GetWindowLongW(hwnd, -20) & 0x8):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = kernel32.OpenProcess(0x1000, False, pid.value)
        name = ctypes.create_unicode_buffer(260)
        size = wt.DWORD(260)
        ok = proc and kernel32.QueryFullProcessImageNameW(proc, 0, name, ctypes.byref(size))
        if proc:
            kernel32.CloseHandle(proc)
        if ok and name.value.lower().endswith(exe_name.lower()):
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left >= min_width:
                found.append(((r.right - r.left) * (r.bottom - r.top), hwnd))
        return True

    user32.EnumWindows(each, 0)
    if not found:
        raise LookupError(f"no window of {exe_name}")
    return max(found)[1]


def place_window(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Moves a window, in physical pixels, keeping its size; returns the size."""
    import ctypes.wintypes as wt
    user32.ShowWindow(hwnd, 9)   # SW_RESTORE
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    # Typed, or HWND_TOPMOST goes over as a 32-bit -1, 0xFFFFFFFF, and the call
    # silently does nothing: the window stayed under the stage, where it was.
    user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetWindowPos(hwnd, wt.HWND(-1), x, y, 0, 0, 0x0041)   # HWND_TOPMOST, SWP_NOSIZE | SWP_SHOWWINDOW
    time.sleep(0.4)
    return r.right - r.left, r.bottom - r.top


def wait_for_line(log: Path, text: str, timeout: float = 30) -> None:
    """Keyed on what the program says it has done, never on a guessed delay."""
    end = time.time() + timeout
    while time.time() < end:
        if log.exists() and text in log.read_text(encoding="utf-8", errors="replace"):
            return
        time.sleep(0.2)
    raise TimeoutError(f"{text!r} never appeared in {log}")


PLANET = Path(__file__).resolve().parents[3] / "electronic-mars.github.io/img/colony.webp"


def run_stage(x: int, y: int, w: int, h: int, corner: str = "br") -> None:
    """The made-up desk: deep space, twinkling stars, and the site's planet.

    The planet is the logo of electronic-mars.github.io, taken from that
    repository beside this one; without it the stage is stars alone. It sits
    in a corner the clip leaves free - bottom right for the bar along the top,
    bottom left for a program by the tray.
    """
    import random
    import tkinter
    from PIL import Image, ImageTk

    top, bottom = (14, 18, 38), (4, 5, 12)
    sky = Image.new("RGB", (1, h))
    for row in range(h):
        t = row / max(1, h - 1)
        sky.putpixel((0, row), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    sky = sky.resize((w, h))

    root = tkinter.Tk()
    root.overrideredirect(True)
    root.geometry(f"{w}x{h}+{x}+{y}")
    canvas = tkinter.Canvas(root, width=w, height=h, highlightthickness=0, borderwidth=0)
    canvas.pack()
    keep = [ImageTk.PhotoImage(sky)]
    canvas.create_image(0, 0, image=keep[0], anchor="nw")

    # The same sky every take, so two takes of one clip can be compared.
    rng = random.Random(21)
    stars = []
    for _ in range(int(w * h / 4500)):
        r = rng.choice((0.7, 0.9, 1.1, 1.4, 1.8))
        sx, sy = rng.uniform(0, w), rng.uniform(0, h)
        item = canvas.create_oval(sx - r, sy - r, sx + r, sy + r, width=0, fill="#ffffff")
        stars.append((item, rng.uniform(0, 6.3), rng.uniform(0.6, 2.2), rng.uniform(0.45, 1.0)))

    if PLANET.exists():
        size = int(h * 0.62)
        planet = Image.open(PLANET).convert("RGBA").resize((size, size), Image.LANCZOS)
        keep.append(ImageTk.PhotoImage(planet))
        px = w - size - int(w * 0.04) if corner == "br" else int(w * 0.04)
        canvas.create_image(px, h - size - int(h * 0.04), image=keep[1], anchor="nw")

    started = time.time()

    def twinkle() -> None:
        t = time.time() - started
        for item, phase, speed, peak in stars:
            v = int(255 * peak * (0.35 + 0.65 * (0.5 + 0.5 * math.sin(phase + t * speed))))
            canvas.itemconfigure(item, fill=f"#{v:02x}{v:02x}{min(255, v + 18):02x}")
        root.after(50, twinkle)

    twinkle()

    # Topmost from the start, so the window of whoever is working at this
    # machine cannot come up over it. What the program opens later goes above
    # it: the bar and its flyouts are topmost too, and place_window lifts the
    # rest. Raising the stage again mid-take put it over the bar.
    root.attributes("-topmost", True)

    # The end of stdin closes the stage.
    import threading

    def listen() -> None:
        sys.stdin.read()
        root.after(0, root.destroy)

    threading.Thread(target=listen, daemon=True).start()
    root.mainloop()


if __name__ == "__main__" and len(sys.argv) in (6, 7) and sys.argv[1] == "stage":
    import ctypes.wintypes  # noqa: F401
    run_stage(*map(int, sys.argv[2:6]), *sys.argv[6:])
else:
    import ctypes.wintypes  # noqa: F401,E402
