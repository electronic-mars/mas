"""Bridge between Python and the interface.

Over local HTTP rather than js_api: in a previous project js_api turned out to be
unreliable in a built exe — the window came up empty. The server listens on
127.0.0.1 only, on a random port, and every call requires a session token.
"""
import json
import mimetypes
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import log
from .paths import data_dir, ui_dir

_log = log.get("bridge")

TOKEN_HEADER = "X-MAS-Token"
# What another program on this machine has to read to talk to us. The port is
# picked at random every run and so is the token, which is exactly right for
# keeping strangers out and exactly wrong for a friend trying to find us — so we
# leave a note. Deleted on the way out, and the reader is expected to check by
# calling rather than to trust a file that a crash may have left behind.
#
# The token in a file means any program running as this person can ask us to
# switch the sound. That is the same boundary they already have: they can send
# us keystrokes, kill us, or replace our exe. It is not the same as letting a web
# page do it, which is what the token is actually there to prevent.
NOTE = "bridge.json"
# 2: the heartbeat says whether the dock is actually drawing us. Under 1 a dock
# that was alive but showed nothing kept the tray icon for ever, and the program
# ran with no way in at all.
PROTOCOL = 2
_TOKEN_MARK = "%%MAS_TOKEN%%"  # must not match a JS var name, or substitution breaks it

# The window is drawn by WebView2, which is Chromium, and Chromium refuses to
# open a page on any of the ports once used by services it does not want a web
# page talking to — SMTP, NFS, PPTP and their neighbours. Asking Windows for
# "any free port" is therefore not safe: the answer can be one of those, and the
# window comes up as ERR_UNSAFE_PORT with no hint as to why. It happened on a
# machine whose dynamic port range had been moved down to start at 1024, and the
# port handed out was 1723, which is PPTP.
#
# The whole list lives in net/base/port_util.cc in Chromium; the largest entry in
# it is 10080. Rather than copy eighty numbers that someone may add to, we simply
# stay above all of them.
FIRST_SAFE_PORT = 10081
LAST_PORT = 65535
PORT_TRIES = 50


class Bridge:
    def __init__(self, api: object, ui_dir_override: Path | None = None):
        self.api = api
        self.ui_dir = ui_dir_override or ui_dir()
        self.token = secrets.token_urlsafe(32)
        self._srv: ThreadingHTTPServer | None = None
        self.port = 0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> str:
        handler = _make_handler(self)
        ThreadingHTTPServer.daemon_threads = True  # request threads do not outlive exit
        for _ in range(PORT_TRIES):
            want = FIRST_SAFE_PORT + secrets.randbelow(LAST_PORT - FIRST_SAFE_PORT + 1)
            try:
                self._srv = ThreadingHTTPServer(("127.0.0.1", want), handler)
                break
            except OSError:
                continue        # somebody else has it; there are fifty thousand more
        else:
            # Fifty taken ports in a row means something is very wrong with this
            # machine, and a window that might not open beats no program at all.
            _log.warning("no free port above %d after %d tries — letting Windows "
                         "choose, which it may choose badly", FIRST_SAFE_PORT, PORT_TRIES)
            self._srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self._srv.server_address[1]
        threading.Thread(target=self._srv.serve_forever, daemon=True, name="mas-bridge").start()
        _log.info("bridge is up on %s, interface from %s", self.url, self.ui_dir)
        self._announce()
        return self.url

    def _announce(self) -> None:
        """Leave the address and the key where a companion program can find them."""
        from . import __version__
        note = {"protocol": PROTOCOL, "url": self.url, "token": self.token,
                "pid": os.getpid(), "version": __version__}
        path = data_dir() / NOTE
        try:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(note, indent=2), encoding="utf-8")
            tmp.replace(path)   # never half a file: the reader may arrive mid-write
        except OSError:
            _log.warning("could not write %s — the dock will not find us", NOTE,
                         exc_info=True)

    def _withdraw(self) -> None:
        try:
            (data_dir() / NOTE).unlink(missing_ok=True)
        except OSError:
            _log.warning("could not remove %s", NOTE, exc_info=True)

    def stop(self) -> None:
        self._withdraw()
        if self._srv:
            self._srv.shutdown()
            self._srv = None

    def call(self, method: str, payload: dict):
        fn = getattr(self.api, method, None)
        if not callable(fn) or method.startswith("_"):
            raise AttributeError(f"no such method: {method}")
        return fn(**payload) if payload else fn()


def _make_handler(bridge: "Bridge"):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass  # our own log, not stderr

        def handle_error(self, request, client_address):
            """The window is closed mid-request — the connection breaks. That is
            normal, not an error: without this handler tracebacks flood the log."""
            import sys as _sys
            exc = _sys.exc_info()[1]
            if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
                return
            _log.warning("failure in the request handler", exc_info=True)

        # --- security -----------------------------------------
        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is None:
                return True  # ordinary window navigation
            return origin == f"http://127.0.0.1:{bridge.port}"

        def _token_ok(self) -> bool:
            return secrets.compare_digest(self.headers.get(TOKEN_HEADER, ""), bridge.token)

        # --- responses ----------------------------------------
        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        # --- GET: static files --------------------------------
        def do_GET(self):
            rel = self.path.split("?", 1)[0].lstrip("/") or "index.html"

            # Application icons live in an on-disk cache, not in the interface folder.
            if rel.startswith("appicon/"):
                from .core.appicons import cache_dir
                base = cache_dir().resolve()
                target = (base / rel[len("appicon/"):]).resolve()
                try:
                    target.relative_to(base)
                except ValueError:
                    return self._send(403, b"forbidden", "text/plain")
                if not target.is_file():
                    return self._send(404, b"not found", "text/plain")
                return self._send(200, target.read_bytes(), "image/png")

            target = (bridge.ui_dir / rel).resolve()
            try:
                target.relative_to(bridge.ui_dir.resolve())
            except ValueError:
                return self._send(403, b"forbidden", "text/plain")
            if not target.is_file():
                return self._send(404, b"not found", "text/plain")

            data = target.read_bytes()
            if target.name == "index.html":
                data = data.replace(_TOKEN_MARK.encode(), bridge.token.encode())
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith(("javascript", "json")):
                ctype += "; charset=utf-8"
            self._send(200, data, ctype)

        # --- POST: method call --------------------------------
        def do_POST(self):
            if not self.path.startswith("/api/"):
                return self._send(404, b"not found", "text/plain")
            if not self._origin_ok():
                _log.warning("rejected Origin: %s", self.headers.get("Origin"))
                return self._json(403, {"error": "bad origin"})
            if not self._token_ok():
                _log.warning("rejected call without a token: %s", self.path)
                return self._json(403, {"error": "bad token"})

            method = self.path[len("/api/"):]
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return self._json(400, {"error": "bad json"})

            # Compute the response first, then send it. Otherwise a connection drop
            # while sending looks like an error in the method, though it did its job.
            try:
                body = {"ok": True, "result": bridge.call(method, payload)}
                code = 200
            except Exception as e:
                _log.exception("error in method %s", method)
                body, code = {"ok": False, "error": f"{type(e).__name__}: {e}"}, 500

            try:
                self._json(code, body)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass  # window closed while the response was computed — normal

    return Handler
