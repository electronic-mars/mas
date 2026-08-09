"""Checking tray gestures without a mouse.

A tray icon cannot be clicked by automation, so the mouse message is sent
straight to the pystray window. The real handler of the live process fires for
real — the result is visible in the program log.

Usage: poke_tray.py left|right|middle
"""
import ctypes
import sys
from ctypes import wintypes

WM_NOTIFY = 1035
BUTTONS = {"left": 0x0202, "right": 0x0205, "middle": 0x0208}

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def tray_windows() -> list[int]:
    found: list[int] = []

    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if "SystemTrayIcon" in buf.value:
            found.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "left"
    if which not in BUTTONS:
        print(f"need one of: {', '.join(BUTTONS)}")
        return 2

    hwnds = tray_windows()
    if not hwnds:
        print("tray window not found — is the program running?")
        return 1

    for hwnd in hwnds:
        user32.PostMessageW(hwnd, WM_NOTIFY, 0, BUTTONS[which])
    print(f"sent {which} to windows: {len(hwnds)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
