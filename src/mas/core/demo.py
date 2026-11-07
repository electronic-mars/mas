"""MAS_DEMO=1: a made-up sound setup, for the README and site recordings.

Nothing real is read or changed. The devices, the applications and the player
are invented; every volume starts at 21; a switch only moves the mark of which
device is the default. Settings live in a temporary folder and the program
speaks English.

The wireless headset is away at the start. A recording script brings it in by
creating the file HEADSET in the data folder, and takes it away by deleting
the file - the program sees it come and go the way it sees a real one.
"""
import json
import math
import os
import threading
import time

ON = os.environ.get("MAS_DEMO") == "1"

VOLUME = 0.21
HEADSET = "demo-headset"      # the file that switches the headset on

OUT = "{0.0.0.00000000}.{demo-%s}"
IN = "{0.0.1.00000000}.{demo-%s}"
SPEAKERS, HEADPHONES, MONITOR, WIRELESS = (OUT % k for k in ("speakers", "headphones", "monitor", "wireless"))
WEBCAM, WIRELESS_MIC = IN % "webcam", IN % "wireless-mic"

NAMES = {
    SPEAKERS: "Speakers (Demo Audio)",
    HEADPHONES: "Headphones (Demo Studio)",
    MONITOR: "Demo Display (Display Audio)",   # named the way screens are
    WIRELESS: "Headset (Demo Wireless)",
    WEBCAM: "Microphone (Demo Webcam)",
    WIRELESS_MIC: "Microphone (Demo Wireless)",
}
AWAY_AT_START = {WIRELESS, WIRELESS_MIC}

# Applications in the mixer: key, name a person reads, and how loud each one
# plays, so the level bars do not move in step.
APPS = [("music.exe", "Music", 0.9), ("browser.exe", "Browser", 0.55),
        ("game.exe", "Game", 0.7), ("chat.exe", "Voice Chat", 0.35)]


class Endpoint:
    """Stands in for both the volume and the meter interface of one device."""

    def __init__(self, loudness: float = 0.8):
        self.volume = VOLUME
        self.muted = False
        self.loudness = loudness
        self.phase = len(_endpoints) * 1.7

    def GetMasterVolumeLevelScalar(self) -> float:
        return self.volume

    def SetMasterVolumeLevelScalar(self, value: float, _context) -> None:
        self.volume = value

    def GetMute(self) -> bool:
        return self.muted

    def SetMute(self, muted: bool, _context) -> None:
        self.muted = bool(muted)

    def GetPeakValue(self) -> float:
        """Something like music: a beat with a slower swell under it."""
        if self.muted:
            return 0.0
        t = time.monotonic() + self.phase
        beat = abs(math.sin(t * 7.3)) * 0.55 + abs(math.sin(t * 2.1)) * 0.45
        return round(self.loudness * self.volume ** 0.3 * (0.35 + 0.65 * beat), 4)


_endpoints: dict[str, Endpoint] = {}
_default = {True: SPEAKERS, False: WEBCAM}
_lock = threading.Lock()


def endpoint(key: str, loudness: float = 0.8) -> Endpoint:
    with _lock:
        if key not in _endpoints:
            _endpoints[key] = Endpoint(loudness)
        return _endpoints[key]


def headset_on() -> bool:
    from ..paths import data_dir
    return (data_dir() / HEADSET).exists()


def present(device_id: str) -> bool:
    return device_id not in AWAY_AT_START or headset_on()


# --- the replacements ----------------------------------------------------------
def _read_all():
    from .devices import Device
    return [Device(id=i, name=n, is_output=i.startswith("{0.0.0."), active=present(i))
            for i, n in NAMES.items()]


def _default_id(is_output: bool = True, max_age: float = 0.0) -> str | None:
    """Like Windows: a default that went away falls back to the speakers and
    the webcam."""
    with _lock:
        value = _default[is_output]
    if not present(value):
        value = SPEAKERS if is_output else WEBCAM
    return value


def _calls_default_id(is_output: bool = False) -> str | None:
    return _default_id(is_output)


def _set_default(device_id: str, include_communications: bool = True) -> bool:
    with _lock:
        _default[device_id.startswith("{0.0.0.")] = device_id
    return True


class _Presence:
    def read(self) -> dict[str, int]:
        return {i: 1 if present(i) else 4 for i in NAMES}     # active / not plugged in

    def close(self) -> None:
        pass


def _open(output: bool):
    e = endpoint(_default_id(output))
    return e, e


def _list_sessions():
    from .mixer import Session
    return [Session(key=k, name=n, volume=endpoint(k, loud).volume, muted=endpoint(k, loud).muted)
            for k, n, loud in APPS]


def _session_meters() -> dict:
    return {k: endpoint(k, loud) for k, _, loud in APPS}


def _set_app_volume(name: str, value: float) -> bool:
    endpoint(name).volume = max(0.0, min(1.0, float(value)))
    return True


def _set_app_mute(name: str, muted: bool) -> bool:
    endpoint(name).muted = bool(muted)
    return True


def _players_run(self) -> None:
    """One player, always the same track; play and pause just swap."""
    from .players import Track
    with self._lock:
        self._snap = Track("Music", "Demo Track", "Demo Artist", True)
        self._seen["music"] = "Music"
    if self._on_track:
        self._on_track()
    while True:
        kind, _ = self._jobs.get()
        if kind == "stop":
            return
        if kind == "cmd":
            with self._lock:
                self._snap.playing = not self._snap.playing
            if self._on_track:
                self._on_track()


def install() -> None:
    """Puts the made-up world in place of the real one. Called first thing,
    before the settings are opened. The folder is paths.data_dir's to choose."""
    # Set up the way somebody would have it after a week: the speakers and the
    # headphones in the cycle, the wireless headset taking over when it comes.
    from ..paths import config_path
    if not config_path().exists():
        config_path().write_text(json.dumps({
            "language": "en", "onboarded": True,
            "cycle": [SPEAKERS, HEADPHONES, MONITOR, WIRELESS],
            "auto_device": WIRELESS, "mic_base": WEBCAM,
        }), encoding="utf-8")

    from . import devices, language, meter, mixer, players
    devices._read_all = _read_all
    devices.default_id = _default_id
    devices.calls_default_id = _calls_default_id
    devices.set_default = _set_default
    devices.usb_ids_of = lambda device_id: None
    devices.Presence = _Presence
    meter._open = _open
    mixer.list_sessions = _list_sessions
    mixer.session_meters = _session_meters
    mixer.set_volume = _set_app_volume
    mixer.set_mute = _set_app_mute
    players.Players.run = _players_run
    language.pick = lambda: "en"
