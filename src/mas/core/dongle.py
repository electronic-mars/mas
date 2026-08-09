"""Wireless headset state, learned from its USB dongle.

Why: the dongle stays plugged in at all times, so the headset's audio endpoint
does not change state when the headset is switched on or off — measured many
times over, and at the Windows level that signal does not exist at all. The
dongle itself, however, sends a short service report over HID, on the same
channel the vendor software uses to show the battery level.

We open read-only and wait: the dongle sends the report on its own, there is no
need to poll it. Nothing is written to the device — people have already tried
writing blindly to headsets like this and bricked them.

The decoding was verified on a HyperX Cloud Flight S (VID 0951, PID 16EA) over
three power cycles:
    0b 00 bb 01 01  — headset connected
    0b 00 bb 01 03  — headset switched off
"""
import ctypes
import threading
from ctypes import wintypes

from .. import log

_log = log.get("dongle")

setupapi = ctypes.WinDLL("setupapi")
hid = ctypes.WinDLL("hid")
k32 = ctypes.WinDLL("kernel32")

GENERIC_READ = 0x80000000
FILE_SHARE_RW = 3
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
ERROR_IO_PENDING = 997
DIGCF_PRESENT, DIGCF_DEVICEINTERFACE = 0x02, 0x10
INVALID = wintypes.HANDLE(-1).value

# Known dongles: (vendor, product) -> how to read the report.
# The "01 on / 03 off" pair also shows up on the previous Cloud Flight model, so
# this list will most likely grow without any code changes.
KNOWN = {
    (0x0951, 0x16EA): {"name": "HyperX Cloud Flight S",
                       "report": 0x0B, "marker": (2, 0xBB), "state_at": 4,
                       "on": 0x01, "off": 0x03},
}


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class _IFACE(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", _GUID),
                ("Flags", wintypes.DWORD), ("Reserved", ctypes.POINTER(wintypes.ULONG))]


class _ATTRS(ctypes.Structure):
    _fields_ = [("Size", wintypes.ULONG), ("VendorID", wintypes.USHORT),
                ("ProductID", wintypes.USHORT), ("VersionNumber", wintypes.USHORT)]


class _CAPS(ctypes.Structure):
    _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                ("InputReportByteLength", wintypes.USHORT),
                ("OutputReportByteLength", wintypes.USHORT),
                ("FeatureReportByteLength", wintypes.USHORT),
                ("Reserved", wintypes.USHORT * 17),
                ("NumberLinkCollectionNodes", wintypes.USHORT),
                ("NumberInputButtonCaps", wintypes.USHORT),
                ("NumberInputValueCaps", wintypes.USHORT),
                ("NumberInputDataIndices", wintypes.USHORT),
                ("NumberOutputButtonCaps", wintypes.USHORT),
                ("NumberOutputValueCaps", wintypes.USHORT),
                ("NumberOutputDataIndices", wintypes.USHORT),
                ("NumberFeatureButtonCaps", wintypes.USHORT),
                ("NumberFeatureValueCaps", wintypes.USHORT),
                ("NumberFeatureDataIndices", wintypes.USHORT)]


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]


setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(_GUID), wintypes.LPCWSTR,
                                          wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                                 ctypes.POINTER(_GUID), wintypes.DWORD,
                                                 ctypes.POINTER(_IFACE)]
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_IFACE),
                                                      ctypes.c_void_p, wintypes.DWORD,
                                                      ctypes.POINTER(wintypes.DWORD),
                                                      ctypes.c_void_p]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
k32.CreateFileW.restype = wintypes.HANDLE
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
k32.CreateEventW.restype = wintypes.HANDLE


def find_collections(vid: int, pid: int) -> list[str]:
    """Paths to all HID collections of the dongle. We open with zero access —
    this is a property query, it does not claim the device."""
    guid = _GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    hdev = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None,
                                         DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    out: list[str] = []
    i = 0
    try:
        while True:
            iface = _IFACE()
            iface.cbSize = ctypes.sizeof(_IFACE)
            if not setupapi.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(guid),
                                                        i, ctypes.byref(iface)):
                break
            i += 1
            need = wintypes.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(iface), None, 0,
                                                      ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0] = (
                8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6)
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(iface), buf,
                                                             need.value, ctypes.byref(need),
                                                             None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            h = k32.CreateFileW(path, 0, FILE_SHARE_RW, None, OPEN_EXISTING, 0, None)
            if h == INVALID:
                continue
            attrs = _ATTRS()
            attrs.Size = ctypes.sizeof(attrs)
            hid.HidD_GetAttributes(wintypes.HANDLE(h), ctypes.byref(attrs))
            k32.CloseHandle(wintypes.HANDLE(h))
            if (attrs.VendorID, attrs.ProductID) == (vid, pid):
                out.append(path)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return out


