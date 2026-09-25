"""A single thread that owns the COM objects of the level meter.

The interface used to poll the level through the bridge, and the HTTP server
raised a thread per request — seven new threads a second, each with its own COM
initialisation and new interfaces. The system ground to a halt. Now COM lives on
a single thread, and the bridge hands out a ready snapshot without touching COM
at all.
"""
import threading

from .. import log

_log = log.get("meter")

# The rhythm is in seconds, not in ticks: the polling rate changes together with
# whether the window is visible, while watching the set of devices and the change
# of the default has to happen equally often in both cases.
WATCH_EVERY_S = 0.5     # how often we look for devices appearing
REBIND_EVERY_S = 2.0    # how often we check whether the device changed
IDLE_INTERVAL = 0.5     # the tick when the window is hidden: nobody sees the level
# Applications come and go far less often than their level moves: the list of
# sessions is re-read once a second, their meters every tick.
SESSIONS_EVERY_S = 1.0
# How long one question from the mixer keeps the application meters running.
# The mixer asks several times a second while it is on screen; when it stops
# asking — another tab, a hidden window — the meters stop with it.
SESSIONS_WANTED_S = 1.5


class Meter(threading.Thread):
    def __init__(self, interval: float = 0.1, on_devices_changed=None,
                 on_default_changed=None, on_mute_changed=None):
        super().__init__(daemon=True, name="mas-meter")
        self.interval = interval
        self._on_devices_changed = on_devices_changed
        self._on_default_changed = on_default_changed
        self._on_mute_changed = on_mute_changed
        # What the listener was last told. Separate from the snapshot, which
        # our own writes update ahead of the device: the listener hears every
        # change once, from here, whoever made it.
        self._told_muted: bool | None = None
        # Application meters: key -> IAudioMeterInformation, and the levels read
        # from them. Only while the mixer is asking (see levels()).
        self._session_meters: dict = {}
        self._levels: dict[str, float] = {}
        self._levels_wanted_until = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        # Set when the meter binds to a device for the first time: the startup
        # does not need to wait "two seconds just in case", it needs to wait for
        # exactly this.
        self.ready = threading.Event()
        # When the window is hidden nobody sees the level: we poll less often.
        self._idle = threading.Event()
        self._snap = {"peak": 0.0, "volume": 0.0, "muted": False, "device": ""}
        self._vol = None
        self._meter = None
        self._bound_id: str | None = None
        self._presence = None
        self._present: set[str] | None = None

    # --- public -------------------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._snap)

    def set_volume(self, value: float) -> None:
        """Writing also goes through this thread's object instead of making a new one.

        We update the snapshot immediately: otherwise, before the next
        measurement, the interface would read the old volume once more and throw
        the slider back to the value the person has just moved it away from.

        Turning the volume also switches the sound back on, as the Windows
        slider does: someone reaching for the knob wants to hear something, and
        a knob that moves while the sound stays off only sends them hunting
        through the system settings.
        """
        if self._vol is None:
            return
        value = max(0.0, min(1.0, float(value)))
        self._vol.SetMasterVolumeLevelScalar(value, None)
        # Asked of the device, not of the snapshot: the snapshot is up to half
        # a second old, and a mute key pressed just before turning would be
        # missed — the one case this is here for.
        if self._vol.GetMute():
            self._vol.SetMute(False, None)
        with self._lock:
            self._snap["volume"] = round(value, 4)
            self._snap["muted"] = False

    def set_mute(self, muted: bool) -> None:
        if self._vol is None:
            return
        self._vol.SetMute(bool(muted), None)
        with self._lock:
            self._snap["muted"] = bool(muted)

    def levels(self) -> dict[str, float]:
        """The current level of every application playing, by mixer key, and a
        promise to keep measuring for a moment longer. Nothing here touches COM:
        the meter thread reads the levels and this hands out its last reading."""
        import time
        self._levels_wanted_until = time.monotonic() + SESSIONS_WANTED_S
        with self._lock:
            return dict(self._levels)

    def _read_levels(self, relist: bool) -> None:
        """In the meter thread only. The session list is read now and then; the
        meters on every tick."""
        from . import mixer
        if relist or not self._session_meters:
            self._session_meters = mixer.session_meters()
        levels = {}
        for key, meter in self._session_meters.items():
            try:
                levels[key] = max(levels.get(key, 0.0), round(meter.GetPeakValue(), 4))
            except Exception:
                levels[key] = 0.0         # the application went away mid-tick
        with self._lock:
            self._levels = levels

    def _drop_levels(self) -> None:
        if self._session_meters or self._levels:
            self._session_meters = {}
            with self._lock:
                self._levels = {}

    def set_idle(self, idle: bool) -> None:
        """The window is hidden — nobody sees the level, we poll five times less
        often. The set of devices and the change of the default we watch at the
        same rate as before."""
        self._idle.set() if idle else self._idle.clear()

    def stop(self) -> None:
        self._stop.set()

    # --- internals ------------------------------------------------------
    def _bind(self) -> None:
        from comtypes import CLSCTX_ALL, POINTER, cast
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, IAudioMeterInformation

        from . import devices

        # Read fresh here, in this thread, so that everybody else can take the
        # cached answer: see _DEFAULT_TTL in devices.
        dev_id = devices.default_id(is_output=True, max_age=0.0)
        devices.default_id(is_output=False, max_age=0.0)
        if dev_id == self._bound_id and self._vol is not None:
            return
        dev = AudioUtilities.GetSpeakers()
        raw = dev._dev if hasattr(dev, "_dev") else dev
        self._vol = cast(raw.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                         POINTER(IAudioEndpointVolume))
        self._meter = cast(raw.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None),
                           POINTER(IAudioMeterInformation))
        self._bound_id = dev_id
        self.ready.set()
        name = ""
        for d in devices.list_devices():
            if d.id == dev_id:
                name = d.name
                break
        with self._lock:
            self._snap["device"] = name
        _log.info("meter bound to device %s", name or "?")
        # We are not the only ones changing the default: Windows itself hands the
        # sound to headphones when they connect, and the person can switch it in
        # the system settings too. The tray icon must show the truth in any case.
        if self._on_default_changed:
            self._on_default_changed(dev_id)

    def _watch(self) -> None:
        """The set of devices changes rarely, so we drop the expensive snapshot
        only when a change actually happened, not on a schedule."""
        from . import devices

        if self._presence is None:
            self._presence = devices.Presence()
        now = self._presence.read()
        was = self._present
        if was is None:
            self._present = now
            _log.info("watching the state of %d audio endpoints", len(now))
            return
        moved = [i for i in set(now) | set(was) if now.get(i) != was.get(i)]
        self._present = now
        if not moved:
            return
        devices.invalidate()
        # We log every change by name: different headphones make the system
        # behave differently, and without this record the reason for "nothing
        # happens" is impossible to catch.
        for i in moved:
            _log.info("endpoint %s: %s -> %s", i[-13:],
                      devices.STATE_NAMES.get(was.get(i), "not in the list"),
                      devices.STATE_NAMES.get(now.get(i), "not in the list"))
        # While we are at it we record the default microphone: when a headset
        # connects, Windows moves recording onto it as well, and when it
        # disconnects it leaves the default on the vanished device — that is when
        # the microphone looks crossed out. Without this record the cause cannot
        # be established.
        mic = devices.default_id(is_output=False, max_age=0.0)
        _log.info("default microphone: %s", mic[-13:] if mic else "undetermined")

        live = {i for i, s in now.items() if s == devices.DEVICE_STATE_ACTIVE}
        before = {i for i, s in was.items() if s == devices.DEVICE_STATE_ACTIVE}
        added, removed = live - before, before - live
        if (added or removed) and self._on_devices_changed:
            self._on_devices_changed(added, removed)
        # Re-read here rather than on the next request thread — and only after
        # the change has been reported: if the read fails, which a device
        # half-way through arriving can make it do, the exception resets the
        # watch, and a change not yet reported would be lost for good.
        devices.list_devices()

    def run(self) -> None:
        import comtypes
        # The free COM model (MTA), not the single-threaded one. In the
        # single-threaded model an object must be released by the same thread
        # that created it, and Python's garbage collector does not know that: it
        # fires on any thread and kills the process with a memory access
        # violation. Caught with a trap.
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        import time
        elapsed = watched = bound = listed = 0.0
        try:
            while True:
                step = IDLE_INTERVAL if self._idle.is_set() else self.interval
                if self._stop.wait(step):
                    break
                elapsed += step
                try:
                    if elapsed - watched >= WATCH_EVERY_S:
                        watched = elapsed
                        self._watch()
                except Exception:
                    self._presence = self._present = None
                    _log.warning("watching the devices broke down", exc_info=True)
                try:
                    if elapsed - bound >= REBIND_EVERY_S or self._vol is None:
                        bound = elapsed
                        self._bind()
                    if self._vol is None:
                        continue
                    peak = self._meter.GetPeakValue()
                    vol = self._vol.GetMasterVolumeLevelScalar()
                    muted = bool(self._vol.GetMute())
                except Exception:
                    # Without this record "the volume is always zero" looks like
                    # an inexplicable breakage: the meter fell off silently and
                    # tried again every hundred milliseconds, leaving no trace.
                    if self._bound_id is not None:
                        _log.warning("the meter fell off the device, rebinding",
                                     exc_info=True)
                    self._vol = self._meter = self._bound_id = None
                    continue
                with self._lock:
                    self._snap.update(peak=round(peak, 4), volume=round(vol, 4), muted=muted)
                try:
                    if time.monotonic() < self._levels_wanted_until:
                        relist = elapsed - listed >= SESSIONS_EVERY_S
                        if relist:
                            listed = elapsed
                        self._read_levels(relist)
                    else:
                        self._drop_levels()
                except Exception:
                    self._session_meters = {}
                    _log.warning("the application meters broke down", exc_info=True)
                if muted != self._told_muted and self._on_mute_changed:
                    self._told_muted = muted
                    try:
                        self._on_mute_changed(muted)
                    except Exception:
                        _log.warning("the mute listener failed", exc_info=True)
        finally:
            # The COM interfaces must be released here, before leaving the thread
            # and before the WebView2 window unloads the .NET runtime. Otherwise
            # Release happens later, in an already destroyed environment, and
            # brings the process down.
            # Only our own interfaces, and by nulling them out: the reference
            # count frees them right away and exactly here. Calling gc.collect()
            # from here is not allowed — collection is global, it reaches objects
            # of other threads and frees them not where they were created: the
            # process crashes.
            self._vol = self._meter = None
            self._session_meters = {}
            self._bound_id = None
            if self._presence is not None:
                self._presence.close()
                self._presence = None
            comtypes.CoUninitialize()
