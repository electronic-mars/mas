"""The update button: one small state, and the work behind it.

The whole thing is read by the page four times a second while anything is
happening and left alone otherwise. Every ending is named: "failed" carries a
reason, because a button that quietly returns to how it was is the one thing
worse than a button that says what went wrong.

What actually fetches, checks and runs the installer lives in core/update.py;
this is the state machine around it, kept apart from the rest of the program so
that the program does not have to know how many stages an update has.
"""
import threading

from . import __version__, log
from .core import update

_log = log.get("updater")


class Updater:
    def __init__(self, on_change, on_installed):
        """`on_change` is called whenever the state moves, so the page can be
        told; `on_installed` once the installer has been handed the files —
        the program has to get out of its way."""
        self._state: dict = {"state": "idle", "detail": "", "percent": 0, "notes": ""}
        self._lock = threading.Lock()
        self._found: dict | None = None
        self._on_change = on_change
        self._on_installed = on_installed

    def state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def _set(self, **fields) -> None:
        with self._lock:
            self._state.update(fields)
        self._on_change()

    def forget(self) -> dict:
        """Back to the plain button — the page asks for this after showing an
        answer that has been read."""
        self._set(state="idle", detail="", percent=0)
        return self.state()

    def check(self) -> dict:
        if update.from_store():
            return self.state()      # the Store does this, and does it better
        self._set(state="checking", detail="", percent=0)
        threading.Thread(target=self._check, daemon=True, name="mas-update").start()
        return self.state()

    def _check(self) -> None:
        try:
            found = update.latest()
        except Exception as e:
            _log.warning("could not ask about updates", exc_info=True)
            return self._set(state="failed", detail=self.why(e))
        if not update.is_newer(found["version"], __version__):
            _log.info("version %s is the newest there is", __version__)
            return self._set(state="current", detail=found["version"])
        _log.info("version %s is available, we are %s", found["version"], __version__)
        self._found = found
        self._set(state="available", detail=found["version"],
                  notes=found.get("notes", ""))

    def install(self) -> dict:
        if not self._found:
            self._set(state="failed", detail="release")
            return self.state()
        self._set(state="downloading", detail="", percent=0)
        threading.Thread(target=self._install, daemon=True, name="mas-update").start()
        return self.state()

    def _install(self) -> None:
        found = self._found
        try:
            def progress(got: int, total: int) -> None:
                # Without a length there is no percentage to show, and inventing
                # one that creeps along is worse than showing none.
                if total:
                    self._set(percent=min(100, round(got * 100 / total)))

            path = update.download(found["url"], progress)
        except Exception as e:
            _log.warning("the update did not download", exc_info=True)
            return self._set(state="failed", detail=self.why(e))

        self._set(state="checking_file", percent=100)
        try:
            signature = bytes.fromhex(found["signature"])
        except ValueError:
            signature = b""
        if not update.verify(path, signature):
            # Loudly, and the file goes. Something is calling itself our release
            # and is not, and the one thing that must not happen next is running it.
            _log.error("the downloaded installer is not signed by us — deleting it")
            path.unlink(missing_ok=True)
            return self._set(state="failed", detail="signature")
        _log.info("the installer is signed by us, handing over")
        self._set(state="installing")
        try:
            update.install(path)
        except Exception as e:
            _log.exception("the installer would not start")
            return self._set(state="failed", detail=self.why(e))
        self._on_installed()     # release our files: the installer is replacing them

    @staticmethod
    def why(e: Exception) -> str:
        """A reason short enough for the panel and specific enough to act on."""
        import socket
        import urllib.error
        if isinstance(e, urllib.error.HTTPError):
            return f"HTTP {e.code}"
        if isinstance(e, (urllib.error.URLError, socket.timeout, OSError)):
            return "network"
        if isinstance(e, ValueError):
            # Our own refusals: a release description that is incomplete, or
            # points somewhere we do not fetch from. The log has the specifics.
            return "release"
        return type(e).__name__
