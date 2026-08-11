"""Autostart via the current user's Run key — no administrator rights needed."""
import sys
import winreg
from pathlib import Path

from .. import log
from ..paths import is_frozen

_log = log.get("startup")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "MasterAudioSwitcher"


STARTUP_FLAG = "--startup"

# The foreign command we have already complained about, so we complain once.
_warned_about: str | None = None


def _command() -> str:
    """A flag in the command is the only way to tell an autostart from a manual
    launch: Windows gives the application no such indication."""
    if is_frozen():
        return f'"{Path(sys.executable)}" {STARTUP_FLAG}'
    return f'"{Path(sys.executable)}" -m mas {STARTUP_FLAG}'


def _normalise(command: str) -> str:
    """A command reduced to something two of them can be compared by.

    The executable is resolved to a real path, because the same program reached
    through a different folder is still the same program, and Windows does not
    care about letter case in either.
    """
    command = command.strip()
    if command.startswith('"'):
        exe, _, rest = command[1:].partition('"')
    else:
        exe, _, rest = command.partition(" ")
    try:
        exe = str(Path(exe).resolve())
    except OSError:
        pass
    return f"{exe} {rest.strip()}".strip().casefold()


def is_enabled() -> bool:
    """Is *this* copy the one Windows starts?

    Whether the entry exists is not the question. It outlives the program being
    moved, rebuilt somewhere else or installed a second time, and then Windows
    goes on starting a copy that is not this one — or nothing at all, if that
    copy is gone. Answering "autostart is on" to that is a lie, and the kind
    that hides an old version quietly starting every morning.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            value = winreg.QueryValueEx(k, VALUE_NAME)[0]
    except OSError:
        return False
    if _normalise(str(value)) == _normalise(_command()):
        return True
    # Said once. This is asked on every refresh of the window, and the same
    # warning three times a second buries everything else in the log.
    global _warned_about
    if _warned_about != value:
        _warned_about = value
        _log.warning("autostart starts another copy, not this one: %s", value)
    return False


def set_enabled(enabled: bool) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(k, VALUE_NAME)
                except FileNotFoundError:
                    pass
        _log.info("autostart %s", "enabled" if enabled else "disabled")
        return True
    except OSError:
        _log.exception("could not change the autostart setting")
        return False
