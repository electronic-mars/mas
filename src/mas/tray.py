"""Tray icon and three gestures.

pystray physically never gets a double click: it registers its own window without
the CS_DBLCLKS style. So the double click is not used at all, and mouse messages
are parsed directly — that way a single left click fires instantly, with no delay
spent waiting for a second click.
"""
import ctypes
import os
import queue
import tempfile
import threading
import winreg
from ctypes import wintypes

import pystray
from PIL import Image, ImageChops, ImageDraw

from . import log
from .core import strings
from .paths import icons_dir

_log = log.get("tray")

WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_MBUTTONUP = 0x0208
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN = 0x0201, 0x0204, 0x0207

DEFAULT_GLYPH = "speakers"
SM_CXSMICON = 49
HAVE_SIZES = (16, 20, 24, 32, 40, 48, 64)
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010

user32 = ctypes.windll.user32
user32.LoadImageW.restype = wintypes.HANDLE


def tray_icon_size() -> int:
    """The icon size Windows expects in the tray, mapped onto the files we have.

    At 125% scaling that is 20 pixels, at 150% — 24. Hand it 32 and Windows will
    shrink it itself, and the glyph will smear: that is exactly why we take the
    file of the size needed.
    """
    want = user32.GetSystemMetrics(SM_CXSMICON) or 16
    for size in HAVE_SIZES:
        if size >= want:
            return size
    return HAVE_SIZES[-1]


