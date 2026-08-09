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


def _command() -> str:
    """A flag in the command is the only way to tell an autostart from a manual
    launch: Windows gives the application no such indication."""
    if is_frozen():
        return f'"{Path(sys.executable)}" {STARTUP_FLAG}'
    return f'"{Path(sys.executable)}" -m mas {STARTUP_FLAG}'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, VALUE_NAME)
        return True
    except OSError:
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
