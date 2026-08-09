"""Settings live in %LOCALAPPDATA% so a program update does not wipe the choices."""
import json
import threading
from typing import Any

from .. import log
from ..paths import config_path

_log = log.get("config")

DEFAULTS: dict[str, Any] = {
    # Cycle order: a user-defined list of output device identifiers.
    # The order is stored in full, including devices that are absent right now —
    # that is exactly what keeps the cycle from shifting when the headphones run
    # out of battery or the laptop is taken out of its dock.
    "cycle": [],
    "mic_favorites": [],
    "icons": {},          # device id -> silhouette name
    "language": "ru",
    "autostart": False,
    "switch_communications": True,
    "sound_on_switch": False,
    "notify_on_switch": False,
    "theme": "system",        # system | dark | light
    # Which button switches the sound. The other one opens the window — they swap
    # together, there is no separate setting for the window.
    "switch_button": "left",  # left | right
    # Hotkey for switching the sound, for example "Ctrl+Alt+H". Empty — disabled.
    "hotkey": "",
    # The player every media command is addressed to, whatever else is going on,
    # by its system id. Starting it pauses the others. Empty — we work out the
    # target ourselves, which is the older and less predictable behaviour.
    "priority_player": "",
    # A combination that starts or pauses that player without opening the window.
    # The keyboard's own play key cannot be used: Windows gives it to whichever
    # player it considers current, and that is exactly what is being avoided.
    "hotkey_play": "",
    # A device that takes over the sound as soon as it appears in the system and
    # hands it back when it disappears. Empty — the usual behaviour.
    "auto_device": "",
    # Switch the microphone together with the headphones: recording moves to the
    # microphone of the same headset, and going back to the speakers restores the
    # previous microphone.
    "switch_microphone": False,
    # Watch the headset through its USB dongle. Needed only where the dongle is
    # always plugged in and Windows does not see the headset being switched on.
    "watch_dongle": False,
    # Write the reports of an unknown dongle to a file so its model can be added
    # from them. Nothing is sent anywhere, the file sits next to the settings.
    "learn_dongle": False,
    "mics_expanded": False,   # the microphone section is collapsed by default
    "onboarded": False,
}


class Config:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        path = config_path()
        if not path.is_file():
            _log.info("no settings yet, using the defaults")
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _log.exception("settings cannot be read, using the defaults")
            return
        with self._lock:
            self._data = {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}
        _log.info("settings loaded")

    def save(self) -> None:
        path = config_path()
        tmp = path.with_suffix(".json.tmp")
        with self._lock:
            data = dict(self._data)
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)  # write via a temp file: a crash leaves no broken config
        except OSError:
            _log.exception("settings were not saved")

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(f"unknown setting: {key}")
        with self._lock:
            self._data[key] = value
        self.save()

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)
