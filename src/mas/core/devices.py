"""Output and recording devices: enumeration and changing the default.

Changing the default goes through the undocumented COM interface IPolicyConfig —
there is no other way in Windows, and Audio Switcher and SoundSwitch are built
on the same one. Verified on Windows 11 build 26200.
"""
import ctypes
import threading
import time
import warnings
from ctypes import HRESULT, POINTER, c_void_p
from ctypes.wintypes import BOOL, DWORD, LPCWSTR
from dataclasses import dataclass

import comtypes
from comtypes import COMMETHOD, GUID, IUnknown

from .. import log

_log = log.get("devices")

# Device roles in Windows. Console and multimedia are ordinary sound,
# communications is a separate default for calls (Discord, Zoom, Teams).
ROLE_CONSOLE, ROLE_MULTIMEDIA, ROLE_COMMUNICATIONS = 0, 1, 2

OUTPUT_PREFIX = "{0.0.0.00000000}"
INPUT_PREFIX = "{0.0.1.00000000}"


class IPolicyConfig(IUnknown):
    _iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
    _methods_ = (
        COMMETHOD([], HRESULT, "GetMixFormat",
                  (["in"], LPCWSTR, "d"), (["out"], POINTER(c_void_p), "p")),
        COMMETHOD([], HRESULT, "GetDeviceFormat",
                  (["in"], LPCWSTR, "d"), (["in"], BOOL, "b"), (["out"], POINTER(c_void_p), "p")),
        COMMETHOD([], HRESULT, "ResetDeviceFormat", (["in"], LPCWSTR, "d")),
        COMMETHOD([], HRESULT, "SetDeviceFormat",
                  (["in"], LPCWSTR, "d"), (["in"], c_void_p, "a"), (["in"], c_void_p, "b")),
        COMMETHOD([], HRESULT, "GetProcessingPeriod",
                  (["in"], LPCWSTR, "d"), (["in"], BOOL, "b"),
                  (["out"], POINTER(ctypes.c_longlong), "a"),
                  (["out"], POINTER(ctypes.c_longlong), "c")),
        COMMETHOD([], HRESULT, "SetProcessingPeriod",
                  (["in"], LPCWSTR, "d"), (["in"], POINTER(ctypes.c_longlong), "p")),
        COMMETHOD([], HRESULT, "GetShareMode",
                  (["in"], LPCWSTR, "d"), (["out"], POINTER(c_void_p), "p")),
        COMMETHOD([], HRESULT, "SetShareMode", (["in"], LPCWSTR, "d"), (["in"], c_void_p, "m")),
        COMMETHOD([], HRESULT, "GetPropertyValue",
                  (["in"], LPCWSTR, "d"), (["in"], BOOL, "f"),
                  (["in"], c_void_p, "k"), (["out"], POINTER(c_void_p), "v")),
        COMMETHOD([], HRESULT, "SetPropertyValue",
                  (["in"], LPCWSTR, "d"), (["in"], BOOL, "f"),
                  (["in"], c_void_p, "k"), (["in"], c_void_p, "v")),
        COMMETHOD([], HRESULT, "SetDefaultEndpoint", (["in"], LPCWSTR, "d"), (["in"], DWORD, "role")),
        COMMETHOD([], HRESULT, "SetEndpointVisibility", (["in"], LPCWSTR, "d"), (["in"], BOOL, "v")),
    )


CLSID_PolicyConfigClient = GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")
CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
DEVICE_STATE_ACTIVE = 0x1
DEVICE_STATE_ALL = 0xF
EDATAFLOW_ALL = 2
STATE_NAMES = {0x1: "active", 0x2: "disabled", 0x4: "not plugged in", 0x8: "not present"}


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    is_output: bool
    active: bool

    @property
    def kind(self) -> str:
        return "output" if self.is_output else "input"


# Enumerating devices costs about 450 ms: pycaw reads the properties of every
# endpoint, including the disabled ones. It used to be called three times per
# switch — hence the second and a half of delay. We keep a snapshot and refresh
# it when needed, not on every question.
_LIST_TTL = 3.0
_DEFAULT_TTL = 0.5

_lock = threading.Lock()
_cache: dict = {"devices": None, "ts": 0.0}
_default_cache: dict = {True: (None, 0.0), False: (None, 0.0)}