def taskbar_is_light() -> bool:
    """0 in SystemUsesLightTheme = dark taskbar, which means a white glyph."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "SystemUsesLightTheme")[0])
    except OSError:
        return False


def load_glyph(name: str, light_taskbar: bool, size: int | None = None) -> Image.Image:
    theme = "light" if light_taskbar else "dark"
    size = size or tray_icon_size()
    path = icons_dir() / "devices" / f"{name}_{theme}_{size}.png"
    if not path.is_file():
        path = icons_dir() / "devices" / f"{DEFAULT_GLYPH}_{theme}_{size}.png"
    return Image.open(path).convert("RGBA")


def with_mute_mark(img: Image.Image, light_taskbar: bool) -> Image.Image:
    """The glyph with a cross cut into its lower right corner: the sound is off.

    The cross stands in a hole of its own rather than on top of the glyph, so
    it reads at twenty pixels instead of merging with the lines under it. The
    hole and the cross are drawn eight times larger and brought down as masks,
    so their edges are smooth; the glyph itself is never resampled — that
    blurred every line of it.
    """
    k = 8
    size = img.width
    s = size * k
    x0 = s / 2                                 # the corner the cross takes
    gap = k * 1.2
    hole = Image.new("L", (s, s), 0)
    ImageDraw.Draw(hole).ellipse((x0 - gap, x0 - gap, s + gap, s + gap), fill=255)
    cross = Image.new("L", (s, s), 0)
    pad = x0 * 0.24
    width = round(size / 13 * k)
    draw = ImageDraw.Draw(cross)
    draw.line((x0 + pad, x0 + pad, s - pad, s - pad), fill=255, width=width)
    draw.line((x0 + pad, s - pad, s - pad, x0 + pad), fill=255, width=width)
    hole = hole.resize((size, size), Image.LANCZOS)
    cross = cross.resize((size, size), Image.LANCZOS)

    out = img.copy()
    keep = Image.eval(hole, lambda v: 255 - v)
    out.putalpha(ImageChops.multiply(out.getchannel("A"), keep))
    ink = (0, 0, 0, 255) if light_taskbar else (255, 255, 255, 255)
    mark = Image.new("RGBA", out.size, ink)
    mark.putalpha(cross)
    return Image.alpha_composite(out, mark)


def icon_handle(img: Image.Image) -> int:
    """A Windows icon of exactly the size it was drawn at, with no rescaling.

    pystray itself loads the icon with the "default size" flag, and for icons that
    is 32 pixels: it would first stretch a 20-pixel image up to 32, and the tray
    would then squeeze it back down to 20. On top of that PIL, saving an ICO
    without an explicit size list, writes a single 16x16 entry out of a 20x20
    image. So we write an ICO with one entry of the size needed and ask Windows
    for exactly that size.
    """
    fd, path = tempfile.mkstemp(suffix=".ico")
    os.close(fd)
    try:
        img.save(path, format="ICO", sizes=[img.size])
        return user32.LoadImageW(None, path, IMAGE_ICON, img.width, img.height,
                                 LR_LOADFROMFILE)
    finally:
        os.unlink(path)


class Tray:
    def __init__(self, on_left, on_right, on_middle, on_quit, outside_decides=False,
                 on_hover=None, on_click=None):
        """`on_hover` hears every move of the pointer over the icon, `on_click`
        every press of a button on it — the hover card lives on those two."""
        self.on_hover = on_hover
        self.on_click = on_click
        self.on_left = on_left
        self.on_right = on_right
        self.on_middle = on_middle
        self.on_quit = on_quit
        self._glyph = DEFAULT_GLYPH
        self._muted = False
        self._light = taskbar_is_light()
        self.icon = pystray.Icon(
            "MasterAudioSwitcher",
            load_glyph(self._glyph, self._light),
            # The name only until the first sign that Windows tells us about the
            # pointer over the icon: from then on our own card comes up there
            # (see overlay.py), and a tooltip would open on top of it.
            "Master Audio Switcher",
            menu=pystray.Menu(pystray.MenuItem(strings.t("tray_exit"), lambda: self.on_quit())),
        )
        self._stop = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        # The icon is not shown until we know which one to show. It used to
        # appear as the default speakers and change to the real device a moment
        # later, and that blink is the first thing a person sees of the program.
        self._shown = False
        # Who decides whether the icon is in the tray. False: this object does,
        # on the first device it hears of, with a timer as a safety net. True:
        # somebody outside does, through set_visible, and nothing here shows or
        # hides on its own. It starts True when the dock was drawing us last
        # time — the icon must not flash on at every boot only to be taken away
        # — and becomes True for good at the first set_visible. One meaning; it
        # used to be cleared there instead, and a device change put back an icon
        # the dock was holding.
        self._outside_decides = outside_decides

    # --- appearance --------------------------------------------------
    # The tray icon is a shared Windows resource. Changing it from arbitrary
    # threads (say, from an HTTP request thread when an icon is picked in the
    # window) is unsafe, so all changes are queued and run by a single thread.
    def set_device(self, glyph: str | None) -> None:
        self._queue.put(("device", glyph or DEFAULT_GLYPH, None))

    def set_muted(self, muted: bool) -> None:
        """The sound was switched off or on — by us, by a keyboard key or in
        Windows itself. Without a mark the icon said nothing about it, and a
        person turning the volume up heard nothing and did not know why."""
        self._queue.put(("muted", bool(muted), None))

    def _image(self, size: int | None = None) -> Image.Image:
        img = load_glyph(self._glyph, self._light, size)
        return with_mute_mark(img, self._light) if self._muted else img

    def notify(self, message: str, title: str = "Master Audio Switcher") -> None:
        self._queue.put(("notify", message, title))

    def _apply(self, job) -> None:
        kind = job[0]
        if kind == "device":
            self._glyph = job[1]
            self.icon.icon = self._image()
            self._show()
        elif kind == "muted":
            if job[1] != self._muted:
                self._muted = job[1]
                self.icon.icon = self._image()
        elif kind == "visible":
            self._outside_decides = True
            if bool(job[1]) != self._shown:
                self._shown = bool(job[1])
                if self._shown:
                    self._add()
                else:
                    self.icon.visible = False
                _log.info("icon %s the tray", "into" if self._shown else "out of")
        elif kind == "notify":
            _, message, title = job
            self.icon.notify(message, title)

    def set_visible(self, on: bool) -> None:
        """Shown or not — the answer coming from outside, and the last word."""
        self._queue.put(("visible", bool(on), None))

    def _add(self) -> None:
        """Put the icon into the notification area, clearing the place first.

        Held back from a start at sign-in and shown six minutes later, the icon
        did not appear: the log said it had, the notification area said
        otherwise. Taken out and shown again, it appeared every time. The only
        difference between the two is a delete in front of the add, so there is
        always one now — for a place that holds nothing it simply fails, which
        costs nothing. What the notification area was keeping in that place was
        never pinned down; sign-in cannot be replayed on demand.
        """
        self.icon._hide()
        self.icon.visible = True

    def _show(self) -> None:
        """Into the tray, once, whichever of the two reasons arrives first."""
        if self._outside_decides:
            return
        if not self._shown:
            self._shown = True
            self._add()
            _log.info("icon in the tray: %s", self._glyph)

    def _show_anyway(self) -> None:
        """A safety net. Waiting for the right icon must never end with no icon
        at all: if the device cannot be read, the program still has to be in the
        tray, because that is where its only certain way out lives."""
        if self._outside_decides:
            return      # the dock's watch decides this one, not a timer here
        if not self._stop.wait(3.0):
            if not self._shown:
                _log.warning("no device came within 3 s — showing the default icon")
            self._show()

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                self._apply(job)
            except Exception:
                _log.warning("tray icon update failed (%s)", job[0], exc_info=True)

    # --- mouse interception -------------------------------------
    def _install_mouse_hook(self) -> None:
        from pystray._util import win32

        original = self.icon._message_handlers.get(win32.WM_NOTIFY)

        def handler(wparam, lparam):
            if lparam == WM_MOUSEMOVE:
                if self.on_hover:
                    if self.icon.title:
                        self.icon.title = ""
                    self._safe(self.on_hover, "hover")
                return
            if lparam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN) and self.on_click:
                self._safe(self.on_click, "press")
            if lparam == WM_LBUTTONUP:
                self._safe(self.on_left, "left button")
                return
            if lparam == WM_RBUTTONUP:
                self._safe(self.on_right, "right button")
                return
            if lparam == WM_MBUTTONUP:
                self._safe(self.on_middle, "middle button")
                return
            if original:
                original(wparam, lparam)

        self.icon._message_handlers[win32.WM_NOTIFY] = handler
        _log.info("icon click interception installed")

    def _install_icon_loader(self) -> None:
        """Our own icon loading instead of pystray's: see `icon_handle`."""
        icon = self.icon

        def assert_handle():
            if icon._icon_handle:
                return
            icon._icon_handle = icon_handle(icon.icon)

        icon._assert_icon_handle = assert_handle
        _log.info("tray icon loaded by our own loader, size %s", tray_icon_size())

    @staticmethod
    def _safe(fn, label: str) -> None:
        try:
            fn()
        except Exception:
            _log.exception("error in handler: %s", label)

    # --- taskbar theme -----------------------------------------
    def _theme_poller(self) -> None:
        size = tray_icon_size()
        while not self._stop.wait(2.0):
            light, now = taskbar_is_light(), tray_icon_size()
            # People change screen scaling on the fly, and then the tray starts
            # asking for another icon size — redraw it, otherwise it smears.
            if light != self._light or now != size:
                self._light, size = light, now
                self.icon.icon = self._image(now)
                _log.info("tray icon redrawn (light taskbar: %s, size: %s)", light, now)

    # --- lifecycle -----------------------------------------------
    def run(self) -> None:
        def setup(icon):
            self._install_icon_loader()
            self._install_mouse_hook()
            threading.Thread(target=self._worker, daemon=True, name="mas-tray-jobs").start()
            threading.Thread(target=self._show_anyway, daemon=True, name="mas-tray-show").start()
            threading.Thread(target=self._theme_poller, daemon=True, name="mas-theme").start()

        self.icon.run(setup=setup)

    def stop(self) -> None:
        self._stop.set()
        self.icon.stop()
