"""Global hotkey.

RegisterHotKey delivers WM_HOTKEY to the very thread that registered the
combination, so registration and the message loop must live in the same thread.
A change of combination arrives here as a separate message, not as a call from
the outside.
"""
import ctypes
import threading
from ctypes import byref, wintypes

from .. import log

_log = log.get("hotkey")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
MOD_NOREPEAT = 0x4000  # without it, holding the key showers us with switches
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
WM_REBIND = 0x0400 + 11  # our own message: "re-read the setting"

MODIFIERS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}

# The key names match those the interface produces when capturing a combination.
NAMED = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22, "ins": 0x2D, "del": 0x2E,
}

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]


def parse(combo: str) -> tuple[int, int] | None:
    """Parses "Ctrl+Alt+H" into (modifiers, key code). None if it cannot be parsed."""
    parts = [p.strip().lower() for p in str(combo).split("+") if p.strip()]
    if not parts:
        return None
    mods, key = 0, None
    for part in parts:
        if part in MODIFIERS:
            mods |= MODIFIERS[part]
        elif key is None:
            key = part
        else:
            return None  # two ordinary keys in one combination
    if key is None:
        return None
    # Latin letters and digits only: key codes match ASCII for those alone, and a
    # non-Latin key such as Cyrillic Yo would turn into a non-existent code 1025.
    if len(key) == 1 and key.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif key in NAMED:
        vk = NAMED[key]
    else:
        return None
    # A single key with no modifier takes it away from the whole system. The
    # exception is the function keys, which is what that separate row is for.
    if not mods and not (0x70 <= vk <= 0x87):
        return None
    return mods, vk


class Hotkeys(threading.Thread):
    """Several combinations at once, each with its own handler.

    Every combination needs its own identifier within the thread, and both the
    registration and the message loop stay on this one thread — so the names are
    fixed when the object is made, and only the combinations behind them change.
    """

    def __init__(self, handlers: dict, combos: dict | None = None):
        super().__init__(daemon=True, name="mas-hotkey")
        self._handlers = dict(handlers)              # name -> what to call
        self._wanted = {n: (combos or {}).get(n) or "" for n in self._handlers}
        self._ids = {n: i + 1 for i, n in enumerate(sorted(self._handlers))}
        self._tid = 0
        self._ready = threading.Event()
        # Per name: was the combination actually claimed. The interface says so
        # out loud, because a combination taken by another program looks exactly
        # like a broken one.
        self.ok = {n: True for n in self._handlers}

    def bind(self, name: str, combo: str) -> None:
        if name not in self._handlers:
            return
        self._wanted[name] = combo or ""
        if self.is_alive() and self._ready.wait(2.0) and self._tid:
            user32.PostThreadMessageW(self._tid, WM_REBIND, 0, 0)

    def stop(self) -> None:
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)

    def _apply(self) -> None:
        for name, hid in self._ids.items():
            user32.UnregisterHotKey(None, hid)
            combo = self._wanted[name]
            if not combo:
                self.ok[name] = True
                continue
            parsed = parse(combo)
            if parsed is None:
                self.ok[name] = False
                _log.warning("combination for %s not parsed: %s", name, combo)
                continue
            mods, vk = parsed
            self.ok[name] = bool(user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk))
            _log.info("combination %s for %s: %s", combo, name,
                      "claimed by us" if self.ok[name]
                      else "already taken by another program")

    def run(self) -> None:
        msg = wintypes.MSG()
        # A thread only gets a message queue after the first access to it, and
        # without a queue PostThreadMessageW loses messages.
        user32.PeekMessageW(byref(msg), None, 0, 0, 0)
        self._tid = kernel32.GetCurrentThreadId()
        self._apply()
        self._ready.set()
        by_id = {hid: name for name, hid in self._ids.items()}
        while user32.GetMessageW(byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                name = by_id.get(msg.wParam)
                try:
                    if name:
                        self._handlers[name]()
                except Exception:
                    _log.exception("handler of the %s hotkey crashed", name)
            elif msg.message == WM_REBIND:
                self._apply()
        for hid in self._ids.values():
            user32.UnregisterHotKey(None, hid)
