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


class Meter(threading.Thread):
    def __init__(self, interval: float = 0.1, on_devices_changed=None,
                 on_default_changed=None):
        super().__init__(daemon=True, name="mas-meter")
        self.interval = interval
        self._on_devices_changed = on_devices_changed
        self._on_default_changed = on_default_changed
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
        """
        if self._vol is None:
            return
        value = max(0.0, min(1.0, float(value)))
        self._vol.SetMasterVolumeLevelScalar(value, None)
        with self._lock:
            self._snap["volume"] = round(value, 4)

    def set_mute(self, muted: bool) -> None:
        if self._vol is None:
            return
        self._vol.SetMute(bool(muted), None)
        with self._lock:
            self._snap["muted"] = bool(muted)

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

        dev_id = devices.default_id(is_output=True)
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

    def run(self) -> None:
        import comtypes
        # The free COM model (MTA), not the single-threaded one. In the
        # single-threaded model an object must be released by the same thread
        # that created it, and Python's garbage collector does not know that: it
        # fires on any thread and kills the process with a memory access
        # violation. Caught with a trap.
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        elapsed = watched = bound = 0.0
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
            self._bound_id = None
            if self._presence is not None:
                self._presence.close()
                self._presence = None
            comtypes.CoUninitialize()
