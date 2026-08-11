"""Wherever the user's taskbar is, that is where our windows go.

People get used to all notifications popping up in one corner. The taskbar can
be put against any edge, so we compute the corner instead of assuming it is the
bottom right one.
"""
import ctypes
from ctypes import wintypes

from .. import log

_log = log.get("screen")

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

# A window handle is a handle, not an int. Undeclared, ctypes cuts whatever
# comes back down to 32 bits — harmless for window handles, which Windows
# promises will fit, and not harmless at all for the module handle next door,
# where the same omission cost this program an access violation on every run.
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]

ABM_GETTASKBARPOS = 0x00000005
SPI_GETWORKAREA = 0x0030
EDGES = {0: "left", 1: "top", 2: "right", 3: "bottom"}
# Below this the window stops being a window: the front panel alone is 250
# points, and squeezing the device list to nothing defeats the whole program.
MIN_HEIGHT = 420


class _APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uCallbackMessage", wintypes.UINT), ("uEdge", wintypes.UINT),
                ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]


shell32.SHAppBarMessage.restype = ctypes.c_size_t
shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(_APPBARDATA)]


def taskbar() -> tuple[str, wintypes.RECT | None]:
    """The edge the taskbar is docked to, and its rectangle."""
    data = _APPBARDATA()
    data.cbSize = ctypes.sizeof(_APPBARDATA)
    if not shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(data)):
        return "bottom", None       # no taskbar found — behave as usual
    return EDGES.get(data.uEdge, "bottom"), data.rc


def work_area() -> wintypes.RECT:
    """The screen minus the taskbar — nothing may stick out beyond it."""
    rc = wintypes.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rc), 0)
    return rc


def dpi_scale() -> float:
    """Physical pixels per logical point, as a factor."""
    get = getattr(user32, "GetDpiForSystem", None)     # Windows 10 1607 and up
    return ((get() if get else 0) or 96) / 96


def fit_height(desired: int, margin: int = 12) -> int:
    """The tallest window that still fits the screen, in logical points.

    Window sizes are given to pywebview in logical points and multiplied by the
    display scale, while the work area comes back in physical pixels — so the
    two have to be brought to the same units before they can be compared.

    Measured on our own machine the work area is 1540 points, which is why the
    full 772 always fitted and this was never visible here. On a 1366x768 laptop
    the work area is about 728 points: 44 are cut off at 100% and 237 at 125%,
    and there is nothing the user can do about it, because the window cannot be
    resized. The content itself scrolls, so a shorter window loses nothing.
    """
    wa = work_area()
    room = int((wa.bottom - wa.top) / dpi_scale()) - margin * 2
    return max(MIN_HEIGHT, min(desired, room))


def own_window(title: str) -> int | None:
    """Our main window by title, with a check that it really is ours."""
    import os
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return hwnd if pid.value == os.getpid() else None


def place_at_tray(hwnd: int, margin: int = 12) -> bool:
    """Move the window to the corner where the user's tray is."""
    rc = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rc)):
        return False
    x, y = anchor(rc.right - rc.left, rc.bottom - rc.top, margin)
    return bool(user32.SetWindowPos(wintypes.HWND(hwnd), None, x, y, 0, 0,
                                    0x0001 | 0x0004))   # SWP_NOSIZE | SWP_NOZORDER


def resize_at_tray(hwnd: int, width: int, height: int, margin: int = 12) -> bool:
    """A new size and a new corner in a single move.

    If you resize first and only then move the window to the tray, the two-step
    jump is visible to the eye. And the corner has to be computed from the new
    height: with the taskbar at the bottom the window holds on to the bottom
    edge, while resizing pulls the top one.
    """
    scale = (user32.GetDpiForWindow(wintypes.HWND(hwnd)) or 96) / 96
    pw, ph = int(width * scale), int(height * scale)
    x, y = anchor(pw, ph, margin)
    return bool(user32.SetWindowPos(wintypes.HWND(hwnd), None, x, y, pw, ph, 0x0004))


def anchor(width: int, height: int, margin: int = 12) -> tuple[int, int]:
    """Top-left corner of a width x height window docked to the tray.

    The tray icon sits at the far end of the taskbar, so we put the window in
    the same corner: with the taskbar at the bottom — bottom right, at the top —
    top right, at a side — right next to the taskbar.
    """
    edge, bar = taskbar()
    wa = work_area()
    if edge == "left":
        x, y = wa.left + margin, wa.bottom - height - margin
    elif edge == "right":
        x, y = wa.right - width - margin, wa.bottom - height - margin
    elif edge == "top":
        x, y = wa.right - width - margin, wa.top + margin
    else:
        x, y = wa.right - width - margin, wa.bottom - height - margin
    # Just in case, keep the window inside the work area: people do have screens
    # where the taskbar is wider than one would expect.
    x = max(wa.left, min(x, wa.right - width))
    y = max(wa.top, min(y, wa.bottom - height))
    return x, y
