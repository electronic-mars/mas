"""Entry point: tray, window and core."""
import ctypes
import gc
import os
import queue
import sys
import threading
import time

import logging

from . import __version__, log
from .bridge import Bridge
from .core import devices, mixer, startup
from .core.config import Config
from .core.dongle import KNOWN as KNOWN_DONGLES
from .core.dongle import MAX_CAPTURE, Dongle, deduce, product_name
from .core.hotkey import Hotkeys
from .core.meter import Meter
from .core.players import Players
from .core import language, runtime, screen, strings, update
from .overlay import Overlay
from .core.switcher import Switcher
from .paths import is_frozen, log_path
from .tray import Tray

_log = log.get("app")

# Local, not Global. A standard user is not allowed to create a Global mutex:
# CreateMutexW then fails with "access denied" rather than "already exists", the
# check below reads that as "nobody here", and a second copy starts as if the
# first did not exist — silently, on exactly the machines a per-user installer
# targets. Per session is also what we want: one tray icon per signed-in person.
MUTEX_NAME = "Local\\MasterAudioSwitcherSingleInstance"
ERROR_ALREADY_EXISTS = 183
FULL_SIZE = (440, 772)      # full window view in logical points, before fitting
# The window is created under this name, and goes back to it whenever there is
# no track to show. It is also what the window is first found by — see own_hwnd.
WINDOW_TITLE = "Master Audio Switcher"


def already_running() -> bool:
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return kernel32.GetLastError() == ERROR_ALREADY_EXISTS


class Api:
    """Methods available to the interface through the bridge."""

    def __init__(self, app: "App"):
        self.app = app
        self.selfcheck_seen = False

    def selfcheck(self, **kw):
        self.selfcheck_seen = True
        _log.info("SELFCHECK: the interface reached the bridge")
        return {"python": sys.version.split()[0], "frozen": is_frozen(), "log": str(log_path())}

    def get_state(self):
        return self.app.state()

    def switch_next(self):
        self.app.cycle()
        return self.app.state()

    def switch_to(self, device_id: str):
        self.app.note_manual_switch()
        if device_id.startswith(devices.OUTPUT_PREFIX):
            self.app._go(device_id)          # same path as the tray: the mic follows
        else:
            # The microphone was chosen by hand. If it belongs to no headset,
            # then this is the person's base microphone.
            if device_id not in devices.tied_microphones():
                self.app._mic_base = device_id
            self.app.go_microphone(device_id)
        return self.app.state()

    def toggle_cycle(self, device_id: str, enabled: bool):
        self.app.switcher.toggle_in_cycle(device_id, enabled)
        return self.app.state()

    def reorder(self, device_ids: list):
        self.app.switcher.reorder(device_ids)
        return self.app.state()

    def set_icon(self, device_id: str, glyph: str):
        icons = dict(self.app.cfg.get("icons"))
        icons[device_id] = glyph
        self.app.cfg.set("icons", icons)
        self.app.refresh_tray()
        return self.app.state()

    def set_setting(self, key: str, value):
        if key == "autostart" and not startup.set_enabled(bool(value)):
            return self.app.state()  # registry refused — don't lie about it
        self.app.cfg.set(key, value)
        if key == "language":
            strings.use(value)
            self.app.refresh_tray()
        elif key == "hotkey":
            self.app.hotkeys.bind("switch", value)
        elif key == "hotkey_play":
            self.app.hotkeys.bind("play", value)
        elif key == "priority_player":
            self.app.players.set_priority(value)
        elif key in ("auto_device", "watch_dongle"):
            self.app.sync_auto_device()
        return self.app.state()

    # --- updating ------------------------------------------------------
    def update_action(self, action: str):
        """One entry point: check, install, poll, forget."""
        app = self.app
        if action == "check":
            return app.update_check()
        if action == "install":
            return app.update_install()
        if action == "forget":
            return app.update_forget()
        raise ValueError(f"no such action: {action}")

    # --- teaching an unknown dongle ------------------------------------
    def dongle_wizard(self, action: str, step: str = ""):
        """One entry point for the wizard: start, step, poll, finish, cancel."""
        app = self.app
        if action == "start":
            return app.wizard_start()
        if action == "step":
            return app.wizard_step(step)
        if action == "poll":
            return app.wizard_state()
        if action == "finish":
            return app.wizard_finish()
        if action == "cancel":
            app.wizard_stop()
            app.sync_dongle()
            return {"running": False}
        raise ValueError(f"no such action: {action}")

    # --- mixer and volume --------------------------------------------
    def get_mixer(self):
        snap = self.app.meter.snapshot()
        return {
            "master": {"volume": snap["volume"], "muted": snap["muted"]},
            "device": snap["device"],
            "sessions": [vars(s) for s in mixer.list_sessions()],
        }

    def set_master(self, value: float):
        self.app.meter.set_volume(value)
        return True

    def set_master_mute(self, muted: bool):
        self.app.meter.set_mute(muted)
        return True

    def set_app_volume(self, key: str, value: float):
        return mixer.set_volume(key, value)

    def set_app_mute(self, key: str, muted: bool):
        return mixer.set_mute(key, muted)

    def get_meter(self):
        """A ready snapshot from the meter thread plus signals for the interface.
        COM is not touched here at all."""
        return {**self.app.meter.snapshot(), **self.app.take_ui_signal()}

    # --- other ---------------------------------------------------------
    def complete_onboarding(self):
        self.app.cfg.set("onboarded", True)
        return True

    def open_url(self, url: str):
        import webbrowser
        if not url.startswith(("http://", "https://")):
            raise ValueError("link is not allowed")
        webbrowser.open(url)
        return True

    def open_startup_settings(self):
        """Windows' own startup list. In a package that is where autostart
        actually lives — our registry entry would be written into the package's
        private copy of the registry and start nothing."""
        import subprocess
        subprocess.Popen(["explorer", "ms-settings:startupapps"])
        return True

    def open_data_folder(self):
        """Show the log folder — nobody types a %LOCALAPPDATA% path by hand."""
        from .paths import data_dir
        import subprocess
        subprocess.Popen(["explorer", str(data_dir())])
        return True

    def media(self, action: str):
        """Pause and track skipping go to the chosen player, not to the one the
        system guessed. The selection rule is described in core/players.py."""
        self.app.players.command(action)
        return True

    def now_playing(self):
        """Who we control and what is playing. The snapshot is updated by the
        players thread."""
        self.app.players.refresh()
        return self.app.players.snapshot()

    def set_mini(self, on: bool, height: int | None = None):
        return self.app.set_mini(on, height)

    def hide_window(self):
        self.app.hide()
        return True

    def quit(self):
        self.app.quit()
        return True