def learn_write(line: str) -> None:
    """Append a line to the learning file. The file stays on disk: the program
    sends nothing anywhere, showing it to someone is the user's decision."""
    from ..paths import learn_path
    try:
        with open(learn_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        _log.warning("cannot write to the learning file", exc_info=True)


class Dongle(threading.Thread):
    """Listens to the dongle and calls the handler when the headset state changes.

    In learning mode there is no decoding: every report that arrives is simply
    written to a file, so that a new model can be added from it later.
    """

    def __init__(self, vid: int, pid: int, on_change, learn: bool = False):
        super().__init__(daemon=True, name="mas-dongle")
        self.vid, self.pid = vid, pid
        self.learn = learn
        self._rule = None if learn else KNOWN[(vid, pid)]
        self._on_change = on_change
        self._stop = threading.Event()
        self._state: bool | None = None

    @property
    def state(self) -> bool | None:
        """True — connected, False — switched off, None — not known yet."""
        return self._state

    def stop(self) -> None:
        self._stop.set()

    def _decode(self, data: bytes) -> bool | None:
        r = self._rule
        if r is None:
            return None
        pos, val = r["marker"]
        if len(data) <= r["state_at"] or data[0] != r["report"] or data[pos] != val:
            return None
        s = data[r["state_at"]]
        return True if s == r["on"] else False if s == r["off"] else None

    def _listen(self, path: str) -> None:
        # Staying silent here is not an option: the log kept a cheerful
        # "listening to dongle" while not a single report arrived, and there was
        # nothing to establish the reason from.
        h = k32.CreateFileW(path, GENERIC_READ, FILE_SHARE_RW, None, OPEN_EXISTING,
                            FILE_FLAG_OVERLAPPED, None)
        if h == INVALID:
            _log.warning("cannot open dongle collection (error %s) — vendor software "
                         "may be holding it: %s", k32.GetLastError(), path[-60:])
            return
        pp = ctypes.c_void_p()
        caps = _CAPS()
        if not hid.HidD_GetPreparsedData(wintypes.HANDLE(h), ctypes.byref(pp)):
            _log.warning("dongle collection has no report descriptor: %s", path[-60:])
            k32.CloseHandle(wintypes.HANDLE(h))
            return
        hid.HidP_GetCaps(pp, ctypes.byref(caps))
        hid.HidD_FreePreparsedData(pp)
        size = caps.InputReportByteLength
        if not size:
            _log.info("dongle collection sends no reports: %s", path[-60:])
            k32.CloseHandle(wintypes.HANDLE(h))
            return
        ev = k32.CreateEventW(None, True, False, None)
        try:
            while not self._stop.is_set():
                buf = ctypes.create_string_buffer(size)
                ov = _OVERLAPPED()
                ov.hEvent = ev
                k32.ResetEvent(wintypes.HANDLE(ev))
                read = wintypes.DWORD()
                ok = k32.ReadFile(wintypes.HANDLE(h), buf, size, ctypes.byref(read),
                                  ctypes.byref(ov))
                if not ok and k32.GetLastError() != ERROR_IO_PENDING:
                    # Usually this means the dongle was unplugged. The listener
                    # dies, and watching stays dead until the program is
                    # restarted — that at least has to be said out loud.
                    _log.warning("reading dongle reports was cut off (error %s), "
                                 "watching this collection stopped", k32.GetLastError())
                    break
                if k32.WaitForSingleObject(wintypes.HANDLE(ev), 500) != 0:
                    k32.CancelIo(wintypes.HANDLE(h))
                    continue
                k32.GetOverlappedResult(wintypes.HANDLE(h), ctypes.byref(ov),
                                        ctypes.byref(read), False)
                data = buf.raw[:read.value]
                if self.learn:
                    import time
                    learn_write(f"{time.strftime('%H:%M:%S')}  {self.vid:04X}:{self.pid:04X}"
                                f"  {path.split('#')[1] if '#' in path else ''}"
                                f"  {data.hex(' ')}")
                    continue
                state = self._decode(data)
                if state is None or state == self._state:
                    continue
                self._state = state
                _log.info("headset %s", "on" if state else "off")
                try:
                    self._on_change(state)
                except Exception:
                    _log.exception("headset state handler crashed")
        finally:
            k32.CloseHandle(wintypes.HANDLE(h))
            k32.CloseHandle(wintypes.HANDLE(ev))

    def run(self) -> None:
        paths = find_collections(self.vid, self.pid)
        if not paths:
            _log.warning("dongle %04X:%04X not found", self.vid, self.pid)
            return
        if self.learn:
            from ..paths import learn_path
            learn_write(f"--- {self.vid:04X}:{self.pid:04X}, {len(paths)} collections")
            _log.info("learning unknown dongle %04X:%04X, writing to %s",
                      self.vid, self.pid, learn_path())
        else:
            _log.info("listening to %s: %d collections", self._rule["name"], len(paths))
        # Which collection actually carries the service report is not known in
        # advance and may differ between firmwares — we listen to all of them,
        # decoding filters out the rest. Each collection waits for its own report
        # and uses no CPU.
        threads = [threading.Thread(target=self._listen, args=(p,), daemon=True,
                                    name="mas-dongle-col") for p in paths]
        for t in threads:
            t.start()
        self._stop.wait()
        for t in threads:
            t.join(timeout=1.0)
