"""Per-application volume and the overall device volume.

An audio session outlives its process: after the application is closed the
session hangs around for a while, and touching its process id raises
NoSuchProcess. This was reproduced, not assumed, so dead sessions are filtered
out here and not "some day later".
"""
import warnings
from dataclasses import dataclass

from comtypes import CLSCTX_ALL, POINTER, cast

from .. import log
from . import appicons

_log = log.get("mixer")

SYSTEM_SOUNDS = "System sounds"


@dataclass
class Session:
    key: str
    name: str
    volume: float
    muted: bool
    icon: str | None = None   # file name in the icon cache, None — draw a letter


def _sessions():
    from pycaw.pycaw import AudioUtilities
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return AudioUtilities.GetAllSessions()


def _session_name(s) -> str | None:
    """None means a dead session — it must not be shown."""
    if s.Process is None:
        return SYSTEM_SOUNDS
    try:
        return s.Process.name()
    except Exception:
        return None


def pretty(exe: str) -> str:
    """chrome.exe -> Chrome. The file name stays the key, we show a readable one."""
    if exe == SYSTEM_SOUNDS:
        return exe
    stem = exe[:-4] if exe.lower().endswith(".exe") else exe
    words = [w for w in stem.replace("_", " ").replace("-", " ").split() if w]
    return " ".join(w if w.isupper() else w.capitalize() for w in words) or exe


def list_sessions() -> list[Session]:
    out: list[Session] = []
    seen: set[str] = set()
    for s in _sessions():
        name = _session_name(s)
        if name is None:
            continue
        try:
            vol = s.SimpleAudioVolume
            exe = s.Process.exe() if s.Process else None
            item = Session(key=name, name=pretty(name),
                           volume=round(vol.GetMasterVolume(), 3),
                           muted=bool(vol.GetMute()),
                           icon=appicons.ensure(exe))
        except Exception:
            # Most often this is a game or a program running as administrator:
            # the path to its file is not given to an ordinary process. Such an
            # application simply disappears from the mixer, and without a log
            # entry the reason cannot be established.
            _log.info("session %s skipped", name, exc_info=True)
            continue
        if item.key in seen:  # one application can hold several sessions
            continue
        seen.add(item.key)
        out.append(item)
    out.sort(key=lambda x: (x.name == SYSTEM_SOUNDS, x.name.lower()))
    return out


def session_meters() -> dict:
    """A level meter for every live application, by the same key the mixer uses.
    For the meter thread: the interfaces belong to the thread that asks."""
    from pycaw.pycaw import IAudioMeterInformation
    out = {}
    for s in _sessions():
        name = _session_name(s)
        if name is None:
            continue
        try:
            out.setdefault(name, s._ctl.QueryInterface(IAudioMeterInformation))
        except Exception:
            _log.info("no meter for session %s", name, exc_info=True)
    return out


def _apply(name: str, fn) -> bool:
    hit = False
    for s in _sessions():
        if _session_name(s) != name:
            continue
        try:
            fn(s.SimpleAudioVolume)
            hit = True
        except Exception:
            _log.warning("could not change session %s", name, exc_info=True)
    return hit


def set_volume(name: str, value: float) -> bool:
    value = max(0.0, min(1.0, float(value)))

    def turn(v):
        # Moving a muted application's slider brings its sound back, like the
        # master knob does.
        v.SetMasterVolume(value, None)
        if v.GetMute():
            v.SetMute(False, None)
    return _apply(name, turn)


def set_mute(name: str, muted: bool) -> bool:
    return _apply(name, lambda v: v.SetMute(bool(muted), None))


# --- overall device volume -------------------------------------------------

def _endpoint_volume():
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        dev = AudioUtilities.GetSpeakers()
    raw = dev._dev if hasattr(dev, "_dev") else dev
    iface = raw.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


def master() -> dict:
    try:
        v = _endpoint_volume()
        return {"volume": round(v.GetMasterVolumeLevelScalar(), 3), "muted": bool(v.GetMute())}
    except Exception:
        _log.warning("overall volume is unavailable", exc_info=True)
        return {"volume": 0.0, "muted": False}


def set_master(value: float) -> None:
    _endpoint_volume().SetMasterVolumeLevelScalar(max(0.0, min(1.0, float(value))), None)


def set_master_mute(muted: bool) -> None:
    _endpoint_volume().SetMute(bool(muted), None)


def peak() -> float:
    """Live audio level — the ring of ticks around the knob breathes with it."""
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            dev = AudioUtilities.GetSpeakers()
        raw = dev._dev if hasattr(dev, "_dev") else dev
        iface = raw.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
        return round(cast(iface, POINTER(IAudioMeterInformation)).GetPeakValue(), 4)
    except Exception:
        return 0.0
