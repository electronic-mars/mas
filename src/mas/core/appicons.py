"""Real application icons for the mixer.

They are pulled out of the exe through ExtractIconExW and put into a cache on
disk: extraction costs about one and a half milliseconds, but there is no point
doing it every time the mixer is shown.

Important: argtypes must be set for the Windows functions. Without them ctypes
truncates 64-bit handles to int and fails with OverflowError — verified.
"""
import ctypes
import hashlib
from ctypes import POINTER, Structure, byref, c_int, c_void_p, sizeof
from ctypes.wintypes import BOOL, DWORD, HANDLE, HBITMAP, HDC, LONG, UINT, WORD
from pathlib import Path

from .. import log
from ..paths import data_dir

_log = log.get("appicons")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
shell32 = ctypes.windll.shell32


class ICONINFO(Structure):
    _fields_ = [("fIcon", BOOL), ("xHotspot", DWORD), ("yHotspot", DWORD),
                ("hbmMask", HBITMAP), ("hbmColor", HBITMAP)]


class BITMAPINFOHEADER(Structure):
    _fields_ = [("biSize", DWORD), ("biWidth", LONG), ("biHeight", LONG),
                ("biPlanes", WORD), ("biBitCount", WORD), ("biCompression", DWORD),
                ("biSizeImage", DWORD), ("biXPelsPerMeter", LONG), ("biYPelsPerMeter", LONG),
                ("biClrUsed", DWORD), ("biClrImportant", DWORD)]


class BITMAPINFO(Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", DWORD * 3)]


shell32.ExtractIconExW.argtypes = [ctypes.c_wchar_p, c_int, POINTER(HANDLE), POINTER(HANDLE), UINT]
shell32.ExtractIconExW.restype = UINT
user32.GetIconInfo.argtypes = [HANDLE, POINTER(ICONINFO)]
user32.GetIconInfo.restype = BOOL
user32.DestroyIcon.argtypes = [HANDLE]
user32.DrawIconEx.argtypes = [HDC, c_int, c_int, HANDLE, c_int, c_int, UINT, HANDLE, UINT]
user32.DrawIconEx.restype = BOOL
user32.PrivateExtractIconsW.argtypes = [ctypes.c_wchar_p, c_int, c_int, c_int,
                                        POINTER(HANDLE), POINTER(UINT), UINT, DWORD]
user32.PrivateExtractIconsW.restype = UINT
gdi32.GetDIBits.argtypes = [HDC, HBITMAP, UINT, UINT, c_void_p, POINTER(BITMAPINFO), UINT]
gdi32.DeleteObject.argtypes = [HANDLE]
gdi32.CreateCompatibleDC.argtypes = [HDC]
gdi32.CreateCompatibleDC.restype = HDC
gdi32.DeleteDC.argtypes = [HDC]
gdi32.CreateDIBSection.argtypes = [HDC, POINTER(BITMAPINFO), UINT, POINTER(c_void_p), HANDLE, DWORD]
gdi32.CreateDIBSection.restype = HBITMAP
gdi32.SelectObject.argtypes = [HDC, HANDLE]
gdi32.SelectObject.restype = HANDLE

DI_NORMAL = 0x0003
# We ask for 64 px: the icons are shown large, and the headroom keeps them from
# going blurry on scaled displays. Windows itself returns the closest suitable
# size from the resource.
SIZE = 64


def cache_dir() -> Path:
    d = data_dir() / "iconcache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _mask_alpha(hicon, size: int):
    """Transparency of old icons lives not in the colour but in a separate mask:
    a one in the mask = the pixel is transparent."""
    from PIL import Image
    info = ICONINFO()
    if not user32.GetIconInfo(hicon, byref(info)):
        return None
    try:
        hdc = gdi32.CreateCompatibleDC(0)
        bi = BITMAPINFO()
        bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = size
        bi.bmiHeader.biHeight = -size
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = 0
        buf = (ctypes.c_char * (size * size * 4))()
        got = gdi32.GetDIBits(hdc, info.hbmMask, 0, size, buf, byref(bi), 0)
        gdi32.DeleteDC(hdc)
        if not got:
            return None
        mask = Image.frombuffer("RGBA", (size, size), bytes(buf), "raw", "BGRA", 0, 1)
        return mask.convert("L").point(lambda v: 0 if v > 127 else 255)
    finally:
        gdi32.DeleteObject(info.hbmColor)
        gdi32.DeleteObject(info.hbmMask)


def _render(hicon, size: int):
    """Draw the icon through DrawIconEx into a 32-bit DIB.

    I used to read the colour bitmap directly — that lost the transparency and
    shifted the picture. DrawIconEx applies the mask and the scaling itself.
    """
    from PIL import Image
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = size
    bi.bmiHeader.biHeight = -size          # rows top to bottom
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0

    bits = c_void_p()
    hdc = gdi32.CreateCompatibleDC(0)
    dib = gdi32.CreateDIBSection(hdc, byref(bi), 0, byref(bits), None, 0)
    if not dib:
        gdi32.DeleteDC(hdc)
        return None
    old = gdi32.SelectObject(hdc, dib)
    try:
        ctypes.memset(bits, 0, size * size * 4)
        if not user32.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, None, DI_NORMAL):
            return None
        raw = ctypes.string_at(bits, size * size * 4)
        img = Image.frombuffer("RGBA", (size, size), raw, "raw", "BGRA", 0, 1)
        if img.getchannel("A").getextrema()[1] == 0:
            alpha = _mask_alpha(hicon, size)
            if alpha is None:
                return None
            img.putalpha(alpha)
        return img
    finally:
        gdi32.SelectObject(hdc, old)
        gdi32.DeleteObject(dib)
        gdi32.DeleteDC(hdc)


def _extract(exe_path: str):
    """PrivateExtractIcons returns an icon of the requested size from the
    resource, not the system "large" size that then has to be stretched."""
    hicons = (HANDLE * 1)()
    ids = (UINT * 1)()
    if user32.PrivateExtractIconsW(exe_path, 0, SIZE, SIZE, hicons, ids, 1, 0) and hicons[0]:
        try:
            return _render(hicons[0], SIZE)
        finally:
            user32.DestroyIcon(hicons[0])

    large = (HANDLE * 1)()
    small = (HANDLE * 1)()
    if shell32.ExtractIconExW(exe_path, 0, large, small, 1) == 0 or not large[0]:
        return None
    try:
        return _render(large[0], SIZE)
    finally:
        for h in (large[0], small[0]):
            if h:
                user32.DestroyIcon(h)


def key_for(exe_path: str) -> str:
    return hashlib.sha1(exe_path.lower().encode("utf-8")).hexdigest()[:16]


def ensure(exe_path: str | None) -> str | None:
    """Returns the file name in the cache, or None if there is no icon.

    Applications without an icon (UWP, system, inaccessible) are a normal thing,
    not an error: the interface shows a fallback letter for them.
    """
    if not exe_path:
        return None
    name = f"{key_for(exe_path)}.png"
    path = cache_dir() / name
    if path.is_file():
        return name
    try:
        img = _extract(exe_path)
        if img is None or img.getchannel("A").getextrema()[1] == 0:
            return None
        img.save(path, "PNG")
        return name
    except Exception:
        _log.warning("icon was not extracted: %s", exe_path, exc_info=True)
        return None
