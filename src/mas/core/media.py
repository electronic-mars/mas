"""Playback control: the same keys as on the keyboard.

Windows itself decides which player a media key is addressed to, and it decides
it with the same arbiter it uses to pick the "current session" for its own
flyout. Verified on this machine: with Spotify and a browser playing at the same
time, the key went to Spotify. So the accuracy here is the same as that of
Windows' own dedicated interface, and it costs nothing: no dependencies, no
threads, no COM.

This approach gives no feedback — there is no way to find out whether music is
playing. That is why the button in the interface shows the combined
"pause/play" sign, like the one on the keyboard, instead of lying about state.
"""
import ctypes
from ctypes import wintypes

from .. import log

_log = log.get("media")

user32 = ctypes.WinDLL("user32")

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

KEYS = {
    "play": 0xB3,       # VK_MEDIA_PLAY_PAUSE
    "next": 0xB0,       # VK_MEDIA_NEXT_TRACK
    "prev": 0xB1,       # VK_MEDIA_PREV_TRACK
}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p)]


class _INPUTUNION(ctypes.Union):
    # The size of the union is set by its largest member — MOUSEINPUT, 32 bytes.
    # Without padding the structure would come out shorter and SendInput would
    # reject it by size.
    _fields_ = [("ki", _KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def tap(action: str) -> bool:
    """Press and release a media key. Returns False if Windows refused.

    A refusal happens when the active window has a higher integrity level: an
    ordinary program cannot send input to a window started as administrator.
    """
    vk = KEYS.get(action)
    if vk is None:
        raise ValueError(f"unknown action: {action}")
    events = (_INPUT * 2)(
        _INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=_KEYBDINPUT(vk, 0, KEYEVENTF_EXTENDEDKEY, 0, None))),
        _INPUT(INPUT_KEYBOARD, _INPUTUNION(
            ki=_KEYBDINPUT(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0, None))),
    )
    sent = user32.SendInput(2, events, ctypes.sizeof(_INPUT))
    if sent != 2:
        _log.warning("key %s was not sent (events accepted: %s)", action, sent)
        return False
    return True