def _enumerate():
    """pycaw is noisy with warnings on disabled devices — we silence them here."""
    from pycaw.pycaw import AudioUtilities
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return AudioUtilities.GetAllDevices()


def _read_all() -> list[Device]:
    out: list[Device] = []
    for d in _enumerate():
        if not d.id:
            continue
        is_output = d.id.startswith(OUTPUT_PREFIX)
        if not is_output and not d.id.startswith(INPUT_PREFIX):
            continue
        out.append(Device(id=d.id, name=d.FriendlyName or "Device",
                          is_output=is_output, active=str(d.state).endswith("Active")))
    return out


def invalidate() -> None:
    """The set of devices changed — the snapshot is no good any more."""
    with _lock:
        _cache["devices"] = None


def list_devices(only_active: bool = True, max_age: float = _LIST_TTL) -> list[Device]:
    now = time.monotonic()
    with _lock:
        cached = _cache["devices"]
        fresh = cached is not None and now - _cache["ts"] <= max_age
    if not fresh:
        cached = _read_all()
        with _lock:
            _cache["devices"], _cache["ts"] = cached, now
    return [d for d in cached if d.active] if only_active else list(cached)


_local = threading.local()
FLOW_RENDER, FLOW_CAPTURE = 0, 1


def _enumerator():
    """One device enumerator per thread, kept for the life of that thread.

    pycaw's helpers build a fresh enumerator on every call, and that is not
    cheap: measured at 46 ms here. The meter asks for the default device every
    two seconds, so those 46 ms were 2.3% of a processor core burned around the
    clock — most of everything the program spent while nobody was looking.

    Per thread rather than one for all: the object belongs to the COM apartment
    that created it. And created once rather than per call for a second reason
    recorded in Presence below — making COM objects several times a second once
    left the whole system's audio service unresponsive.
    """
    enum = getattr(_local, "enum", None)
    if enum is None:
        from pycaw.pycaw import IMMDeviceEnumerator
        enum = comtypes.cast(
            comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator,
                                      comtypes.CLSCTX_INPROC_SERVER),
            POINTER(IMMDeviceEnumerator))
        _local.enum = enum
    return enum


def default_id(is_output: bool = True, max_age: float = _DEFAULT_TTL) -> str | None:
    now = time.monotonic()
    with _lock:
        value, ts = _default_cache[is_output]
    if value is not None and now - ts <= max_age:
        return value

    try:
        flow = FLOW_RENDER if is_output else FLOW_CAPTURE
        value = _enumerator().GetDefaultAudioEndpoint(flow, ROLE_CONSOLE).GetId()
    except Exception:
        _log.warning("could not get the default device (%s)",
                     "output" if is_output else "recording", exc_info=True)
        return None
    with _lock:
        _default_cache[is_output] = (value, now)
    return value


def _owner(name: str) -> str:
    """'Headphones (Powerbeats Pro)' -> 'Powerbeats Pro'.

    Windows builds the endpoint name as 'purpose (device)'. The property holding
    the parent device name is not always filled in — the Powerbeats output has
    none at all — while the parentheses in the name are always there.
    """
    head, sep, tail = name.partition(" (")
    return tail.rstrip(")").strip() if sep else ""


def _common_words(a: str, b: str) -> int:
    wa, wb = a.split(), b.split()
    n = 0
    for x, y in zip(wa, wb):
        if x.lower() != y.lower():
            break
        n += 1
    return n


def microphone_of(output_id: str) -> Device | None:
    """The microphone of the same headset as the given output device.

    First an exact match on the device in parentheses — that is how headphones
    are found whose output and recording are named the same. If there is no exact
    match, we look for a common beginning of two or more words: on some headsets
    the halves are called "... Game" and "... Chat", and only the shared prefix
    links them.
    """
    devs = list_devices(only_active=True)
    out = next((d for d in devs if d.id == output_id), None)
    if out is None:
        return None
    tag = _owner(out.name)
    if not tag:
        return None
    mics = [d for d in devs if not d.is_output]
    for m in mics:
        if _owner(m.name) == tag:
            return m
    best, score = None, 1
    for m in mics:
        n = _common_words(tag, _owner(m.name))
        if n > score:
            best, score = m, n
    return best