class App:
    def __init__(self):
        self.cfg = Config()
        self.switcher = Switcher(self.cfg)
        self.meter = Meter(on_devices_changed=self._devices_changed,
                           on_default_changed=self._default_changed)
        if not self.cfg.get("language"):
            self.cfg.set("language", language.pick())
        # The tray and the notifications speak the same language as the window.
        strings.use(self.cfg.get("language"))
        self.players = Players(on_track=self.refresh_tip, on_dead=self._player_dead,
                               on_new_app=self.push_state)
        self.players.set_priority(self.cfg.get("priority_player"))
        self.hotkeys = Hotkeys(
            {"switch": self.cycle, "play": lambda: self.players.command("play")},
            {"switch": self.cfg.get("hotkey"), "play": self.cfg.get("hotkey_play")})
        self._device_tip = strings.t("starting")
        self.api = Api(self)
        self.bridge = Bridge(self.api)
        self.window = None      # webview.Window, but the module loads later — see run()
        self.tray: Tray | None = None
        self.overlay = Overlay()
        self._quitting = False
        # Version of the engine the window is drawn with, None when it is not
        # installed. Then there is no window at all, and the program lives in
        # the tray alone — where its main job is done anyway.
        self._engine: str | None = None
        self._engine_asking = False
        self._stopped = threading.Event()
        self.launched_by_startup = startup.STARTUP_FLAG in sys.argv[1:]
        self._ui_lock = threading.Lock()
        self._pending_tab: str | None = None
        self._state_rev = 0
        # Mini view is session state, not a setting: it is not written to config.
        self._mini = False
        self._mini_height = 250
        # The full height the window is allowed on this screen. The real value
        # is measured in run(), once the window module has set DPI awareness.
        self._full_height = FULL_SIZE[1]
        # Whether the window is visible. A hidden window keeps drawing: the page
        # does not know about it (document.hidden stays false for a hidden
        # window), so the knowledge comes from Python on the next poll.
        self._visible = False
        # Snapshot of the "known outputs" list: dropped on a device-set event,
        # not on a timer.
        self._known_cache: list[dict] | None = None
        self._known_pinned = ""
        # Where to return the sound when the priority device disappears, and
        # whether we are holding it right now. If the person left it by hand,
        # we do not interfere.
        self._auto_prev: str | None = None
        self._auto_held = False
        # The base microphone is the one a person uses without a headset.
        self._mic_base: str | None = None
        # USB dongle listener and the recognized headset name for the interface.
        self.dongle: Dongle | None = None
        self._dongle_name: str | None = None
        self._dongle_usb: str | None = None
        # Last known headset state: None means we have not heard from it yet.
        self._dongle_on: bool | None = None
        # The teaching wizard, while it is running: its buckets and its own
        # listener, which holds the dongle instead of the watcher above.
        self._wiz: dict | None = None
        self._wiz_dongle: Dongle | None = None
        # What the window is called right now, and its handle. The title follows
        # the track, so the handle has to be remembered rather than looked up by
        # a name that no longer stands still.
        self._title = WINDOW_TITLE
        self._hwnd: int | None = None
        # Where the update button has got to, and what the release page offered.
        self._up: dict = {"state": "idle", "detail": "", "percent": 0, "notes": ""}
        self._up_lock = threading.Lock()
        self._up_found: dict | None = None
        self._jobs: queue.SimpleQueue = queue.SimpleQueue()

    def own_hwnd(self) -> int | None:
        """Our window, found once and kept."""
        if self._hwnd is None:
            self._hwnd = screen.own_window(WINDOW_TITLE)
        return self._hwnd

    # --- updating -------------------------------------------------------
    # The whole thing is one small state, read by the page four times a second
    # while anything is happening and left alone otherwise. Every ending is
    # named: "failed" carries a reason, because a button that quietly returns to
    # how it was is the one thing worse than a button that says what went wrong.
    def update_state(self) -> dict:
        with self._up_lock:
            return dict(self._up)

    def _update_set(self, **fields) -> None:
        with self._up_lock:
            self._up.update(fields)
        self.push_state()

    def update_forget(self) -> dict:
        """Back to the plain button — the page asks for this after showing an
        answer that has been read."""
        self._update_set(state="idle", detail="", percent=0)
        return self.update_state()

    def update_check(self) -> dict:
        if update.from_store():
            return self.update_state()      # the Store does this, and does it better
        self._update_set(state="checking", detail="", percent=0)
        threading.Thread(target=self._update_check, daemon=True, name="mas-update").start()
        return self.update_state()

    def _update_check(self) -> None:
        try:
            found = update.latest()
        except Exception as e:
            _log.warning("could not ask about updates", exc_info=True)
            return self._update_set(state="failed", detail=self._why(e))
        if not update.is_newer(found["version"], __version__):
            _log.info("version %s is the newest there is", __version__)
            return self._update_set(state="current", detail=found["version"])
        _log.info("version %s is available, we are %s", found["version"], __version__)
        self._up_found = found
        self._update_set(state="available", detail=found["version"],
                         notes=found.get("notes", ""))

    def update_install(self) -> dict:
        if not self._up_found:
            self._update_set(state="failed", detail="release")
            return self.update_state()
        self._update_set(state="downloading", detail="", percent=0)
        threading.Thread(target=self._update_install, daemon=True,
                         name="mas-update").start()
        return self.update_state()

    def _update_install(self) -> None:
        found = self._up_found
        try:
            def progress(got: int, total: int) -> None:
                # Without a length there is no percentage to show, and inventing
                # one that creeps along is worse than showing none.
                if total:
                    self._update_set(percent=min(100, round(got * 100 / total)))

            path = update.download(found["url"], progress)
        except Exception as e:
            _log.warning("the update did not download", exc_info=True)
            return self._update_set(state="failed", detail=self._why(e))

        self._update_set(state="checking_file", percent=100)
        try:
            signature = bytes.fromhex(found["signature"])
        except ValueError:
            signature = b""
        if not update.verify(path, signature):
            # Loudly, and the file goes. Something is calling itself our release
            # and is not, and the one thing that must not happen next is running it.
            _log.error("the downloaded installer is not signed by us — deleting it")
            path.unlink(missing_ok=True)
            return self._update_set(state="failed", detail="signature")
        _log.info("the installer is signed by us, handing over")
        self._update_set(state="installing")
        try:
            update.install(path)
        except Exception as e:
            _log.exception("the installer would not start")
            return self._update_set(state="failed", detail=self._why(e))
        self.quit()          # release our files: the installer is replacing them

    @staticmethod
    def _why(e: Exception) -> str:
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

    def device_name(self, device_id: str) -> str:
        """The name of an endpoint, present or not. From the cached list, so it
        costs nothing — enumerating the disabled ones takes half a second."""
        if not device_id:
            return ""
        return next((d["name"] for d in self.known_outputs_cached(device_id)
                     if d["id"] == device_id), "")

    # --- state for the interface ---------------------------------------
    def state(self) -> dict:
        cur_out = devices.default_id(is_output=True)
        cur_in = devices.default_id(is_output=False)
        icons = self.cfg.get("icons")
        cycle = self.cfg.get("cycle")
        devs = devices.list_devices(only_active=True)

        def pack(d: devices.Device) -> dict:
            return {
                "id": d.id, "name": d.name, "kind": d.kind,
                "icon": icons.get(d.id) or devices.guess_icon(d.name, d.is_output),
                "in_cycle": d.id in cycle,
                "is_default": d.id == (cur_out if d.is_output else cur_in),
            }

        outputs = [pack(d) for d in devs if d.is_output]
        outputs.sort(key=lambda x: cycle.index(x["id"]) if x["id"] in cycle else len(cycle))
        settings = self.cfg.all()
        # One source for the version number: the package. It used to be written
        # out again as a literal in the page, and would have drifted from the
        # build on the very first release.
        settings["version"] = __version__
        settings["autostart"] = startup.is_enabled()  # source of truth is the registry
        settings["hotkey_ok"] = self.hotkeys.ok["switch"]
        settings["hotkey_play_ok"] = self.hotkeys.ok["play"]
        settings["players"] = self.players.known_apps()
        # Installed from the Store, updating is the Store's job: the button
        # would be against its rules and would duplicate work already done.
        settings["from_store"] = update.from_store()
        # The update button's whole state travels with everything else, so the
        # page needs no poller of its own: the counter it already watches is
        # bumped on every step, including each slice of the download.
        settings["update"] = self.update_state()
        settings["dongle_name"] = self._dongle_name
        settings["dongle_usb"] = self._dongle_usb
        known = self.known_outputs_cached(settings.get("auto_device", ""))
        return {
            "outputs": outputs,
            "inputs": [pack(d) for d in devs if not d.is_output],
            "known_outputs": known,
            "settings": settings,
        }

    def known_outputs_cached(self, pinned: str = "") -> list[dict]:
        """The same list, but computed once.

        Enumerating every endpoint, including the disabled ones, costs half a
        second, and the window asks for the state on every refresh. The set of
        devices changes rarely, and the watcher tells us when it does — the
        snapshot is dropped on that, not on a timer.
        """
        if self._known_cache is None or self._known_pinned != pinned:
            self._known_cache = self.known_outputs(pinned)
            self._known_pinned = pinned
        return self._known_cache

    def forget_known(self) -> None:
        self._known_cache = None

    @staticmethod
    def known_outputs(pinned: str = "") -> list[dict]:
        """The list for choosing the priority device.

        You have to choose it exactly when the headphones are off, so the
        endpoints that are absent right now are needed too. But Windows piles up
        their duplicates over the years: four separate "Digital Audio (HDMI)"
        entries add up. Identical names mean one and the same jack, so we keep
        one record per name, preferring a live one, and drop unnamed endpoints
        entirely.
        """
        best: dict[str, devices.Device] = {}
        for d in devices.list_devices(only_active=False):
            # "Device" is the fallback name devices.py gives an endpoint that
            # reports none of its own — it is data, and must match that literal.
            if not d.is_output or d.name in ("", "Device"):
                continue
            kept = best.get(d.name)
            # The already selected device must stay in the list, otherwise the
            # setting would look reset even though it is in force.
            if kept is None or d.id == pinned or (d.active and not kept.active
                                                  and kept.id != pinned):
                best[d.name] = d
        ordered = sorted(best.values(), key=lambda d: (not d.active, d.name.lower()))
        return [{"id": d.id, "name": d.name, "active": d.active} for d in ordered]

    def current_device(self) -> devices.Device | None:
        cur = devices.default_id(is_output=True)
        return next((d for d in devices.list_devices() if d.id == cur), None) if cur else None

    # --- actions --------------------------------------------------------
    def cycle(self) -> None:
        """The icon changes BEFORE the sound is switched.

        Changing the device in Windows takes about 90 ms, and if the icon is
        drawn after that, the person sees the response with a delay and decides
        the click did not work. Show the result first, do the work second.
        """
        target = self.switcher.next_id()
        if target is None:
            if self.tray:
                self.tray.notify(strings.t("msg_none_marked"))
            return
        self.note_manual_switch()
        self._go(target)

    def _go(self, device_id: str) -> None:
        """The common switching path: icon first, sound second.

        The icon changes before the switch for the sake of responsiveness —
        changing the device in Windows takes about 90 ms. But if the system
        refuses, what was shown has to be taken back: a utility with a single
        job has no right to lie about whether it did that job.
        """
        dev = self.switcher.device_by_id(device_id)
        self.show_device(dev)
        try:
            done = self.switcher.switch_to(device_id)
        except Exception:
            # The device managed to disappear between drawing the list and the
            # click: Windows answers "element not found". That is no reason to
            # crash, but staying silent is not an option either — the icon
            # already shows the wrong thing.
            _log.warning("the switch failed with an error", exc_info=True)
            done = None
        if done is None:
            _log.warning("the switch did not happen, reverting the icon")
            self.show_device(self.current_device())
            if self.tray:
                self.tray.notify(strings.t("msg_switch_failed"))
            self.push_state()
            return
        self._follow_microphone(device_id)
        self.announce(dev, tray_done=True)

    def go_microphone(self, device_id: str) -> None:
        """A microphone picked by hand in the list.

        Outputs get the whole ceremony in _go, including taking the tray icon
        back when the system refuses. A microphone has no tray icon, so the
        refusal used to pass in complete silence: announce(None) returns at once
        and the row in the list kept showing the old choice with no explanation.
        The switch is verified the same way — it just has to be said out loud.
        """
        try:
            dev = self.switcher.switch_to(device_id)
        except Exception:
            _log.warning("the microphone switch failed with an error", exc_info=True)
            dev = None
        if dev is None:
            _log.warning("the microphone did not switch")
            if self.tray:
                self.tray.notify(strings.t("msg_mic_failed"))
            self.push_state()
            return
        self.announce(dev)

    def _follow_microphone(self, output_id: str) -> None:
        """The mic follows the headset; on speakers the base one comes back.

        Asking "which microphone was it a minute ago" is not allowed: Windows
        sometimes moves the microphone to the headset before we do, and then the
        previous one turns out to be that very microphone. So the base
        microphone is determined by meaning — it is the one that belongs to no
        headset.

        The communications role is always included: a microphone is needed
        exactly for talking.
        """
        if not self.cfg.get("switch_microphone"):
            return
        try:
            mic = devices.microphone_of(output_id)
            cur = devices.default_id(is_output=False, max_age=0.0)
            if mic is not None:
                if mic.id != cur:
                    devices.set_default(mic.id, include_communications=True)
                    _log.info("the microphone moved to %s", mic.name)
                return
            if cur and cur not in devices.tied_microphones():
                self._mic_base = cur   # belongs to no headset — so it is the base
                return
            base = self._mic_base or devices.standalone_microphone()
            if base and base != cur:
                devices.set_default(base, include_communications=True)
                self._mic_base = base
                _log.info("the microphone is back on the base one")
            elif not base:
                _log.info("no base microphone known — leaving the microphone alone")
        except Exception:
            _log.exception("could not switch the microphone")

    # --- priority device -------------------------------------------------
    def note_manual_switch(self) -> None:
        """The person switched by hand — so we no longer "hold" the headphones,
        and there is no need to butt in with our fallback when they vanish."""
        self._auto_held = False

    def sync_auto_device(self) -> None:
        """The setting could have been turned on while the headphones are
        already connected. We consider them held if the sound really is on them
        — otherwise the very first time they are turned off the setting would
        look like it does nothing."""
        auto = self.cfg.get("auto_device")
        self._auto_held = bool(auto) and devices.default_id(is_output=True, max_age=0.0) == auto
        self._auto_prev = None
        self.sync_dongle()

    def dongle_ids(self) -> tuple[int, int] | None:
        """The USB identifiers of the priority device, if it has any."""
        auto = self.cfg.get("auto_device")
        return devices.usb_ids_of(auto) if auto else None

    def dongle_rule(self, ids: tuple[int, int]) -> dict | None:
        """A shipped model first, then whatever this copy worked out itself."""
        rule = KNOWN_DONGLES.get(ids)
        if rule is not None:
            return rule
        return self.cfg.get("dongle_rules").get(f"{ids[0]:04X}:{ids[1]:04X}")

    def sync_dongle(self) -> None:
        """Start or stop the dongle listener to match the current settings."""
        if self.dongle is not None:
            self.dongle.stop()
            self.dongle = None
        self._dongle_name = self._dongle_usb = None
        ids = self.dongle_ids()
        if ids is None:
            return                            # not USB — no dongle can be here
        self._dongle_usb = f"{ids[0]:04X}:{ids[1]:04X}"
        rule = self.dongle_rule(ids)
        if rule is None:
            return                            # unknown: the wizard is offered instead
        self._dongle_name = rule["name"]      # the interface will show a toggle
        if self._wiz is not None or not self.cfg.get("watch_dongle"):
            return                            # the wizard is holding the dongle
        self.dongle = Dongle(ids[0], ids[1], self._dongle_changed, rule=rule)
        self.dongle.start()

    # --- teaching an unknown dongle ----------------------------------------
    # Four steps, not two: one on and one off would also be told apart by a
    # battery reading or a counter, and a wrong byte means headphones that grab
    # the sound at random. Two full cycles throw those out — see dongle.deduce.
    WIZARD_STEPS = ("on1", "off1", "on2", "off2")

    def wizard_start(self) -> dict:
        """Begin teaching. Listening runs from here to the end without a break:
        the reports simply land in the bucket of whichever step is running, so
        nothing is lost while the person is reaching for the headset."""
        self.wizard_stop()
        ids = self.dongle_ids()
        if ids is None:
            return {"error": "no_dongle"}
        self._wiz = {"ids": ids, "step": "", "last": 0.0,
                     "steps": {s: [] for s in self.WIZARD_STEPS}}
        self.sync_dongle()                    # let go of the watcher, if any
        self._wiz_dongle = Dongle(ids[0], ids[1], self._wizard_report, learn=True)
        self._wiz_dongle.start()
        return self.wizard_state()

    def wizard_step(self, step: str) -> dict:
        """Move to a step. Everything arriving from now on belongs to it."""
        if self._wiz is None:
            return {"error": "not_running"}
        if step not in self.WIZARD_STEPS:
            raise ValueError(f"no such step: {step}")
        self._wiz["step"] = step
        self._wiz["last"] = 0.0
        return self.wizard_state()

    def _wizard_report(self, data: bytes) -> None:
        """Called from a dongle thread for every report that arrives."""
        wiz = self._wiz
        if wiz is None or wiz["step"] not in wiz["steps"]:
            return
        bucket = wiz["steps"][wiz["step"]]
        if len(bucket) < MAX_CAPTURE:
            bucket.append(data)
        wiz["last"] = time.monotonic()

    def wizard_state(self) -> dict:
        """What the page needs to draw the current step.

        "settled" is the answer to the only hard question here: has the dongle
        finished speaking? A headset takes seconds to power up and then sends
        several reports in a row; moving on in the middle of that would file the
        rest of them under the next step.
        """
        wiz = self._wiz
        if wiz is None:
            return {"running": False}
        counts = {s: len(v) for s, v in wiz["steps"].items()}
        heard = counts.get(wiz["step"], 0)
        return {"running": True, "step": wiz["step"], "counts": counts,
                "heard": heard,
                "settled": bool(heard) and time.monotonic() - wiz["last"] > 1.2}

    def wizard_stop(self) -> None:
        if self._wiz_dongle is not None:
            self._wiz_dongle.stop()
            self._wiz_dongle = None
        self._wiz = None

    def wizard_finish(self) -> dict:
        """Read the four buckets, save what was learned, and prepare the report."""
        wiz = self._wiz
        if wiz is None:
            return {"error": "not_running"}
        ids = wiz["ids"]
        steps = wiz["steps"]
        on = steps["on1"] + steps["on2"]
        off = steps["off1"] + steps["off2"]
        rule = deduce(on, off) if on and off else None
        usb = f"{ids[0]:04X}:{ids[1]:04X}"
        name = (product_name(*ids)
                or self.device_name(self.cfg.get("auto_device")) or usb)
        if rule is not None:
            rule = {**rule, "name": name}
            rules = {**self.cfg.get("dongle_rules"), usb: rule}
            self.cfg.set("dongle_rules", rules)
            # They just taught it; switching it on themselves afterwards would be
            # a step that exists only to be clicked.
            self.cfg.set("watch_dongle", True)
        text = self._wizard_report_text(usb, name, rule, steps)
        self.wizard_stop()
        self.sync_dongle()
        self.push_state()
        return {"ok": rule is not None, "name": name, "usb": usb,
                "detail": self._wizard_detail(rule), "report": text,
                "url": self._wizard_issue_url(usb, name, rule is not None, text)}

    @staticmethod
    def _wizard_detail(rule: dict | None) -> str:
        if rule is None:
            return ""
        pos, val = rule["marker"]
        return (f"report 0x{rule['report']:02X}, byte {rule['state_at']}: "
                f"on 0x{rule['on']:02X}, off 0x{rule['off']:02X} "
                f"(marker byte {pos} = 0x{val:02X})")

    def _wizard_report_text(self, usb: str, name: str, rule: dict | None,
                            steps: dict) -> str:
        """The whole finding as plain text, ready to be read by a person.

        Repeated lines are collapsed: a dongle that says the same thing forty
        times adds nothing but length, and the count says it better.
        """
        out = [f"Dongle: {usb} — {name or 'unnamed'}",
               f"Audio device: {self.device_name(self.cfg.get('auto_device'))}",
               f"Program: {__version__}", ""]
        if rule is None:
            out.append("Result: no byte told the two states apart.")
        else:
            out.append(f"Result: {self._wizard_detail(rule)}")
            if rule.get("also"):
                out.append("Other bytes that would have worked too: " + ", ".join(
                    f"byte {i}: on 0x{a:02X}, off 0x{b:02X}" for i, a, b in rule["also"]))
        for step in self.WIZARD_STEPS:
            seen: dict[str, int] = {}
            for data in steps[step]:
                line = data.hex(" ")
                seen[line] = seen.get(line, 0) + 1
            out.append("")
            out.append(f"[{step}] {len(steps[step])} reports")
            out.extend(f"  {line}" + (f"   ×{n}" if n > 1 else "")
                       for line, n in seen.items())
        return "\n".join(out)

    @staticmethod
    def _wizard_issue_url(usb: str, name: str, ok: bool, text: str) -> str:
        """The report form, with its fields already filled in.

        Through the template rather than a blank issue: the template carries the
        label and the questions, and its field ids are what these parameters
        fill. Sending it is the person's click and their decision — the program
        itself sends nothing anywhere, ever.
        """
        from urllib.parse import urlencode
        query = urlencode({
            "template": "dongle.yml",
            "title": f"Dongle: {name or usb}",
            "model": name,
            "ids": usb,
            "reports": text,
            "worked": "yes" if ok else "no",
        })
        return f"https://github.com/electronic-mars/mas/issues/new?{query}"

    def _dongle_changed(self, on: bool) -> None:
        """The dongle reported that the headset was turned on or off.

        Reports arrive in batches: at startup the dongle dumps several of them
        in a row, and each one used to count as an event — the program threw the
        sound back and forth several times a second (314 such events in the
        log). We react only to a change of state.
        """
        if on == self._dongle_on:
            return
        self._dongle_on = on
        auto = self.cfg.get("auto_device")
        if not auto:
            return
        if on:
            self._dispatch(self._grab_auto, auto)
        elif self._auto_held:
            self._dispatch(self._release_auto, auto)

    def _devices_changed(self, added: set, removed: set) -> None:
        """Called from the meter thread: the set of endpoints has changed."""
        self.forget_known()
        self.push_state()
        auto = self.cfg.get("auto_device")
        if not auto:
            return
        if auto in added:
            job = self._grab_auto
        elif auto in removed and self._auto_held:
            job = self._release_auto
        else:
            return
        self._dispatch(job, auto)

    def _default_changed(self, device_id: str) -> None:
        """The default device changed — no matter who changed it."""
        self.refresh_tray()
        self.push_state()

    def _dispatch(self, job, auto: str) -> None:
        self._jobs.put((job, auto))

    def _job_loop(self) -> None:
        """One thread for the whole session that switches sound on events.

        Switching right in the meter thread is not allowed: enumerating devices
        creates pycaw objects, at the end the meter thread runs garbage
        collection, and objects belonging to other threads are released
        somewhere other than where they were created — the process crashes.
        Starting a thread per event is not allowed either: some of the objects
        end up in reference cycles, outlive the thread and are released in an
        already closed COM environment — the same crash. So there is one
        environment here and it lives to the end.
        """
        import comtypes
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        while True:
            job, auto = self._jobs.get()
            try:
                job(auto)
            except Exception:
                _log.exception("automatic switching failed")

    def _grab_auto(self, auto: str) -> None:
        current = devices.default_id(is_output=True, max_age=0.0)
        self._auto_held = True
        if current == auto:
            # Windows already gave the sound to the headphones on its own —
            # there is nothing to switch, but the tray icon is still ours and it
            # must show the new device.
            self.show_device(self.switcher.device_by_id(auto))
            self.push_state()
            return
        self._auto_prev = current
        _log.info("the priority device appeared, taking the sound")
        self._go(auto)

    def _release_auto(self, auto: str) -> None:
        self._auto_held = False
        present = {d.id for d in devices.list_devices(only_active=True) if d.is_output}
        back = self._auto_prev if self._auto_prev in present else None
        if back is None:
            # The previous device is gone too (or we never remembered it) — take
            # the first one marked in the cycle, just so the sound does not stay
            # nowhere.
            back = next((i for i in self.switcher.available() if i != auto), None)
        self._auto_prev = None
        if back is None:
            return
        _log.info("the priority device disappeared, returning the sound")
        self._go(back)

    def _button(self, pressed: str) -> None:
        if pressed == self.cfg.get("switch_button"):
            return self.cycle()
        hwnd = self.own_hwnd()
        if self._visible and hwnd and not screen.is_front(hwnd):
            # Open, but behind the browser — so from where the person is sitting
            # it is not open at all. Hiding it here is what the program used to
            # do, and it looked like the click did nothing: the first press put
            # away a window they could not see, and only the second brought it
            # back. A window that is not in front is asking to be brought
            # forward, not put away.
            screen.to_front(hwnd)
        elif self._visible:
            # The button that opened the window closes it. Until now the only
            # way back was the cross in the corner, and pressing the icon again
            # — the obvious thing to try — did nothing at all.
            self.hide()
        else:
            self.show("devices")

    def show_device(self, dev: devices.Device | None) -> None:
        """Only the icon and the tooltip — the fastest part of the feedback."""
        if dev is None or not self.tray:
            _log.warning("icon not updated: device %s, tray %s",
                         "not found" if dev is None else "there",
                         "there" if self.tray else "missing")
            return
        glyph = self.cfg.get("icons").get(dev.id) or devices.guess_icon(
            dev.name, dev.is_output)
        # Written to the log: the complaint "the tray icon never changed" is
        # otherwise impossible to settle.
        _log.info("tray icon: %s (%s)", glyph or "default", dev.name)
        self._device_tip = dev.name
        self.tray.set_device(glyph, self.tray_tip())

    def tray_tip(self) -> str:
        """The tooltip on the icon.

        While the music plays — only the track name. The program name, the
        player name and the device are things the person knows anyway, and
        because of them the main thing had to be read out of a long line. When
        there is no music there is nothing to show, and the line goes back to
        the device.
        """
        now = self.players.snapshot()
        if now["playing"]:
            track = " — ".join(x for x in (now["artist"], now["title"]) if x)
            if track:
                return track
        return f"Master Audio Switcher — {self._device_tip}"

    def window_title(self) -> str:
        """What the taskbar button says.

        While the music plays it is the track, the way Spotify does it, and for
        the same reason: the button is the one place the track can be read
        without switching to the program at all.
        """
        now = self.players.snapshot()
        if now["playing"]:
            track = " — ".join(x for x in (now["artist"], now["title"]) if x)
            if track:
                return track
        return WINDOW_TITLE

    def refresh_title(self) -> None:
        """Put the current title on the window.

        Only while it is visible: hidden, it has no taskbar button to read, and
        the call is not free — it crosses to the interface thread and waits for
        it. Measured on this machine at well under a millisecond, but it is
        skipped when there is nothing to show for it.
        """
        if not self.window or not self._visible:
            return
        title = self.window_title()
        if title == self._title:
            return
        try:
            self.window.set_title(title)
            self._title = title
        except Exception:
            _log.warning("the window title did not change", exc_info=True)

    def refresh_tip(self) -> None:
        """The track changed — refresh the tooltip without touching the icon."""
        if self.tray:
            self.tray.set_tip(self.tray_tip())
        self.refresh_title()

    def _player_dead(self, who: str) -> None:
        """The player is listed in the system but does not answer: usually the
        tab has already been closed."""
        if self.tray:
            self.tray.notify(strings.t("msg_player_dead", who))

    def announce(self, dev: devices.Device | None, tray_done: bool = False) -> None:
        """Feedback is mandatory: without it a person switches blind."""
        if dev is None:
            return
        if not tray_done:
            self.refresh_tray()
        if self.cfg.get("notify_on_switch"):
            self.overlay.show(
                self.cfg.get("icons").get(dev.id) or devices.guess_icon(dev.name, dev.is_output),
                dev.name, self._light_theme())
        if self.cfg.get("sound_on_switch"):
            self._beep()
        self.push_state()

    def _light_theme(self) -> bool:
        """The overlay follows the window theme, and with "like Windows" — the
        system theme."""
        mode = self.cfg.get("theme")
        if mode in ("light", "dark"):
            return mode == "light"
        from .tray import taskbar_is_light
        return taskbar_is_light()

    @staticmethod
    def _beep() -> None:
        """The tone plays on the default device, that is, already on the new one
        — you hear where the sound went. In a separate thread so the click is
        not held up."""
        def run():
            try:
                import winsound
                winsound.Beep(880, 90)
            except Exception:
                _log.warning("the beep did not play", exc_info=True)

        threading.Thread(target=run, daemon=True, name="mas-beep").start()

    def refresh_tray(self) -> None:
        if not self.tray:
            return
        dev = self.current_device()
        if dev is None:
            self.tray.set_device(
                None, f"Master Audio Switcher — {strings.t('device_unknown')}")
            return
        self.show_device(dev)

    def push_state(self) -> None:
        """Only mark that the state changed. The interface will fetch it."""
        with self._ui_lock:
            self._state_rev += 1

    # --- window ----------------------------------------------------------
    def set_mini(self, on: bool, height: int | None = None) -> bool:
        """Mini view: only the front panel is left, the window shrinks in height.

        The interface measures the height itself and sends it here: it depends
        on the fonts and the screen scale, and guessing it with a number in the
        code is lying to yourself. The mode is deliberately not kept between
        runs: otherwise one day a person gets a stub of a window at start and
        decides the program is broken.
        """
        hwnd = self.own_hwnd()
        if not hwnd:
            return False
        if height:
            self._mini_height = max(120, min(int(height), 420, self._full_height))
        self._mini = bool(on)
        size = (FULL_SIZE[0], self._mini_height if on else self._full_height)
        ok = screen.resize_at_tray(hwnd, *size)
        _log.info("mini view: %s, window %s×%s", on, *size)
        return ok

    def leave_mini(self) -> None:
        """Mini view is cancelled when we need to show what it does not have."""
        if self._mini:
            self.set_mini(False)
            self.push_state()

    def _offer_engine(self, modal: bool = False) -> None:
        """Say that the engine the window needs is missing, and offer to get it.

        A notification always; a dialog only when the person is standing at the
        screen — they started the program by hand, or they just clicked the icon
        asking for the window. From autostart it stays a notification, otherwise
        it would be a modal box in the face at every sign-in.
        """
        if self.tray:
            self.tray.notify(strings.t("msg_no_engine"))
        if not modal or self._engine_asking:
            return
        self._engine_asking = True
        threading.Thread(target=self._engine_dialog, daemon=True,
                         name="mas-engine").start()

    def _engine_dialog(self) -> None:
        MB_YESNO, MB_ICONWARNING, IDYES = 0x4, 0x30, 6
        try:
            answer = ctypes.windll.user32.MessageBoxW(
                None, strings.t("dlg_no_engine"),
                "Master Audio Switcher", MB_YESNO | MB_ICONWARNING)
            if answer == IDYES:
                import webbrowser
                webbrowser.open(runtime.DOWNLOAD_URL)
        finally:
            self._engine_asking = False

    def show(self, tab: str = "devices") -> None:
        """Python does not call JavaScript. The tab we need goes into the
        snapshot, and the interface picks it up on the next poll. Calling
        evaluate_js from a background thread into a hidden window used to hang
        the whole program dead."""
        if not self.window:
            # Silence here would look like a broken program: the person clicked
            # and nothing happened. If there is no window because the engine is
            # missing, say so every time they ask — they asked, after all.
            if self._engine is None:
                self._offer_engine(modal=True)
            return
        # The mixer and the settings have nowhere to go in mini view — leave it.
        if tab != "devices" and self._mini:
            self.set_mini(False)
        with self._ui_lock:
            self._pending_tab = tab
            self._state_rev += 1
        try:
            self.window.show()
            self._visible = True
            self.meter.set_idle(False)
            hwnd = self.own_hwnd()
            if hwnd:
                screen.place_at_tray(hwnd)   # the corner where the tray is
                screen.to_front(hwnd)        # and in front of what is already open
            self.refresh_title()
            _log.info("window shown, tab %s", tab)
        except Exception:
            _log.exception("the window did not show up")

    def take_ui_signal(self) -> dict:
        with self._ui_lock:
            tab, self._pending_tab = self._pending_tab, None
            return {"tab": tab, "rev": self._state_rev, "mini": self._mini,
                    "hidden": not self._visible, "now": self.players.snapshot()}

    def hide(self) -> None:
        if not self.window:
            return
        try:
            self.window.hide()
        except Exception:
            _log.warning("the window did not hide", exc_info=True)
            return
        # The order matters: hide first, then put everything into sleep mode.
        self._visible = False
        self.meter.set_idle(True)
        if self._title != WINDOW_TITLE:
            # Back to the program's own name. A hidden window has no taskbar
            # button to read a track from, and Alt+Tab would still be offering
            # a song title with nothing behind it.
            try:
                self.window.set_title(WINDOW_TITLE)
                self._title = WINDOW_TITLE
            except Exception:
                _log.warning("the window title did not go back", exc_info=True)
        if self._wiz is not None:
            # The wizard lives in the window. Closing it mid-way would otherwise
            # leave the dongle held open by a listener nobody can reach again.
            self.wizard_stop()
            self.sync_dongle()
        with self._ui_lock:
            self._state_rev += 1      # so the page learns of it on the next poll

    def _shutdown_com(self) -> None:
        """Let COM go before the window unloads the .NET runtime.

        Otherwise the garbage collector calls Release in an already destroyed
        environment, and the process crashes with a memory access violation —
        caught by the crash trap.
        """
        self.hotkeys.stop()
        self.players.stop()
        self.meter.stop()
        self.meter.join(timeout=1.5)
        devices.invalidate()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        _log.info("exit on request")
        self._stopped.set()          # releases run() when there is no window
        self._shutdown_com()
        if self.tray:
            self.tray.stop()
        self.bridge.stop()
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass

    # --- startup ---------------------------------------------------------
    def run(self) -> int:
        # The window module is loaded here and not at the top of the file: it
        # drags .NET along with it and costs about 90 ms, and until the tray
        # icon appears it is not needed at all.
        import webview

        # Asked before anything is drawn. Without the runtime pywebview does not
        # fail — it silently falls back to the Internet Explorer engine, and our
        # page renders there as an empty rectangle. A black window with a title
        # bar and no explanation is worse than no window at all.
        self._engine = runtime.webview2_version()
        _log.info("window engine: %s", self._engine or "MISSING")

        # Only now, after the window module has declared this process DPI aware,
        # does the screen report its real size. A window taller than the screen
        # cannot be scrolled or resized — it is simply cut off at the bottom.
        self._full_height = screen.fit_height(FULL_SIZE[1])
        if self._full_height != FULL_SIZE[1]:
            _log.info("the screen is short: window height %s instead of %s",
                      self._full_height, FULL_SIZE[1])

        url = self.bridge.start()
        self.meter.start()
        self.hotkeys.start()
        self.players.start()
        threading.Thread(target=self._job_loop, daemon=True, name="mas-auto").start()

        # The buttons are read on every click instead of being remembered at
        # startup: the setting gets changed on the fly, and restarting the
        # program for that would be silly.
        self.tray = Tray(
            on_left=lambda: self._button("left"),
            on_right=lambda: self._button("right"),
            on_middle=lambda: self.show("mixer"),
            on_quit=self.quit,
        )
        self.overlay.start()
        threading.Thread(target=self.tray.run, daemon=True, name="mas-tray").start()
        threading.Thread(target=self._boot_watchdog, daemon=True, name="mas-boot").start()

        # Our own title bar instead of the native frame. easy_drag is off: with
        # it the window is dragged by any point of the page, and the sliders and
        # the knob stop working. The drag zone is set in the markup by the
        # pywebview-drag-region class.
        if self._engine is not None:
            self.window = webview.create_window(
                WINDOW_TITLE, url, width=FULL_SIZE[0], height=self._full_height,
                resizable=False, frameless=True, easy_drag=False, hidden=True,
                background_color="#1C1F24",
            )
        try:
            if self.window is None:
                # No engine, so no window — but the program is not useless: its
                # main job is a click on the tray icon, and that needs nothing
                # from a browser. We keep the tray alive and wait for the exit.
                # A manual start is told by show() further down, which is where
                # the request for a window actually arrives; from autostart
                # nobody asked for anything, so a notification is enough.
                if self.launched_by_startup:
                    self._offer_engine()
                self._stopped.wait()
                _log.info("exit without a window")
            else:
                webview.start()
                # We get here both when the window was closed and when the
                # WebView2 engine crashed. Telling them apart matters: in the
                # second case the program is obliged to say so.
                _log.info("window loop finished (exit requested: %s)", self._quitting)
        finally:
            self._shutdown_com()
            self.bridge.stop()
            _log.info("=== exit ===")
            log.note_clean_exit()
            logging.shutdown()
            # We cut the process off without letting the interpreter shut down.
            # On exit the WebView2 window unloads the .NET runtime, that runtime
            # starts garbage collection, and it releases the remaining COM
            # objects in an already collapsing environment — the process crashes
            # with a memory access violation five times out of five. There is
            # nothing to clean up: the settings are written immediately, and the
            # memory is given back by the system.
            os._exit(0)
        return 0

    def _boot_watchdog(self) -> None:
        # Devices are enumerated here and not in the main thread: the main one
        # is the only one with the single-threaded COM model, and the COM objects
        # created there are later released by the garbage collector from another
        # thread, and the process crashes.
        self.switcher.seed_if_empty()
        # The icon first, before anything is waited for. It is what puts the
        # program in the tray at all, and the wait below is about the window.
        self.refresh_tray()
        # We wait not "two seconds just in case" but for exactly what we are
        # waiting for: the first binding of the meter to a device. The window
        # used to appear 2.5 s after a manual start only because of that pause.
        if not self.meter.ready.wait(timeout=2.0):
            _log.info("the meter did not bind within 2 s — showing the window as is")
        self.sync_auto_device()
        # A manual start is obliged to show the window: Windows hides a new icon
        # in the tray overflow, and the person decides the program did not
        # start. A start from autostart goes to the tray silently, otherwise the
        # window pops up every time the computer is turned on.
        if self.launched_by_startup:
            # The window was never opened — put the meter into the sleepy rhythm
            # right away, otherwise it spins at full rate until the window is
            # first shown, that is, possibly for the whole session.
            self.meter.set_idle(True)
            _log.info("started from autostart — not showing the window")
        else:
            _log.info("manual start — showing the window")
            self.show("devices")
        dev = self.current_device()
        _log.info("SELFCHECK RESULT: bridge=%s, tray=%s, device=%s",
                  "alive" if self.api.selfcheck_seen else "SILENT",
                  "there" if self.tray else "missing",
                  dev.name if dev else "unknown")


