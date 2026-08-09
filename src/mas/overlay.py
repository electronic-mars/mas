"""Our own overlay instead of a Windows notification.

A Windows notification cannot be styled, it is signed with the program name and
piles up in the notification centre. Something else is needed: the device icon,
its name and nothing more — it appears, hangs for a second and a half, dissolves.

We draw it in PIL and show it in a layered window with per-pixel transparency. The
window takes no focus and lets clicks through: it asks nothing, it only tells.
"""
import ctypes
import queue
import threading
import time
from ctypes import wintypes

from . import log
from .core import screen
from .paths import icons_dir

_log = log.get("overlay")

# Our own library instances rather than the shared ctypes.windll: the type
# descriptions there are already set by the app-icons module for its own
# structures, and ours would clash with them.
user32 = ctypes.WinDLL("user32")
gdi32 = ctypes.WinDLL("gdi32")

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
ULW_ALPHA = 0x00000002
AC_SRC_OVER, AC_SRC_ALPHA = 0x00, 0x01
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
SW_HIDE = 0

HOLD = 1.4      # seconds we keep it in view
FADE = 0.35     # seconds it takes to dissolve
PAD, ICON, GAP = 18, 32, 14
HEIGHT = 74
MIN_W, MAX_W = 240, 460
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64)   # which glyph files exist on disk


def scale() -> float:
    """Screen scaling. The overlay is drawn in real pixels, not in layout units,
    so at 125% we have to enlarge it ourselves — otherwise it comes out smaller
    than the rest of the interface, and the icon in it twice as coarse."""
    try:
        dpi = user32.GetDpiForSystem()
    except AttributeError:
        return 1.0                          # Windows older than 10 version 1607
    return max(1.0, min(3.0, dpi / 96))


def _icon_file(glyph: str, light: bool, want: int):
    """A glyph file no smaller than needed: a stretched icon shows at once."""
    kind = "light" if light else "dark"
    for size in ICON_SIZES:
        if size >= want:
            path = icons_dir() / "devices" / f"{glyph}_{kind}_{size}.png"
            if path.is_file():
                return path
    return None


def _fit(text: str, font, limit: int, draw) -> str:
    """Cut the name with an ellipsis: some devices have a name a whole line long,
    and it used to run past the panel edge, breaking off in the middle of a letter."""
    if draw.textlength(text, font=font) <= limit:
        return text
    ell = "…"
    while text and draw.textlength(text + ell, font=font) > limit:
        text = text[:-1]
    return text.rstrip() + ell


class _BLEND(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class _BMIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class _BMI(ctypes.Structure):
    _fields_ = [("bmiHeader", _BMIH), ("bmiColors", wintypes.DWORD * 3)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class _WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(_BMI), wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE,
                                   wintypes.DWORD]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(_POINT),
                                       ctypes.POINTER(_SIZE), wintypes.HDC,
                                       ctypes.POINTER(_POINT), wintypes.DWORD,
                                       ctypes.POINTER(_BLEND), wintypes.DWORD]


