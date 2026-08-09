"""Application paths. In a built exe resources sit next to it, not in the sources."""
import os
import sys
from pathlib import Path

APP_NAME = "MasterAudioSwitcher"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """Folder holding ui/, the locales and the icons."""
    if is_frozen():
        return Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(sys.executable).parent
    return Path(__file__).resolve().parent


def ui_dir() -> Path:
    """The one place where the path to the interface and the icons is defined."""
    return resource_dir() / "ui"


def icons_dir() -> Path:
    return ui_dir() / "icons"


def data_dir() -> Path:
    """%LOCALAPPDATA%\\MasterAudioSwitcher — settings survive a program update."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path() -> Path:
    return data_dir() / "mas.log"


def config_path() -> Path:
    return data_dir() / "config.json"


def learn_path() -> Path:
    """Reports from an unknown dongle. The file stays on disk and goes nowhere."""
    return data_dir() / "dongle-learn.txt"
