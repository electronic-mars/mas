"""Living inside Master Control Dock.

The dock draws us as one of its widgets, and then the tray icon is a duplicate.
It may have it — on two conditions. That the person said so: the icon stays
beside the widget unless they switch it off, because it is the one way in that
depends on nothing else running. And that we can always take it back: a dock
that has been closed, has crashed, was uninstalled, or is alive but not drawing
us would otherwise leave a running program with no icon, no window anybody can
reach and no way to quit it short of the task manager.

What the dock says to us arrives through the bridge (see docs/DOCK.md); this is
what we make of it.
"""
import threading
import time

from . import log

_log = log.get("dock")


class Dock:
    SILENCE = 15.0     # longer than any hiccup, shorter than any patience
    WATCH = 3.0

    def __init__(self, cfg, tray, on_change, stopped: threading.Event):
        """`tray` answers the Tray, or None before it exists; `on_change` tells
        the page the state moved; `stopped` ends the watch with the program."""
        self._cfg = cfg
        self._tray = tray
        self._on_change = on_change
        self._stopped = stopped
        # When the dock last spoke, whether it said it was drawing us, what the
        # settings page was last told, and what the tray currently shows —
        # None until somebody has decided.
        self._seen = 0.0
        self._showing = False
        self._was_showing = False
        self._tray_shown: bool | None = None

    def seen(self, showing: bool) -> None:
        """The dock has just spoken to us, and said whether it draws us."""
        self._seen = time.monotonic()
        self._showing = showing

    def showing(self) -> bool:
        """Is a living dock drawing us right now?"""
        return (bool(self._cfg.get("dock_hosts_us"))
                and self._showing
                and time.monotonic() - self._seen < self.SILENCE)

    def has_us(self) -> bool:
        """Does the dock stand in for the tray icon? Only if it is drawing us
        and the person has said they do not want the icon as well."""
        return self.showing() and not self._cfg.get("tray_with_dock")

    def apply(self) -> None:
        """Put the tray icon wherever the answer currently is."""
        tray = self._tray()
        if not tray:
            return
        showing = self.showing()
        if showing != self._was_showing:
            # The settings page offers the tray switch only while a dock shows
            # us, so it has to hear when that starts and stops.
            self._was_showing = showing
            self._on_change()
        want = not self.has_us()
        if want != self._tray_shown:
            self._tray_shown = want
            tray.set_visible(want)
            _log.info("the tray icon is %s (the dock %s us)",
                      "ours" if want else "the dock's",
                      "has" if not want else "does not have")

    def watch(self) -> None:
        while not self._stopped.wait(self.WATCH):
            try:
                self.apply()
            except Exception:
                # Whatever went wrong here, the icon is the way out of the
                # program: never let this thread die quietly.
                _log.exception("the dock watch stumbled")