def _font(size: int):
    from PIL import ImageFont
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render(glyph: str | None, text: str, light: bool, k: float | None = None):
    """The panel as an image: rounded rectangle, icon, name."""
    from PIL import Image, ImageDraw

    k = scale() if k is None else k
    px = lambda v: int(round(v * k))         # noqa: E731 — panel units to screen pixels
    pad, icon, gap, height = px(PAD), px(ICON), px(GAP), px(HEIGHT)

    font = _font(px(17))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    room = px(MAX_W) - pad - icon - gap - pad
    text = _fit(text, font, room, probe)
    tw = int(probe.textlength(text, font=font))
    width = max(px(MIN_W), min(px(MAX_W), pad + icon + gap + tw + pad))

    bg = (247, 245, 241, 245) if light else (28, 31, 36, 242)
    fg = (35, 38, 43, 255) if light else (233, 236, 241, 255)
    line = (0, 0, 0, 38) if light else (255, 255, 255, 30)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, width - 1, height - 1), radius=px(16), fill=bg,
                        outline=line, width=1)

    if glyph:
        path = _icon_file(glyph, light, icon)
        if path is not None:
            with Image.open(path) as raw:
                ic = raw.convert("RGBA")
            if ic.width != icon:
                ic = ic.resize((icon, icon), Image.LANCZOS)
            img.alpha_composite(ic, (pad, (height - icon) // 2))

    # Vertically the name is placed on the icon's middle line, not on the font's
    # baseline: the font has varying ascenders, and the text would "jump" from one
    # name to the next.
    d.text((pad + icon + gap, height // 2), text, font=font, fill=fg, anchor="lm")
    return img


def _premultiplied(img) -> bytes:
    """A layered window expects colour already multiplied by alpha, in BGRA order."""
    out = bytearray(img.width * img.height * 4)
    px = img.load()
    i = 0
    for y in range(img.height - 1, -1, -1):        # raster bottom-up
        for x in range(img.width):
            r, g, b, a = px[x, y]
            out[i] = b * a // 255
            out[i + 1] = g * a // 255
            out[i + 2] = r * a // 255
            out[i + 3] = a
            i += 4
    return bytes(out)


class Overlay(threading.Thread):
    """A single overlay window for the whole session, with its own message loop."""

    def __init__(self):
        super().__init__(daemon=True, name="mas-overlay")
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._hwnd = None
        self._proc = WNDPROC(lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l))

    def show(self, glyph: str | None, text: str, light: bool = False) -> None:
        self._queue.put((glyph, text, light))

    # --- internals --------------------------------------------------
    def _create(self) -> None:
        wc = _WNDCLASS()
        wc.lpfnWndProc = self._proc
        wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
        wc.lpszClassName = "MasOverlay"
        user32.RegisterClassW(ctypes.byref(wc))
        self._hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
            | WS_EX_TOPMOST | WS_EX_NOACTIVATE,
            "MasOverlay", "", WS_POPUP, 0, 0, 0, 0, None, None, wc.hInstance, None)

    def _paint(self, img, alpha: int, x: int, y: int) -> None:
        w, h = img.width, img.height
        bits = _premultiplied(img)
        screen_dc = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bmi = _BMI()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BMIH)
        bmi.bmiHeader.biWidth, bmi.bmiHeader.biHeight = w, h
        bmi.bmiHeader.biPlanes, bmi.bmiHeader.biBitCount = 1, 32
        ptr = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0,
                                        ctypes.byref(ptr), None, 0)
        ctypes.memmove(ptr, bits, len(bits))
        old = gdi32.SelectObject(mem_dc, bitmap)
        blend = _BLEND(AC_SRC_OVER, 0, alpha, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(self._hwnd, screen_dc, ctypes.byref(_POINT(x, y)),
                                   ctypes.byref(_SIZE(w, h)), mem_dc,
                                   ctypes.byref(_POINT(0, 0)), 0,
                                   ctypes.byref(blend), ULW_ALPHA)
        gdi32.SelectObject(mem_dc, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)

    def _pump(self) -> None:
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _display(self, glyph, text, light) -> None:
        img = _render(glyph, text, light)
        x, y = screen.anchor(img.width, img.height)
        self._paint(img, 255, x, y)
        user32.SetWindowPos(self._hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        # Hold it, then fade it out with constant alpha: there is no need to redraw
        # the image, only one blend byte changes.
        deadline = time.monotonic() + HOLD
        while time.monotonic() < deadline:
            if not self._queue.empty():
                return                      # a new one came — no point watching the old
            self._pump()
            time.sleep(0.03)
        start = time.monotonic()
        while True:
            k = (time.monotonic() - start) / FADE
            if k >= 1 or not self._queue.empty():
                break
            self._paint(img, int(255 * (1 - k)), x, y)
            self._pump()
            time.sleep(0.02)
        user32.ShowWindow(self._hwnd, SW_HIDE)

    def run(self) -> None:
        self._create()
        if not self._hwnd:
            _log.warning("overlay window was not created")
            return
        while True:
            glyph, text, light = self._queue.get()
            while not self._queue.empty():      # show only the latest one
                glyph, text, light = self._queue.get()
            try:
                self._display(glyph, text, light)
            except Exception:
                _log.exception("overlay failed to show")
