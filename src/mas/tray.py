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

# --- the mouse wheel over the icon ------------------------------------
# A tray icon is told about moves and presses, never about the wheel: the wheel
# goes to the window with the focus. So while the pointer is on the icon — and
# only then — a low-level mouse hook watches for the wheel and keeps the notches
# that land on the icon's rectangle. Every mouse event of the whole system runs
# through such a hook, in Python, holding up the pointer if Python is busy; a
# hook left on for the session would be paid for by every move anywhere. It is
# put on when the pointer arrives and taken off the moment it leaves.
WH_MOUSE_LL = 14
WM_MOUSEWHEEL = 0x020A
PM_REMOVE = 1
QS_ALLINPUT = 0x04FF
WHEEL_LEAVE_S = 0.3     # the pointer off the icon this long: the hook comes off
_u32 = ctypes.WinDLL("user32")
_k32 = ctypes.WinDLL("kernel32")
_shell = ctypes.WinDLL("shell32")


class _MSLLHOOK(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p)]


class _NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("guidItem", ctypes.c_byte * 16)]


_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_u32.SetWindowsHookExW.restype = ctypes.c_void_p
_u32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_u32.CallNextHookEx.restype = ctypes.c_ssize_t
_u32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_u32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
_u32.MsgWaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.c_void_p, wintypes.BOOL,
                                           wintypes.DWORD, wintypes.DWORD]
_u32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                              wintypes.UINT, wintypes.UINT]
_u32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_k32.GetModuleHandleW.restype = wintypes.HMODULE
_k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_shell.Shell_NotifyIconGetRect.restype = ctypes.c_long
_shell.Shell_NotifyIconGetRect.argtypes = [ctypes.POINTER(_NOTIFYICONIDENTIFIER),
                                           ctypes.POINTER(wintypes.RECT)]

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
                 on_hover=None, on_click=None, on_wheel=None):
        """`on_hover` hears every move of the pointer over the icon and says
        whether the wheel is wanted there; `on_wheel` gets the turned notches
        (120 a notch, up positive); `on_click` every press of a button on it."""
        self.on_hover = on_hover
        self.on_click = on_click
        self.on_wheel = on_wheel
        self._wheel_arm = threading.Event()
        self._wheel_rect: tuple[int, int, int, int] | None = None
        self._wheel_acc = 0
        self._hook_proc = _HOOKPROC(self._on_low_level_mouse)   # kept alive: Windows calls it
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
            # pointer over the icon: from then on, with the wheel on, nothing
            # comes up on a mere pass — the card answers the wheel, and a
            # tooltip would open on top of it.
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
                    # The pointer is on the icon: get ready for the wheel. The
                    # tooltip is empty while the wheel is on, so the card it
                    # brings up is the only thing there; switched off in the
                    # settings, the tooltip names the program again.
                    try:
                        wheel = bool(self.on_hover())
                    except Exception:
                        _log.exception("error in handler: hover")
                        wheel = False
                    if wheel:
                        self._wheel_arm.set()
                    want = "" if wheel else "Master Audio Switcher"
                    if self.icon.title != want:
                        self.icon.title = want
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

    def _icon_rect(self) -> tuple[int, int, int, int] | None:
        """Where the icon is on the screen now. pystray registers it with id 0
        (it passes its own id under a misspelt field name, so the real field
        stays zero)."""
        hwnd = getattr(self.icon, "_hwnd", None)
        if not hwnd:
            return None
        nid = _NOTIFYICONIDENTIFIER(cbSize=ctypes.sizeof(_NOTIFYICONIDENTIFIER),
                                    hWnd=hwnd, uID=0)
        r = wintypes.RECT()
        if _shell.Shell_NotifyIconGetRect(ctypes.byref(nid), ctypes.byref(r)) != 0:
            return None
        return r.left, r.top, r.right, r.bottom

    def _on_low_level_mouse(self, code, wparam, lparam):
        """Runs for every mouse event while the hook is on — so it only keeps
        the notch and returns; the work happens in the loop that pumps it."""
        try:
            rect = self._wheel_rect
            if code == 0 and wparam == WM_MOUSEWHEEL and rect:
                m = ctypes.cast(lparam, ctypes.POINTER(_MSLLHOOK)).contents
                if rect[0] <= m.x < rect[2] and rect[1] <= m.y < rect[3]:
                    self._wheel_acc += ctypes.c_short(m.mouseData >> 16).value
                    return 1        # ours: nothing else scrolls under the icon
        except Exception:
            pass
        return _u32.CallNextHookEx(None, code, wparam, lparam)

    def _wheel_loop(self) -> None:
        """Hook on while the pointer is on the icon, off when it leaves."""
        import time
        hmod = _k32.GetModuleHandleW(None)
        msg = wintypes.MSG()
        pt = wintypes.POINT()
        while not self._stop.is_set():
            if not self._wheel_arm.wait(1.0):
                continue
            self._wheel_arm.clear()
            rect = self._icon_rect()
            if rect is None:
                continue
            hook = _u32.SetWindowsHookExW(WH_MOUSE_LL, self._hook_proc, hmod, 0)
            if not hook:
                _log.warning("the wheel over the tray icon was not hooked (error %s)",
                             ctypes.get_last_error())
                continue
            self._wheel_rect, self._wheel_acc = rect, 0
            last_on = time.monotonic()
            try:
                while not self._stop.is_set():
                    # Woken at once by mouse input for the hook, else every 50 ms.
                    _u32.MsgWaitForMultipleObjects(0, None, False, 50, QS_ALLINPUT)
                    while _u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                        _u32.TranslateMessage(ctypes.byref(msg))
                        _u32.DispatchMessageW(ctypes.byref(msg))
                    acc, self._wheel_acc = self._wheel_acc, 0
                    if acc and self.on_wheel:
                        self._safe(lambda: self.on_wheel(acc), "wheel")
                    _u32.GetCursorPos(ctypes.byref(pt))
                    l, t, r, b = rect
                    if l - 2 <= pt.x < r + 2 and t - 2 <= pt.y < b + 2:
                        last_on = time.monotonic()
                    elif time.monotonic() - last_on > WHEEL_LEAVE_S:
                        break
            finally:
                self._wheel_rect = None
                _u32.UnhookWindowsHookEx(hook)

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
            threading.Thread(target=self._wheel_loop, daemon=True, name="mas-wheel").start()

        self.icon.run(setup=setup)

    def stop(self) -> None:
        self._stop.set()
        self.icon.stop()
