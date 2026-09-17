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
    # Empty means "not chosen yet": on the first run the language is taken from
    # Windows. Defaulting to a particular language would have shown Russian to
    # everyone who never opened the settings.
    "language": "",
    "autostart": False,
    "switch_communications": True,
    "sound_on_switch": False,
    # On by default, and it has to be. Switching sound is invisible: nothing on
    # screen moves, and the only other sign is the tray icon, which a person is
    # not looking at when they click it. Installed on a second machine with this
    # off, the program switched devices perfectly and read as broken — the click
    # did something, and nothing said so. The notification is the receipt.
    "notify_on_switch": True,
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
    #
    # On by default. Off, the program's own promise — that putting the headset on
    # moves everything, not half of it — was invisible until somebody found the
    # setting, and the microphones sat in the window looking like decoration.
    # This is the one default that can interrupt a person mid-call, so it only
    # ever acts on a headset that has a microphone of its own, and it puts the
    # previous one back on the way out.
    "switch_microphone": True,
    # Watch the headset through its USB dongle. Needed only where the dongle is
    # always plugged in and Windows does not see the headset being switched on.
    "watch_dongle": False,
    # Dongles this copy of the program worked out for itself, "0951:16EA" -> rule.
    # A shipped model is nobody's to wait for: the wizard watches the headset be
    # switched on and off and writes down what changed, and the headset works
    # here from that moment on, release or no release.
    "dongle_rules": {},
    # The dock draws us instead of the tray. Set by the dock itself through the
    # bridge, not by anything in our own window: it is the dock that knows
    # whether it is there. The tray icon comes back by itself the moment the
    # dock stops asking — a program with no icon and no dock has no way out at
    # all, and that is not a state we are willing to leave anybody in.
    "dock_hosts_us": False,
    # Whether the tray icon stays while the dock is showing us. The dock used to
    # decide that on its own, and the icon simply vanished the moment a widget
    # appeared — the person had not chosen anything. It is theirs to choose, and
    # the tray icon stays unless they say otherwise: it is the one way in that
    # depends on nothing else running.
    "tray_with_dock": True,
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
        # Key by key, and each one has to be the shape the program expects. A
        # file that parses but says `"icons": [1, 2]` used to be taken at its
        # word, and the program then ran with no tray icon, an empty window and
        # a log filling five times a second — alive and useless, with nothing
        # to say why. Unknown keys and wrong shapes go back to the default, and
        # the log says which.
        kept, dropped = {}, []
        for k, v in raw.items():
            if k not in DEFAULTS:
                continue
            if type(v) is not type(DEFAULTS[k]):
                dropped.append(f"{k} ({type(v).__name__} where {type(DEFAULTS[k]).__name__} was expected)")
                continue
            kept[k] = v
        with self._lock:
            self._data = {**DEFAULTS, **kept}
        if dropped:
            _log.warning("settings ignored, back to their defaults: %s", "; ".join(dropped))
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
