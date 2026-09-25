"""Our own overlay instead of a Windows notification.

A Windows notification cannot be styled, it is signed with the program name and
piles up in the notification centre. Something else is needed: a card with the
device, what it is and its volume — it appears, hangs for a second and a half,
dissolves. The same card comes up while the pointer rests on the tray icon, in
place of the system tooltip, with the track underneath.

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
k32 = ctypes.WinDLL("kernel32")

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
# Undeclared, ctypes assumes a function returns a 32-bit int. A module handle is
# the address the executable is loaded at, and on 64-bit Windows that is a
# 64-bit number: 0x7FF67BC00000 came back as 0x7BC00000, with the top half
# thrown away. Windows then dereferenced that garbage while registering the
# class and creating the window — an access violation on every run, sometimes
# three, always in this thread. It never killed the program because Windows
# handles it, and the address is randomised at boot, so how far it went wrong
# differed from morning to morning. Declared, it is simply correct.
k32.GetModuleHandleW.restype = wintypes.HMODULE
k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClassW.restype = wintypes.ATOM
user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASS)]
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


def _font(size: int, weight: str = "regular"):
    from PIL import ImageFont
    names = {"regular": ("segoeui.ttf", "arial.ttf"),
             "semibold": ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"),
             "bold": ("segoeuib.ttf", "arialbd.ttf")}[weight]
    for name in names:
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


# The card, in panel units (multiplied by the screen scale when drawn). The same
# picture serves the notification after a switch and the card shown while the
# pointer rests on the tray icon; the notification adds a caption on top, the
# hover card the track underneath.
CARD_W, CARD_PAD, CARD_R, SHADOW = 340, 14, 14, 12
WELL, LAMPS, LAMP_H, LAMP_GAP = 40, 20, 5, 3
ORANGE = (242, 106, 33, 255)


def _palette(light: bool) -> dict:
    if light:
        return {"bg": (247, 245, 241, 250), "line": (0, 0, 0, 30), "well": (233, 229, 221, 255),
                "tx": (35, 38, 43, 255), "tx2": (92, 97, 105, 255), "tx3": (98, 104, 113, 255),
                "off": (0, 0, 0, 24), "shadow": 70}
    return {"bg": (28, 31, 36, 248), "line": (255, 255, 255, 26), "well": (18, 20, 24, 255),
            "tx": (233, 236, 241, 255), "tx2": (152, 160, 172, 255), "tx3": (136, 144, 155, 255),
            "off": (255, 255, 255, 26), "shadow": 120}


def _render(card: dict, light: bool, k: float | None = None):
    """The card as an image, shadow included. `card` holds glyph, title, sub,
    pct (None for no volume), muted, and optionally caption and track."""
    from PIL import Image, ImageDraw, ImageFilter

    k = scale() if k is None else k
    px = lambda v: int(round(v * k))         # noqa: E731 — panel units to screen pixels
    c = _palette(light)
    pad, w, sh = px(CARD_PAD), px(CARD_W), px(SHADOW)
    f_cap, f_title, f_sub = _font(px(9.5), "bold"), _font(px(15), "semibold"), _font(px(12.5))
    f_pct, f_unit, f_track = _font(px(22), "semibold"), _font(px(12)), _font(px(12.5))
    f_track_b = _font(px(12.5), "semibold")

    cap_h = px(21) if card.get("caption") else 0
    head_h = px(WELL)
    lamps_top = cap_h + head_h + px(14)
    track = card.get("track")
    h = lamps_top + px(LAMP_H) + (px(26) if track else 0) + 2 * pad

    img = Image.new("RGBA", (w + 2 * sh, h + 2 * sh), (0, 0, 0, 0))
    # A soft shadow under the card: without one a borderless panel floats on
    # the desktop with nothing to say where it ends.
    shadow = Image.new("L", img.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((sh, sh + px(3), sh + w, sh + h + px(3)),
                                             radius=px(CARD_R), fill=c["shadow"])
    shadow = shadow.filter(ImageFilter.GaussianBlur(px(6)))
    img.putalpha(shadow)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((sh, sh, sh + w - 1, sh + h - 1), radius=px(CARD_R),
                        fill=c["bg"], outline=c["line"], width=1)
    x0, y = sh + pad, sh + pad

    if card.get("caption"):
        text = card["caption"].upper()
        cx = x0 + px(2)
        for ch in text:                       # letter-spaced by hand: PIL has no tracking
            d.text((cx, y), ch, font=f_cap, fill=c["tx3"])
            cx += d.textlength(ch, font=f_cap) + px(1.4)
        y += cap_h

    # the icon well
    d.rounded_rectangle((x0, y, x0 + head_h, y + head_h), radius=px(10), fill=c["well"])
    glyph = card.get("glyph")
    if glyph:
        icon = px(26)
        path = _icon_file(glyph, light, icon)
        if path is not None:
            with Image.open(path) as raw:
                ic = raw.convert("RGBA")
            if ic.width != icon:
                ic = ic.resize((icon, icon), Image.LANCZOS)
            img.alpha_composite(ic, (x0 + (head_h - icon) // 2, y + (head_h - icon) // 2))

    # the volume on the right
    right = sh + w - pad
    pct = card.get("pct")
    text_right = right
    if pct is not None:
        unit_w = d.textlength("%", font=f_unit)
        num = str(pct)
        num_w = d.textlength(num, font=f_pct)
        base = y + head_h // 2 + px(8)
        d.text((right - unit_w, base), "%", font=f_unit, fill=c["tx3"], anchor="ls")
        d.text((right - unit_w - px(1) - num_w, base), num, font=f_pct,
               fill=c["tx3"] if card.get("muted") else c["tx"], anchor="ls")
        text_right = right - unit_w - num_w - px(14)

    # the name and what it is
    tx = x0 + head_h + px(12)
    room = text_right - tx
    title = _fit(card.get("title") or "", f_title, room, d)
    sub = _fit(card.get("sub") or "", f_sub, room, d)
    if sub:
        d.text((tx, y + head_h // 2 - px(2)), title, font=f_title, fill=c["tx"], anchor="ls")
        d.text((tx, y + head_h // 2 + px(5)), sub, font=f_sub, fill=c["tx2"], anchor="lt")
    else:
        d.text((tx, y + head_h // 2), title, font=f_title, fill=c["tx"], anchor="lm")

    # the lamps: one per five percent, the same count the volume says
    y = sh + pad + lamps_top
    lamp_w = (w - 2 * pad - (LAMPS - 1) * px(LAMP_GAP)) / LAMPS
    lit = 0 if card.get("muted") or pct is None else (max(1, round(pct / 5)) if pct > 0 else 0)
    for i in range(LAMPS):
        lx = x0 + i * (lamp_w + px(LAMP_GAP))
        d.rounded_rectangle((lx, y, lx + lamp_w, y + px(LAMP_H)), radius=px(1.5),
                            fill=ORANGE if i < lit else c["off"])

    if track:
        y += px(LAMP_H) + px(12)
        bars = ((6, 0), (10, 1), (4, 2), (8, 3))
        for bh, i in bars:
            bx = x0 + i * px(3.5)
            d.rounded_rectangle((bx, y + px(12) - px(bh), bx + px(2), y + px(12)), radius=px(1), fill=ORANGE)
        tx = x0 + px(20)
        name, artist = track
        name = _fit(name, f_track_b, w - 2 * pad - px(20), d)
        d.text((tx, y + px(12)), name, font=f_track_b, fill=c["tx"], anchor="ls")
        if artist:
            used = d.textlength(name, font=f_track_b)
            rest = _fit(f" — {artist}", f_track, w - 2 * pad - px(20) - used, d)
            d.text((tx + used, y + px(12)), rest, font=f_track, fill=c["tx2"], anchor="ls")
    return img


def _premultiplied(img) -> bytes:
    """A layered window expects colour already multiplied by alpha, in BGRA
    order, rows bottom-up.

    PIL has a raw mode for exactly that, "BGRa", and it runs in C. The loop it
    replaced walked every pixel in Python: 12.5 ms per frame, eighteen frames
    per fade, 226 ms of processor for every notification — measured. This is
    0.14 ms, and the bytes differ by at most one from rounding.
    """
    from PIL import Image
    return img.transpose(Image.FLIP_TOP_BOTTOM).tobytes("raw", "BGRa")


class _PT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def _cursor() -> tuple[int, int]:
    p = _PT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


# Hovering the tray icon: the card comes up once the pointer has rested this
# long — two seconds, not half of one: at half a second it came up on every pass
# of the pointer towards the clock and got in the way more than it helped, and goes the moment the pointer leaves the icon. Windows says nothing
# when the pointer leaves, only while it moves over the icon, so "left" means
# "moved further than an icon's width from where it last moved over it".
HOVER_DELAY = 2.0
HOVER_MAX = 12.0


class Overlay(threading.Thread):
    """A single overlay window for the whole session, with its own message loop."""

    def __init__(self, hover_card=None):
        """`hover_card` returns (card, light) for the card shown on hover, or
        None when there is nothing to show."""
        super().__init__(daemon=True, name="mas-overlay")
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._hwnd = None
        self._proc = WNDPROC(lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l))
        self._hover_card = hover_card
        self._hover_at: tuple[int, int] | None = None   # where it last moved over the icon
        self._hover_waiting = False

    def show(self, card: dict, light: bool = False) -> None:
        self._queue.put(("note", card, light))

    def hover(self) -> None:
        """The pointer moved over the tray icon. Called for every move — cheap."""
        self._hover_at = _cursor()
        if not self._hover_waiting:
            self._hover_waiting = True
            self._queue.put(("hover", None, None))

    def unhover(self) -> None:
        """A click on the icon: whatever it does, the card is in the way."""
        self._hover_at = None

    # --- internals --------------------------------------------------
    def _create(self) -> None:
        wc = _WNDCLASS()
        wc.lpfnWndProc = self._proc
        wc.hInstance = k32.GetModuleHandleW(None)
        wc.lpszClassName = "MasOverlay"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            # Said out loud: without the class there is no window, and a
            # notification that never appears looks like a setting that does
            # nothing rather than like something broken.
            _log.warning("overlay window class was not registered (error %s)",
                         k32.GetLastError())
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

    def _put_up(self, img):
        # The image carries its shadow as a margin: the card itself is what sits
        # in the corner, the shadow spills past it.
        sh = int(round(SHADOW * scale()))
        x, y = screen.anchor(img.width - 2 * sh, img.height - 2 * sh)
        x, y = x - sh, y - sh
        self._paint(img, 255, x, y)
        user32.SetWindowPos(self._hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        return x, y

    def _fade(self, img, x, y, seconds) -> None:
        start = time.monotonic()
        while True:
            k = (time.monotonic() - start) / seconds
            if k >= 1 or not self._queue.empty():
                break
            self._paint(img, int(255 * (1 - k)), x, y)
            self._pump()
            time.sleep(0.02)
        user32.ShowWindow(self._hwnd, SW_HIDE)

    def _note(self, card, light) -> None:
        img = _render(card, light)
        x, y = self._put_up(img)
        # Hold it, then fade it out with constant alpha: there is no need to redraw
        # the image, only one blend byte changes.
        deadline = time.monotonic() + HOLD
        while time.monotonic() < deadline:
            if not self._queue.empty():
                return                      # a new one came — no point watching the old
            self._pump()
            time.sleep(0.03)
        self._fade(img, x, y, FADE)

    def _near(self) -> bool:
        at = self._hover_at
        if at is None:
            return False
        cx, cy = _cursor()
        reach = 20 * scale()
        return abs(cx - at[0]) <= reach and abs(cy - at[1]) <= reach

    def _hover(self) -> None:
        try:
            # Resting, not passing through: the pointer must stay on the icon.
            deadline = time.monotonic() + HOVER_DELAY
            while time.monotonic() < deadline:
                if not self._near() or not self._queue.empty():
                    return
                time.sleep(0.03)
            got = self._hover_card() if self._hover_card else None
            if not got:
                return
            card, light = got
            img = _render(card, light)
            x, y = self._put_up(img)
            until = time.monotonic() + HOVER_MAX
            while self._near() and time.monotonic() < until and self._queue.empty():
                self._pump()
                time.sleep(0.04)
            if self._queue.empty():
                self._fade(img, x, y, 0.15)
        finally:
            self._hover_waiting = False

    def run(self) -> None:
        self._create()
        if not self._hwnd:
            _log.warning("overlay window was not created")
            return
        while True:
            job = self._queue.get()
            while not self._queue.empty():      # show only the latest one
                job = self._queue.get()
            if job[0] != "hover":
                self._hover_waiting = False     # a dropped hover must not block the next
            try:
                if job[0] == "note":
                    self._note(job[1], job[2])
                else:
                    self._hover()
            except Exception:
                _log.exception("overlay failed to show")
                user32.ShowWindow(self._hwnd, SW_HIDE)