# The device path in the system lies in the endpoint property under this key —
# the vendor and product come from it: "USB\VID_0951&PID_16EA&MI_00\...".
_PKEY_DEVICE_PATH = "{B3F8FA53-0004-438E-9003-51A46E139BFC} 39"


def usb_ids_of(device_id: str) -> tuple[int, int] | None:
    """Vendor and product of the USB device behind an endpoint.

    Returns None if the endpoint is not on USB or Windows did not fill the
    property in — that happens with Bluetooth, for example.
    """
    import re
    from pycaw.pycaw import AudioUtilities
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for d in AudioUtilities.GetAllDevices():
            if d.id != device_id:
                continue
            for k, v in (d.properties or {}).items():
                if str(k) != _PKEY_DEVICE_PATH or not v:
                    continue
                m = re.search(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", str(v), re.I)
                if m:
                    return int(m.group(1), 16), int(m.group(2), 16)
    return None


def tied_microphones() -> set[str]:
    """Microphones that belong to some output device."""
    devs = list_devices(only_active=True)
    out = set()
    for d in devs:
        if d.is_output:
            m = microphone_of(d.id)
            if m is not None:
                out.add(m.id)
    return out


def standalone_microphone() -> str | None:
    """A microphone that belongs to no headset — usually the built-in one.

    We answer only when there is exactly one: if there are several, guessing
    which of them is "the main one" is above the program's station.
    """
    free = [d for d in list_devices(only_active=True)
            if not d.is_output and d.id not in tied_microphones()]
    return free[0].id if len(free) == 1 else None


def note_default(device_id: str, is_output: bool = True) -> None:
    """We have just changed the default ourselves — no need to ask the system."""
    with _lock:
        _default_cache[is_output] = (device_id, time.monotonic())


class Presence:
    """The state of every audio endpoint — id and state, without properties.

    A full enumeration with properties costs about 300 ms, and this snapshot
    single milliseconds, so it can ask the system twice a second.

    We read the states themselves, not the list of active ones: on wireless
    headsets with a USB receiver the endpoint does not disappear when they are
    switched off, it changes state — and the difference in states shows what the
    composition of the list does not.
    The object must live on the thread that owns COM.
    """

    def __init__(self):
        # The enumerator is created once and lives with the thread. Creating COM
        # objects several times a second has already led, in this project, to the
        # audio service becoming unresponsive for the whole system.
        from pycaw.pycaw import IMMDeviceEnumerator
        self._enum = comtypes.cast(
            comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator,
                                      comtypes.CLSCTX_INPROC_SERVER),
            POINTER(IMMDeviceEnumerator))

    def read(self) -> dict[str, int]:
        coll = self._enum.EnumAudioEndpoints(EDATAFLOW_ALL, DEVICE_STATE_ALL)
        out = {}
        for i in range(coll.GetCount()):
            d = coll.Item(i)
            out[d.GetId()] = d.GetState()
        return out

    def close(self) -> None:
        self._enum = None


def set_default(device_id: str, include_communications: bool = True) -> bool:
    """Switch the sound and make sure the system agreed.

    Returns False if the default stayed the same after the switch. That does
    happen: a driver or a policy can refuse while still returning S_OK. The
    program used to record the intention as a fact — the tray icon showed
    headphones while the sound stayed in the speakers, and there was nothing to
    disprove it with.

    One switch takes about 90 ms. Rapid repeated calls are safe.
    """
    pc = comtypes.CoCreateInstance(CLSID_PolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_ALL)
    roles = [ROLE_CONSOLE, ROLE_MULTIMEDIA]
    if include_communications:
        roles.append(ROLE_COMMUNICATIONS)
    for role in roles:
        pc.SetDefaultEndpoint(device_id, role)
    is_output = device_id.startswith(OUTPUT_PREFIX)
    note_default(device_id, is_output=is_output)
    # We check past the cache: we filled the cache ourselves a moment ago with
    # the value we wanted.
    actual = default_id(is_output=is_output, max_age=0.0)
    if actual == device_id:
        _log.info("default device: %s (roles %s)", device_id[-14:], roles)
        return True
    _log.error("the system did not accept the switch: asked for %s, got %s",
               device_id[-14:], actual[-14:] if actual else "nothing")
    note_default(actual, is_output=is_output) if actual else invalidate()
    return False