def set_app_id() -> None:
    """Without an app id of its own Windows signs notifications with the process
    name — when started from source, "Python" shows up in the title."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MasterAudioSwitcher.App")
    except Exception:
        _log.warning("the application id was not set", exc_info=True)


def main() -> int:
    # Cyclic garbage collection is disabled on purpose, and this is not an
    # optimization. COM objects live in different threads, while the collector
    # fires in whichever thread got unlucky and releases someone else's object
    # outside its environment — the process crashes with a memory access
    # violation. Caught by the trap on the path back from the headset. Reference
    # counting releases everything by itself, in the right thread. The price is
    # measured: 8 KB for a full device enumeration, and those same kilobytes are
    # not given back by a manual collection either — that is, there is no price
    # at all.
    gc.disable()
    log.setup()
    # Before anything measures the screen. pywebview calls exactly this when it
    # starts the window (platforms/winforms.py), and until then Windows lies to
    # us about sizes: the tray asks for a 16-pixel icon on a 125% display, we
    # draw one, and a second later the truth arrives and the icon is redrawn at
    # 20, blurred in between. Calling it first costs nothing — the second call
    # from inside pywebview simply finds it already done.
    ctypes.windll.user32.SetProcessDPIAware()
    set_app_id()
    # Which of the two builds this is decides who updates it, and it is the
    # first thing worth knowing when reading somebody else's log.
    _log.info("=== start, frozen=%s, from=%s ===", is_frozen(),
              "the Microsoft Store" if update.from_store() else "the releases page")
    if already_running():
        _log.warning("an instance is already running, exiting")
        return 0
    return App().run()


if __name__ == "__main__":
    sys.exit(main())
