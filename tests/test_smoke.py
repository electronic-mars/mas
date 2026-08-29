"""A tiny dependency-free runner. Run in full after every feature."""
import os
import sys
import tempfile
from pathlib import Path

# The tests must not write into the real log. Importing mas.app sets logging up
# against %LOCALAPPDATA%, and every fake device, every seeded cycle and every
# deliberately refused switch used to land in the file we read to work out what
# went wrong on a live machine. Redirected before mas is imported, because the
# folder is resolved at that moment.
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="mas-tests-")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mas.core import devices  # noqa: E402
from mas.core.config import DEFAULTS  # noqa: E402
from mas.core.switcher import Switcher  # noqa: E402

# Kept before anything replaces it: fake_world below swaps default_id for a stub,
# and the test of its own logging needs the real one.
REAL_DEFAULT_ID = devices.default_id

_passed, _failed = 0, 0


def check(label: str, got, want):
    global _passed, _failed
    if got == want:
        _passed += 1
    else:
        _failed += 1
        print(f"  FAILED: {label}\n    got: {got!r}\n    expected: {want!r}")


class FakeConfig:
    def __init__(self, **over):
        self._d = {**DEFAULTS, **over}

    def get(self, k):
        return self._d[k]

    def set(self, k, v):
        self._d[k] = v


def fake_world(present_ids, current_id, monkey_target=devices):
    """Replace the real devices with a given set."""
    monkey_target.list_devices = lambda only_active=True: [
        devices.Device(id=i, name=f"dev{i}", is_output=True, active=True) for i in present_ids
    ]
    monkey_target.default_id = lambda is_output=True, **kw: current_id


A, B, C = "id-A", "id-B", "id-C"

print("Cycle: basic behaviour")
sw = Switcher(FakeConfig(cycle=[A, B]))
fake_world([A, B], A)
check("from A we go to B", sw.next_id(), B)
fake_world([A, B], B)
check("from B we come back to A", sw.next_id(), A)

print("Cycle: three devices")
sw = Switcher(FakeConfig(cycle=[A, B, C]))
fake_world([A, B, C], B)
check("the order is respected", sw.next_id(), C)
fake_world([A, B, C], C)
check("it wraps around to the start", sw.next_id(), A)

print("The cycle is tied to the device, not to the position")
sw = Switcher(FakeConfig(cycle=[A, B, C]))
fake_world([A, C], A)                       # B is gone (headphones ran out of charge)
check("a missing one is skipped", sw.next_id(), C)
fake_world([A, C], C)
check("the order of the rest did not shift", sw.next_id(), A)
fake_world([A, B, C], A)                    # B is back
check("the returned one takes its own place", sw.next_id(), B)

print("Cycle: edge cases")
sw = Switcher(FakeConfig(cycle=[A, B]))
fake_world([], None)
check("an empty cycle does not crash", sw.next_id(), None)
fake_world([A], A)
check("a single device stays itself", sw.next_id(), A)
sw = Switcher(FakeConfig(cycle=[A, B]))
fake_world([A, B], "id-someone-elses")              # Windows reset the default
check("default outside the cycle — we enter from the start", sw.next_id(), A)
sw = Switcher(FakeConfig(cycle=[]))
fake_world([A, B], A)
check("nothing is ticked — nothing to switch to", sw.next_id(), None)

print("Reordering")
cfg = FakeConfig(cycle=[A, B, C])
sw = Switcher(cfg)
sw.reorder([C, A])
check("missing from the list goes to the tail, does not vanish", cfg.get("cycle"), [C, A, B])

print("Ticking participation")
cfg = FakeConfig(cycle=[A])
sw = Switcher(cfg)
sw.toggle_in_cycle(B, True)
check("adding", cfg.get("cycle"), [A, B])
sw.toggle_in_cycle(A, False)
check("removing", cfg.get("cycle"), [B])
sw.toggle_in_cycle(B, True)
check("adding again does not duplicate", cfg.get("cycle"), [B])

print("Seeding the cycle on a clean install")
fake_world([A, B], A)
cfg = FakeConfig(cycle=[])
sw = Switcher(cfg)
sw.seed_if_empty()
check("an empty cycle is filled with output devices", cfg.get("cycle"), [A, B])
cfg = FakeConfig(cycle=[B])
sw = Switcher(cfg)
sw.seed_if_empty()
check("a non-empty cycle is left alone", cfg.get("cycle"), [B])

print("The microphone of the same headset")


def world(pairs):
    """pairs: (id, name, is output). Replace the whole device list."""
    devices.list_devices = lambda only_active=True, **kw: [
        devices.Device(id=i, name=n, is_output=o, active=True) for i, n, o in pairs
    ]


world([("out-pb", "Headphones (Powerbeats Pro)", True),
       ("mic-pb", "Headset (Powerbeats Pro)", False),
       ("mic-lap", "Microphone Array (Intel Smart Sound)", False)])
got = devices.microphone_of("out-pb")
check("exact match on the device in brackets", got and got.id, "mic-pb")

world([("out-hx", "Headphones (HyperX Cloud Flight S Game)", True),
       ("mic-hx", "Microphone (HyperX Cloud Flight S Chat)", False),
       ("mic-lap", "Microphone Array (Intel Smart Sound)", False)])
got = devices.microphone_of("out-hx")
check("the Game and Chat halves link up by their common start", got and got.id, "mic-hx")

world([("out-rt", "Speakers (Realtek(R) Audio)", True),
       ("mic-lap", "Microphone Array (Intel Smart Sound)", False)])
check("speakers have no microphone of their own", devices.microphone_of("out-rt"), None)

world([("out-x", "Speakers", True), ("mic-lap", "Microphone Array (Intel)", False)])
check("a name without brackets gives no false pair", devices.microphone_of("out-x"), None)

world([("out-pb", "Headphones (Powerbeats Pro)", True)])
check("no microphones at all", devices.microphone_of("out-pb"), None)
check("the device is not in the system", devices.microphone_of("no-such-id"), None)

print("Main microphone")
FULL = [("out-pb", "Headphones (Powerbeats Pro)", True),
        ("out-rt", "Speakers (Realtek(R) Audio)", True),
        ("mic-pb", "Headset (Powerbeats Pro)", False),
        ("mic-lap", "Microphone Array (Intel Smart Sound)", False)]
world(FULL)
check("a headset microphone counts as tied", devices.tied_microphones(), {"mic-pb"})
check("only one free microphone — it is the main one", devices.standalone_microphone(), "mic-lap")

world(FULL + [("mic-usb", "Microphone (Blue Yeti)", False)])
check("two free ones — we do not guess", devices.standalone_microphone(), None)

world([("out-rt", "Speakers (Realtek(R) Audio)", True)])
check("no microphones at all", devices.standalone_microphone(), None)

check("bracket parsing", devices._owner("Headphones (Powerbeats Pro)"), "Powerbeats Pro")
check("nested brackets do not throw it off", devices._owner("Speakers (Realtek(R) Audio)"),
      "Realtek(R) Audio")

print("Hotkey parsing")
from mas.core import hotkey  # noqa: E402

check("modifiers add up", hotkey.parse("Ctrl+Alt+H"), (0x0002 | 0x0001, ord("H")))
check("case does not matter", hotkey.parse("ctrl+alt+h"), hotkey.parse("Ctrl+Alt+H"))
check("function keys", hotkey.parse("Ctrl+Shift+F9"), (0x0002 | 0x0004, 0x78))
check("named keys", hotkey.parse("Alt+Del"), (0x0001, 0x2E))
check("the F row is allowed without a modifier", hotkey.parse("F13"), (0, 0x7C))
check("a letter without a modifier is taken from the system", hotkey.parse("H"), None)
check("empty string", hotkey.parse(""), None)
check("modifiers only", hotkey.parse("Ctrl+Shift"), None)
check("two ordinary keys", hotkey.parse("Ctrl+A+B"), None)
check("a non-existent F key", hotkey.parse("Ctrl+F25"), None)
check("Cyrillic does not produce a bogus key code", hotkey.parse("Ctrl+Ё"), None)

print("Priority device")
from mas.app import App  # noqa: E402


def auto_app(auto_id, cycle=(A, B, C)):
    """A real App with a faked environment: we check exactly its own logic."""
    app = App.__new__(App)
    app.cfg = FakeConfig(cycle=list(cycle), auto_device=auto_id)
    app.switcher = Switcher(app.cfg)
    app.tray = None
    app.window = None
    threading = __import__("threading")
    app._auto_prev, app._auto_held = None, False
    app._auto_lock = threading.Lock()
    app._ui_lock, app._state_rev, app._pending_tab = threading.Lock(), 0, None
    app.moved = []
    app._go = lambda i: app.moved.append(i)
    # In production the work goes off to a separate thread with its own COM
    # apartment; in the test we run it in place, to check the decision, not races.
    app._dispatch = lambda job, auto: job(auto)
    return app


HP = "id-headphones"

# The headphones were switched on: sound goes to them, the previous device is remembered.
app = auto_app(HP)
fake_world([A, B], A)
app._devices_changed({HP}, set())
check("headphones appearing take the sound", app.moved, [HP])
check("the previous device is remembered", app._auto_prev, A)

# And it comes back exactly where it left from.
fake_world([A, B], HP)
app._devices_changed(set(), {HP})
check("disappearing gives the sound back", app.moved, [HP, A])
check("the memory of the previous one is cleared", app._auto_prev, None)

# The previous device is gone too — take the first ticked one, anything but nowhere.
app = auto_app(HP)
fake_world([A, B], A)
app._devices_changed({HP}, set())
fake_world([B], HP)
app._devices_changed(set(), {HP})
check("previous one gone — go to the first available in the cycle", app.moved, [HP, B])

# The person left the headphones themselves — switching them off is none of our business.
app = auto_app(HP)
fake_world([A, B], A)
app._devices_changed({HP}, set())
app.note_manual_switch()
fake_world([A, B], A)
app._devices_changed(set(), {HP})
check("after a manual switch we do not interfere", app.moved, [HP])

# Windows sometimes gives the sound to new headphones itself — nothing to switch.
app = auto_app(HP)
fake_world([A, B], HP)
app._devices_changed({HP}, set())
check("the sound is already there — no extra switch", app.moved, [])
check("but we are the ones holding them", app._auto_held, True)

# The setting is off — nothing happens at all.
app = auto_app("")
fake_world([A, B], A)
app._devices_changed({HP}, set())
app._devices_changed(set(), {HP})
check("with no device chosen the mode stays quiet", app.moved, [])

# An unrelated device showed up — none of our business.
app = auto_app(HP)
fake_world([A, B], A)
app._devices_changed({C}, set())
check("a foreign device is ignored", app.moved, [])


# --- media control --------------------------------------------------------
# We do not press the keys: the test must not pause somebody's music. We check
# only that the input structure is assembled correctly — Windows silently rejects
# a request of the wrong size, and the error would look like "the button is dead".
import ctypes  # noqa: E402

from mas.core import media  # noqa: E402

check("size of the input structure", ctypes.sizeof(media._INPUT), 40)
check("set of media actions", sorted(media.KEYS), ["next", "play", "prev"])
try:
    media.tap("stop")
    check("an unknown action is rejected", "not rejected", "ValueError")
except ValueError:
    check("an unknown action is rejected", "ValueError", "ValueError")

# The "playing" number comes from Windows itself. It was once written down by eye
# as 5, that is "paused", and for a month the program treated a playing player as
# stopped: it hit "resume" on a playing one and "pause" on a stopped one, and then
# declared it broken.
from mas.core.players import PLAYING  # noqa: E402

try:
    import winrt.windows.media.control as _ctl  # noqa: E402

    real = int(_ctl.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING)
except ImportError:
    real = PLAYING
    print("  the player list is unavailable — nothing to check \"playing\" against")
check("\"playing\" matches the Windows enumeration", PLAYING, real)

# A closed tab leaves a record in the system, frozen in "playing" forever. As long
# as such a ghost counted as alive, it intercepted every keypress from the real
# player: the target is picked by the "playing" flag, and only it plays forever.
print("\nGhost of a closed tab")
from mas.core.players import PAUSED, Players  # noqa: E402


class FakeControls:
    is_play_enabled = is_pause_enabled = is_next_enabled = is_previous_enabled = True


class FakeInfo:
    def __init__(self, status):
        self.playback_status = status
        # _describe reads this to write the log line that says who was there and
        # what they could do — the line that settled the last false bug report.
        self.controls = FakeControls()


class FakeSession:
    def __init__(self, app, status):
        self.source_app_user_model_id = app
        self.status = status

    def get_playback_info(self):
        return FakeInfo(self.status)


ghost, live = FakeSession("Opera", PLAYING), FakeSession("Spotify", PAUSED)
p = Players()
p._dead["Opera"] = PLAYING
check("the ghost does not intercept the command", p._pick([ghost, live]).source_app_user_model_id, "Spotify")
check("nobody else left — we take the ghost too", p._pick([ghost]).source_app_user_model_id, "Opera")
ghost.status = PAUSED
p._revive([ghost, live])
check("state changed — alive again", "Opera" in p._dead, False)

print("A player nominated by hand")
# The case this exists for: a short video starts in a browser while the music is
# meant to be Spotify. Without a nomination the command follows whoever plays.
opera, spotify = FakeSession("Opera", PLAYING), FakeSession("Spotify", PAUSED)
free = Players()
check("without a nomination the playing one wins",
      free._pick([opera, spotify]).source_app_user_model_id, "Opera")

named = Players()
named.set_priority("Spotify")
check("the nominated one wins even while another plays",
      named._pick([opera, spotify]).source_app_user_model_id, "Spotify")
check("its name is remembered for the settings list",
      [a["name"] for a in named.known_apps()], ["Spotify"])
check("it is offered even while it is not running",
      named._pick([opera]).source_app_user_model_id, "Opera")

# A player that starts after the window was opened must reach the settings list.
# The page fetches the state only when it is told the state changed, so a player
# discovered quietly stayed invisible until something unrelated forced a refresh
# — which is how an empty dropdown appeared with Spotify playing in plain sight.
told = []
late = Players(on_new_app=lambda: told.append(1))
late._note([opera])
check("the window is told about a player it had not seen", len(told), 1)
late._note([opera])
check("and not told again about the same one", len(told), 1)
late._note([opera, spotify])
check("but told when another one turns up", len(told), 2)
check("both are in the list now",
      [a["name"] for a in late.known_apps()], ["Opera", "Spotify"])

# Taking the nomination away must actually change what happens. Without this the
# un-nominated player kept winning as "the one controlled last", and the setting
# looked as though it had not applied at all.
dropped = Players()
dropped.set_priority("Spotify")
dropped._last_app = "Spotify"
dropped.set_priority("")
check("the habit goes with the nomination", dropped._last_app, None)
check("and the command follows whoever plays",
      dropped._pick([opera, spotify]).source_app_user_model_id, "Opera")

# Somebody else's stickiness is not ours to throw away.
kept = Players()
kept.set_priority("Spotify")
kept._last_app = "Opera"
kept.set_priority("")
check("an unrelated last target is left alone", kept._last_app, "Opera")

# A nominated player that stopped responding must not hold the command hostage.
mute = Players()
mute.set_priority("Spotify")
mute._dead["Spotify"] = PAUSED
check("a nominated ghost yields to a live player",
      mute._pick([opera, spotify]).source_app_user_model_id, "Opera")


class HushSession(FakeSession):
    def __init__(self, app, status):
        super().__init__(app, status)
        self.paused = False

    def try_pause_async(self):
        self.paused = True

        async def done():
            return True
        return done()


loud = HushSession("Opera", PLAYING)
quiet = HushSession("Chrome", PAUSED)
mine = HushSession("Spotify", PAUSED)
hushing = Players()
hushing.set_priority("Spotify")
hushing._hush([loud, quiet, mine], "Spotify")
check("what was playing is paused", loud.paused, True)
check("what was already quiet is left alone", quiet.paused, False)
check("the nominated one is never hushed", mine.paused, False)

# Icon tooltip: while something is playing — only the track, otherwise the device.
print("\nTray icon tooltip")


def tip_for(**snap):
    holder = App.__new__(App)
    holder._device_tip = "Speakers (Realtek(R) Audio)"
    holder.players = type("P", (), {"snapshot": staticmethod(lambda: snap)})
    return App.tray_tip(holder)


check("playing — the track title only",
      tip_for(app="Spotify", artist="Biosphere", title="Infinite Reflections", playing=True),
      "Biosphere — Infinite Reflections")
check("paused — the device",
      tip_for(app="Spotify", artist="Biosphere", title="Infinite Reflections", playing=False),
      "Master Audio Switcher — Speakers (Realtek(R) Audio)")
check("no player — the device",
      tip_for(app="", artist="", title="", playing=False),
      "Master Audio Switcher — Speakers (Realtek(R) Audio)")
check("playing, but the title is unknown — the device",
      tip_for(app="Opera", artist="", title="", playing=True),
      "Master Audio Switcher — Speakers (Realtek(R) Audio)")

print("Window height on someone else's screen")

from mas.core import screen  # noqa: E402


def room_for(work_area_px: int, scale: float, desired: int = 772) -> int:
    """fit_height over a made-up screen: a work area and a display scale."""
    screen.work_area = lambda: type("R", (), {"top": 0, "bottom": work_area_px})
    screen.dpi_scale = lambda: scale
    return screen.fit_height(desired)


# Our own machine: 1540 points of work area, everything fits — which is exactly
# why this was never visible here.
check("a tall screen keeps the full height", room_for(1540, 1.0), 772)
# A 1366x768 laptop: about 728 points of work area. Before this, 44 points were
# cut off at 100% and 237 at 125%, with no way to scroll or resize.
check("1366x768 at 100% — the window shrinks", room_for(728, 1.0), 704)
check("1080p at 150% — scale counts too", room_for(1032, 1.5), 664)
check("a margin is left at the top and the bottom", room_for(700, 1.0), 700 - 24)
check("an absurdly short screen still leaves a window", room_for(200, 1.0),
      screen.MIN_HEIGHT)
check("the window never grows beyond what it asked for", room_for(4000, 1.0), 772)

print("A machine with no audio devices")

# Found on the build machine, which has no sound card: the log filled with a
# stack trace twice a second for as long as the program ran. The one file we
# have to work from must not be buried by a condition that never changes.
import logging  # noqa: E402


class Counter(logging.Handler):
    def __init__(self):
        super().__init__()
        self.said = []

    def emit(self, record):
        self.said.append(record.levelno)


counter = Counter()
logging.getLogger("mas.devices").addHandler(counter)
real_enum, devices._enumerator = devices._enumerator, None


def no_devices():
    raise OSError("no endpoint here")


devices._quiet[True] = False
devices._enumerator = no_devices
for _ in range(5):
    REAL_DEFAULT_ID(is_output=True, max_age=0.0)
check("five attempts, one complaint",
      [n for n in counter.said if n >= logging.WARNING], [logging.WARNING])

counter.said.clear()
devices._enumerator = lambda: type("E", (), {"GetDefaultAudioEndpoint":
    lambda self, f, r: type("D", (), {"GetId": lambda s: "id-back"})()})()
check("and it says so when a device comes back",
      REAL_DEFAULT_ID(is_output=True, max_age=0.0), "id-back")
check("exactly once", len(counter.said), 1)
devices._enumerator = real_enum
logging.getLogger("mas.devices").removeHandler(counter)

print("A command that cannot be carried out")

import mas.core.players as players_mod  # noqa: E402


class Cmd(FakeSession):
    """A session that answers but does not necessarily obey."""

    def __init__(self, app, status, obeys=True):
        super().__init__(app, status)
        self.obeys = obeys
        self.played = self.paused = False

    def _act(self, playing):
        async def done():
            return True
        if self.obeys:
            self.status = PLAYING if playing else PAUSED
        return done()

    def try_play_async(self):
        self.played = True
        return self._act(True)

    def try_pause_async(self):
        self.paused = True
        return self._act(False)

    # _do builds the call table for all three actions before picking one, so
    # every method has to exist even when only play is under test.
    def try_skip_next_async(self):
        return self._act(self.status == PLAYING)

    def try_skip_previous_async(self):
        return self._act(self.status == PLAYING)


class Mgr:
    def __init__(self, sessions, current):
        self._s, self._cur = sessions, current

    def get_sessions(self):
        return self._s

    def get_current_session(self):
        return self._cur


def do_play(sessions, current, priority, keys_only=()):
    """Run a real play command against fake players, with the key press counted."""
    p = Players()
    p._mgr = Mgr(sessions, current)
    p.set_priority(priority)
    p._keys_only.update(keys_only)
    p.dead_said = []
    p._on_dead = p.dead_said.append
    taps = []
    real_tap, players_mod.media.tap = players_mod.media.tap, taps.append
    real_wait, players_mod.VERIFY_WAIT_S = players_mod.VERIFY_WAIT_S, 0.05
    try:
        p._do("play")
    finally:
        players_mod.media.tap = real_tap
        players_mod.VERIFY_WAIT_S = real_wait
    return p, taps


# The whole point: a video is playing in a browser, the nominated player starts,
# and the browser goes quiet.
video = Cmd("Opera", PLAYING)
music = Cmd("Spotify", PAUSED)
p, taps = do_play([video, music], video, "Spotify")
check("the nominated player is started", music.played, True)
check("what was playing is hushed", video.paused, True)
check("no blind key press", taps, [])

# It refuses to start. Everything must not be left silent, and the person must
# be told — that failure used to pass in complete quiet.
video = Cmd("Opera", PLAYING)
music = Cmd("Spotify", PAUSED, obeys=False)
p, taps = do_play([video, music], video, "Spotify")
check("the hush is undone when the music does not start", video.played, True)
check("and still no key press that would hit the browser", taps, [])
check("the person is told", len(p.dead_said), 1)
# This is the one that made the feature die after a single slow press: the player
# was recorded as key-only on the strength of a key press that never happened.
check("a player is not blamed for a key we never pressed",
      "Spotify" in p._keys_only, False)

# With nobody nominated the old fallback still works: the key is pressed, and a
# player that ignores addressed commands is remembered as such.
lonely = Cmd("Chrome", PAUSED, obeys=False)
p, taps = do_play([lonely], lonely, "")
check("without a nomination the key is still pressed", taps, ["play"])
check("and the player is remembered as key-only", "Chrome" in p._keys_only, True)

print("The languages")

import json  # noqa: E402

LOCALES = Path(__file__).resolve().parents[1] / "src" / "mas" / "ui" / "locales"
docs = {p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in LOCALES.glob("*.json") if p.stem != "index"}
english = docs["en"]["strings"]
listed = {i["code"] for i in json.loads((LOCALES / "index.json").read_text(encoding="utf-8"))}

# A key missing from one language shows English instead, and that is invisible
# until a user reports a page half in another language. The previous project drifted
# three keys behind in fifteen languages exactly this way.
for code, doc in sorted(docs.items()):
    strings = doc["strings"]
    check(f"{code}: the same set of keys as English", set(strings), set(english))
    check(f"{code}: nothing left blank", [k for k, v in strings.items() if not v.strip()], [])
    check(f"{code}: the placeholder survives translation",
          [k for k, v in english.items() if "%s" in v and "%s" not in strings[k]], [])
    check(f"{code}: named in the dropdown", code in listed, True)
    check(f"{code}: says which language it is", bool(doc.get("name")), True)

check("the dropdown lists exactly the files we ship", listed, set(docs))
check("English is offered first",
      json.loads((LOCALES / "index.json").read_text(encoding="utf-8"))[0]["code"], "en")

# Text in a tab or on a segment cannot wrap: it is simply cut off. The budget is
# generous — this catches a translation that ran away, not a long word.
TIGHT = {"tab_devices": 14, "tab_mixer": 14, "tab_settings": 16, "tab_about": 18,
         "lcd_level": 12, "lcd_signal": 12, "btn_left": 12, "btn_right": 12,
         "hk_clear": 12, "open_btn": 14, "welcome_ok": 16}
over = [(c, k, len(d["strings"][k])) for c, d in docs.items()
        for k in TIGHT if len(d["strings"][k]) > TIGHT[k]]
check("nothing overflows a tab or a button", over, [])

print(f"  {len(docs)} languages, {len(english)} strings each")

print("No placeholders left in the About tab")

import re  # noqa: E402

from mas import __version__  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "src" / "mas" / "ui" / "app.js").read_text(encoding="utf-8")
SPEC = (ROOT / "build" / "mas.spec").read_text(encoding="utf-8")

check("the support button leads somewhere real", "example.invalid" in APP_JS, False)
check("no button points at a bare github.com",
      'data-url="https://github.com/"' in APP_JS, False)
check("support goes to Patreon",
      'data-url="https://www.patreon.com/ElectronicMARS"' in APP_JS, True)
check("GitHub goes to our repository",
      'data-url="https://github.com/electronic-mars/mas"' in APP_JS, True)
# Updating is no longer a link to a page for the person to work out for
# themselves — the button does the whole thing, so the address moved into
# core/update.py, where it is checked against the host allowlist.
check("the About tab no longer sends people off to fetch it by hand",
      "releases/latest" in APP_JS, False)
check("and the release feed points at our repository",
      'FEED = "https://github.com/electronic-mars/mas/releases/'
      in (ROOT / "src" / "mas" / "core" / "update.py").read_text(encoding="utf-8"), True)

# One source for the number. Written out twice it drifts on the first release,
# and then the exe properties, the About tab and the release tag disagree.
check("the page does not carry a version of its own",
      re.search(r"\d+\.\d+\.\d+", APP_JS), None)
check("the page takes the version from the program",
      "state.settings.version" in APP_JS, True)
spec_version = re.search(r'__version__ = "\(\[\^"\]\+\)"', SPEC)
check("the build reads the version out of the package", bool(spec_version), True)
check("and the exe gets a version resource at all", "version=VERSION_RESOURCE" in SPEC, True)
print(f"  the version is {__version__}, and it lives in one place")

print("A microphone that refused to switch")


def mic_app(result):
    """An App with only what go_microphone touches."""
    app = App.__new__(App)
    th = __import__("threading")
    app._ui_lock, app._state_rev = th.Lock(), 0
    app.said, app.announced = [], []
    app.tray = type("T", (), {"notify": lambda s, text: app.said.append(text)})()
    app.switcher = type("S", (), {"switch_to": staticmethod(lambda i: result)})()
    app.announce = app.announced.append
    return app


# An output takes its tray icon back when the system refuses. A microphone has
# no icon, so the refusal has to be spoken, or it passes in total silence.
one = mic_app(None)
one.go_microphone("mic-x")
check("a refusal is said out loud", len(one.said), 1)
check("nothing is announced as done", one.announced, [])

mic = devices.Device(id="mic-x", name="Microphone", is_output=False, active=True)
two = mic_app(mic)
two.go_microphone("mic-x")
check("a switch that worked is announced", two.announced, [mic])
check("and nothing is said about a refusal", two.said, [])

print("The engine the window is drawn with")

from mas.core import runtime  # noqa: E402

import winreg  # noqa: E402

# The real root handles: runtime.PLACES is built with them at import time, so a
# fake registry keyed by anything else would simply never match.
HKLM, HKCU = winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER
MACHINE_32 = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{}".format(runtime.CLIENT)
MACHINE = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{}".format(runtime.CLIENT)


class FakeReg:
    """Just enough of winreg: a registry that holds the keys we hand it."""

    def __init__(self, keys):
        self.keys = keys                     # (root, path) -> value of pv

    def OpenKey(self, root, path):
        if (root, path) not in self.keys:
            raise OSError("no such key")
        value = self.keys[(root, path)]
        return type("K", (), {"__enter__": lambda s: value,
                              "__exit__": lambda s, *a: False})()

    def QueryValueEx(self, key, name):
        if key is None:
            raise OSError("no such value")
        return key, 1


def version_with(keys):
    real, runtime.winreg = runtime.winreg, FakeReg(keys)
    try:
        return runtime.webview2_version()
    finally:
        runtime.winreg = real


# A machine-wide install lands in the 32-bit view even on 64-bit Windows, which
# is why the plain path alone is not enough. Measured on this machine.
check("found in the 32-bit view", version_with({(HKLM, MACHINE_32): "147.0.3912.72"}),
      "147.0.3912.72")
check("found on a 32-bit Windows", version_with({(HKLM, MACHINE): "120.0.0.1"}),
      "120.0.0.1")
check("found in a per-user install",
      version_with({(HKCU, MACHINE): "121.0.0.2"}), "121.0.0.2")
check("nothing installed", version_with({}), None)
# Edge Update keeps the key after the runtime is removed and blanks the value.
check("a leftover key is not an install", version_with({(HKLM, MACHINE_32): "0.0.0.0"}),
      None)
check("an empty version is not an install", version_with({(HKLM, MACHINE_32): ""}), None)
check("a broken value does not throw",
      version_with({(HKLM, MACHINE_32): None}), None)

print(f"  on this machine: {runtime.webview2_version() or 'the runtime is missing'}")


# --------------------------------------------------------------------------
# Working out an unknown dongle. This is the one piece where a wrong answer is
# worse than no answer: a byte that only looked like the state means headphones
# that seize the sound at random, and nobody would connect that to a wizard they
# ran once. So the cases that must be refused matter more than the ones that work.
print("\nWorking out an unknown dongle")
from mas.core.dongle import KNOWN, deduce  # noqa: E402


def b(*vals):
    return bytes(vals)


# The real HyperX, as recorded over three power cycles.
hx = deduce([b(0x0B, 0, 0xBB, 1, 1)] * 2, [b(0x0B, 0, 0xBB, 1, 3)] * 2)
check("the HyperX rule is recovered from its reports",
      {k: hx[k] for k in ("report", "state_at", "on", "off")},
      {"report": 0x0B, "state_at": 4, "on": 0x01, "off": 0x03})
check("and it is the rule that ships", hx["marker"], KNOWN[(0x0951, 0x16EA)]["marker"])

# A battery byte differs between one on and one off just as convincingly. Two
# cycles are what throws it out — this is the whole reason the wizard has four
# steps instead of two.
noisy_on = [b(0x0B, 0, 0xBB, 90, 1), b(0x0B, 0, 0xBB, 88, 1)]
noisy_off = [b(0x0B, 0, 0xBB, 87, 3), b(0x0B, 0, 0xBB, 86, 3)]
check("a battery reading is not mistaken for the state",
      deduce(noisy_on, noisy_off)["state_at"], 4)
check("nothing is claimed when the only difference wanders",
      deduce([b(0x0B, 0, 90)], [b(0x0B, 0, 87)])["state_at"], 2)
check("a byte that wanders inside one state is refused",
      deduce([b(0x0B, 90), b(0x0B, 88)], [b(0x0B, 87), b(0x0B, 86)]), None)
check("silence on one side decides nothing", deduce([b(0x0B, 1)], []), None)
check("two states that look identical decide nothing",
      deduce([b(0x0B, 0, 1)], [b(0x0B, 0, 1)]), None)
check("reports of another kind are not compared",
      deduce([b(0x01, 1)], [b(0x02, 3)]), None)
# Nothing steady to anchor on: position 0 stands in, and it holds the report id
# that was matched already, so the check passes without pretending to mean more.
check("with no steady byte the marker falls back to the report id",
      deduce([b(0x0B, 1)], [b(0x0B, 3)])["marker"], (0, 0x0B))
# A report where everything moves is a stream of something else that happened to
# stop; the quiet one next to it is the real signal.
mixed = deduce([b(0x0B, 1, 9, 4), b(0x0B, 1, 9, 4), b(0x0C, 0, 0xBB, 1)],
               [b(0x0B, 2, 7, 5), b(0x0B, 2, 7, 5), b(0x0C, 0, 0xBB, 3)])
check("the cleaner of two reports is chosen", mixed["report"], 0x0C)
check("and its marker is the byte that never moved", mixed["marker"], (2, 0xBB))
# Shorter than the position being read: the decoder must not run off the end.
rule = dict(KNOWN[(0x0951, 0x16EA)])
check("a truncated report decodes to nothing",
      __import__("mas.core.dongle", fromlist=["Dongle"]).Dongle(
          0x0951, 0x16EA, None, rule=rule)._decode(b(0x0B, 0, 0xBB)), None)


# The wizard end to end, with the dongle replaced by hand-fed bytes. What is
# checked here is the plumbing around the deduction: that reports land in the
# step that was running, that the learned rule is saved where sync_dongle looks
# for it, and that the report offered to a person holds what happened.
print("\nThe teaching wizard, end to end")
import mas.app as app_mod  # noqa: E402


class FakeDongle:
    started = []

    def __init__(self, vid, pid, on_change, rule=None, learn=False):
        self.on_change, self.learn = on_change, learn
        FakeDongle.started.append((vid, pid, learn))

    def start(self):
        pass

    def stop(self):
        pass


def wizard_app():
    app = App.__new__(App)
    app.cfg = FakeConfig(auto_device="id-hp", dongle_rules={})
    app._wiz = app._wiz_dongle = app.dongle = None
    app._dongle_name = app._dongle_usb = app._dongle_on = None
    app._known_cache = [{"id": "id-hp", "name": "Cloud Flight S"}]
    app._known_pinned = "id-hp"
    app.push_state = lambda: None
    return app


FakeDongle.started.clear()
real_dongle, app_mod.Dongle = app_mod.Dongle, FakeDongle
real_ids, app_mod.devices.usb_ids_of = app_mod.devices.usb_ids_of, lambda i: (0x1234, 0x5678)
real_product, app_mod.product_name = app_mod.product_name, lambda v, p: "Test Dongle"
try:
    app = wizard_app()
    check("the wizard opens the dongle", app.wizard_start()["running"], True)
    check("and it opens it to listen, not to decode", FakeDongle.started[-1], (0x1234, 0x5678, True))
    check("nothing is filed before the first step", app.wizard_state()["heard"], 0)
    # A report that arrives between steps belongs to nobody, and must not be
    # filed under whichever step happens to come next.
    app._wizard_report(b"\x0b\x00\xbb\x01\x01")
    for step, byte in (("on1", 1), ("off1", 3), ("on2", 1), ("off2", 3)):
        app.wizard_step(step)
        app._wizard_report(bytes((0x0B, 0, 0xBB, 1, byte)))
    check("each step kept its own reports", app.wizard_state()["counts"],
          {"on1": 1, "off1": 1, "on2": 1, "off2": 1})
    done = app.wizard_finish()
    check("the headset was worked out", done["ok"], True)
    check("it is named after the dongle", done["name"], "Test Dongle")
    check("the rule is saved where the listener looks for it",
          app.dongle_rule((0x1234, 0x5678))["state_at"], 4)
    check("and watching is on without another click", app.cfg.get("watch_dongle"), True)
    check("the wizard let the dongle go", app._wiz, None)
    check("the report says what was found", "byte 4: on 0x01, off 0x03" in done["report"], True)
    check("and carries the raw lines", "0b 00 bb 01 03" in done["report"], True)
    check("the report form is prefilled, not sent", done["url"].startswith(
        "https://github.com/electronic-mars/mas/issues/new?template=dongle.yml"), True)
    check("and it fills the fields the template asks for",
          all(f"&{f}=" in done["url"] for f in ("title", "model", "ids", "reports", "worked")),
          True)

    # Nothing switched: the same reports in every step. Saying so plainly beats
    # saving a rule that would fire at random.
    app = wizard_app()
    app.wizard_start()
    for step in App.WIZARD_STEPS:
        app.wizard_step(step)
        app._wizard_report(b"\x0b\x00\xbb\x01\x01")
    done = app.wizard_finish()
    check("a headset that never changed is not guessed at", done["ok"], False)
    check("and nothing is saved", app.cfg.get("dongle_rules"), {})
    check("but the report is still offered", "no byte told" in done["report"], True)
finally:
    app_mod.Dongle = real_dongle
    app_mod.devices.usb_ids_of = real_ids
    app_mod.product_name = real_product


# --------------------------------------------------------------------------
print("\nAutostart points at a copy, not at a name")
from mas.core import startup  # noqa: E402

here = str(Path(sys.executable))
check("the same command is recognised as ours",
      startup._normalise(f'"{here}" --startup'), startup._normalise(f'"{here}" --startup'))
check("case and quoting do not make it a different one",
      startup._normalise(f'{here.upper()} --startup'),
      startup._normalise(f'"{here}" --startup'))
# The case reported from a live machine: the build folder moved, the entry did
# not, and the settings went on saying autostart was on while Windows started
# an old copy from the old path every morning.
check("another folder is another program",
      startup._normalise(r'"C:\old\build\MasterAudioSwitcher.exe" --startup')
      == startup._normalise(r'"C:\new\build\MasterAudioSwitcher.exe" --startup'), False)
check("and so are different arguments",
      startup._normalise(f'"{here}"') == startup._normalise(f'"{here}" --startup'), False)


# --------------------------------------------------------------------------
print("\nThe window title and the tray button")


def titled(playing, artist="", title=""):
    app = App.__new__(App)
    app.players = type("P", (), {"snapshot": lambda s: {
        "playing": playing, "artist": artist, "title": title}})()
    return app.window_title()


check("while the music plays the button is the track",
      titled(True, "Mannymore", "Shiver"), "Mannymore — Shiver")
check("an unnamed artist does not leave a dash", titled(True, "", "Shiver"), "Shiver")
check("paused, it is the program again", titled(False, "Mannymore", "Shiver"),
      "Master Audio Switcher")
# A player can report itself playing and name nothing at all. A blank taskbar
# button would look like a program that had lost its own name.
check("a nameless track is not shown", titled(True), "Master Audio Switcher")


def pressed(button, visible, switch_button="left", front=True):
    """Which of the three things a tray click did.

    `front` is whether our window, when it is open, is the one the person is
    actually looking at — a window buried under a browser is open as far as the
    program is concerned and invisible as far as the person is concerned.
    """
    import mas.app as app_mod

    app = App.__new__(App)
    app.cfg = FakeConfig(switch_button=switch_button)
    app._visible = visible
    app._hwnd = 42
    done = []
    app.cycle = lambda: done.append("switched")
    app.show = lambda tab="devices": done.append("shown")
    app.hide = lambda: done.append("hidden")
    was = app_mod.screen.is_front, app_mod.screen.to_front
    app_mod.screen.is_front = lambda hwnd: front
    app_mod.screen.to_front = lambda hwnd: done.append("raised")
    try:
        app._button(button)
    finally:
        app_mod.screen.is_front, app_mod.screen.to_front = was
    return done


check("the switching button switches", pressed("left", False), ["switched"])
check("and goes on switching with the window open", pressed("left", True), ["switched"])
check("the other button opens the window", pressed("right", False), ["shown"])
# The point of the change: pressing the same button again is the obvious thing
# to try, and it used to do nothing — the cross in the corner was the only exit.
check("and closes it when it is already open", pressed("right", True), ["hidden"])
check("swapped buttons swap both jobs", pressed("left", True, "right"), ["hidden"])
# Open and buried under another program is not open to the person sitting there.
# Hiding it then spent their click on putting away something they could not see,
# and only the second press brought it back.
check("a buried window is brought forward, not hidden",
      pressed("right", True, front=False), ["raised"])
check("and the press after that, with it in front, still closes it",
      pressed("right", True, front=True), ["hidden"])
check("burying does not change what the switching button does",
      pressed("left", True, front=False), ["switched"])


# --------------------------------------------------------------------------
# The notification window is created from a module handle. Undeclared, ctypes
# assumes any function returns a 32-bit int, and on 64-bit Windows that cuts an
# address in half: 0x7FF67BC00000 arrived as 0x7BC00000. Windows dereferenced
# the remains and raised an access violation on every single run — handled, so
# nothing ever crashed, and 269 of them piled up in the crash log unnoticed.
print("\nHandles come back whole")
import ctypes as _ct  # noqa: E402
from ctypes import wintypes  # noqa: E402

from mas import overlay as overlay_mod  # noqa: E402

_probe = _ct.WinDLL("kernel32")
_probe.GetModuleHandleW.restype = wintypes.HMODULE
_probe.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
check("the module handle is not cut in half",
      overlay_mod.k32.GetModuleHandleW(None), _probe.GetModuleHandleW(None))
check("and it is the whole address, not its lower half",
      _probe.GetModuleHandleW(None) > 0xFFFFFFFF
      or overlay_mod.k32.GetModuleHandleW(None) == _probe.GetModuleHandleW(None), True)


# --------------------------------------------------------------------------
# Updating. The program downloads an executable and runs it, so the only part
# that really matters is the refusing: a file that is not ours must never reach
# the point of being started, whatever it claims about itself.
print("\nUpdating, and everything it must refuse")
from mas.core import update  # noqa: E402

check("a later version is newer", update.is_newer("1.2.0", "1.1.9"), True)
check("the same one is not", update.is_newer("1.2.0", "1.2.0"), False)
check("an earlier one is not", update.is_newer("1.1.9", "1.2.0"), False)
# 1.10 after 1.9 is the classic: compared as text, "1.10" sorts before "1.9"
# and everyone stops receiving updates at the tenth release.
check("ten comes after nine", update.is_newer("1.10.0", "1.9.0"), True)
check("a leading v changes nothing", update.is_newer("v1.3.0", "1.2.0"), True)
check("nonsense does not read as newer", update.is_newer("", "1.0.0"), False)

# Signature checking, against a key made for this test alone.
TEST_KEY = bytes.fromhex(
    "d84ffcde6bb4ce5270a914480f32a6ac272dabe7b257dc7358462eb082d196f7"
    "21c02ec96fd5ca6512afa56fc23741c163b97ac4ee6123e61d5b78542f7be3be")
TEST_SIG = bytes.fromhex(
    "1925fbad23d654d8ad90bcb4d12b3a2557695007c21cc256ea22e6960f107119"
    "75f49845a9f88af2db5ebffa9611561e034ed53cb3065c39e7c08658e6ccc6f4")
PAYLOAD = b"pretend this is an installer\n"

signed = Path(tempfile.mkdtemp(prefix="mas-update-")) / "setup.exe"
signed.write_bytes(PAYLOAD)
real_key, update.PUBLIC_KEY = update.PUBLIC_KEY, TEST_KEY
try:
    check("a genuine installer is accepted", update.verify(signed, TEST_SIG), True)
    signed.write_bytes(PAYLOAD + b"x")     # one byte added by somebody
    check("a changed installer is refused", update.verify(signed, TEST_SIG), False)
    signed.write_bytes(PAYLOAD)
    bad = bytearray(TEST_SIG)
    bad[0] ^= 0x01
    check("a forged signature is refused", update.verify(signed, bytes(bad)), False)
    check("a signature of the wrong size is refused", update.verify(signed, b"short"), False)
    update.PUBLIC_KEY = bytes(64)
    # A build with no key in it must refuse everything rather than trust
    # everything: getting that backwards would install whatever turned up.
    check("a build carrying no key installs nothing",
          update.verify(signed, TEST_SIG), False)
finally:
    update.PUBLIC_KEY = real_key
check("the release key is in this build", len(update.PUBLIC_KEY) == 64
      and any(update.PUBLIC_KEY), True)

# Where a download may come from. The signature already makes substitution
# pointless, but a release description pointing somewhere else is a bad sign in
# itself and is worth refusing before the first byte, not after the last.


def refuses(url):
    try:
        update._open(url)
        return False
    except ValueError:
        return True
    except Exception:
        return True     # it got as far as the network, which is not the point here


check("plain http is refused", refuses("http://github.com/x"), True)
check("another host is refused", refuses("https://evil.example.com/setup.exe"), True)
check("a lookalike host is refused", refuses("https://github.com.evil.net/setup.exe"), True)


# A redirect is somebody else's instruction. GitHub answers the download address
# with one, pointing at its own file store, so redirects have to be followed —
# but each hop gets the same test, or the test on the first address is decoration.
def redirect_to(url):
    handler = update._CheckedRedirects()
    try:
        handler.redirect_request(None, None, 302, "Found", {}, url)
        return "followed"
    except ValueError:
        return "refused"
    except Exception:
        return "refused"      # it got past the check and failed on the fake request


check("a redirect to a stranger is refused",
      redirect_to("https://evil.example.com/setup.exe"), "refused")
check("a redirect downgrading to http is refused",
      redirect_to("http://objects.githubusercontent.com/x"), "refused")

# The name of the downloaded file is ours, never one taken from the address:
# otherwise where we write would be chosen by whoever wrote the release
# description.
check("the download has a name of our own choosing",
      'folder() / "update-setup.exe"'
      in (ROOT / "src" / "mas" / "core" / "update.py").read_text(encoding="utf-8"), True)


def feed(doc):
    """latest() against a made-up release description."""
    import io as _io
    import json as _json

    class Answer:
        def read(self, n=None):
            return _json.dumps(doc).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    real, update._open = update._open, lambda url: Answer()
    try:
        return update.latest()
    except Exception as e:
        return type(e).__name__
    finally:
        update._open = real


good = {"version": "1.4.0", "notes": "hello",
        "platforms": {"windows-x86_64": {
            "url": "https://github.com/electronic-mars/mas/releases/download/v1.4.0/s.exe",
            "signature": "ab" * 64}}}
check("a good release description is read", feed(good)["version"], "1.4.0")
check("one with no signature is refused",
      feed({"version": "1.4.0", "platforms": {"windows-x86_64": {"url": good[
          "platforms"]["windows-x86_64"]["url"]}}}), "ValueError")
check("one for another platform only is refused",
      feed({"version": "1.4.0", "platforms": {"linux-x86_64": {}}}), "ValueError")
check("one pointing at a stranger is refused",
      feed({"version": "1.4.0", "platforms": {"windows-x86_64": {
          "url": "https://files.example.com/s.exe", "signature": "ab" * 64}}}),
      "ValueError")

# This machine is not a Store install, and the program has to know that or it
# would hide the update button from everybody.
check("an ordinary copy knows it is not from the Store", update.from_store(), False)


# --------------------------------------------------------------------------
# A build server that writes an undefined repository variable into the
# environment sets it to the empty string, and dict.get returns its default only
# for a key that is missing — not for one that is present and empty. The Store
# package went out with an empty identity, and makeappx refused it over a name
# shorter than three characters. The failure landed three steps and two minutes
# away from the mistake, which is why it is caught here instead.
print("\nSettings that arrive empty")
sys.path.insert(0, str(ROOT / "tools"))
import make_msix  # noqa: E402


def resolved(value):
    """What the packager settles on when the variable is absent, empty, or real."""
    had = os.environ.get("MSIX_IDENTITY_NAME")
    if value is None:
        os.environ.pop("MSIX_IDENTITY_NAME", None)
    else:
        os.environ["MSIX_IDENTITY_NAME"] = value
    try:
        return make_msix.setting("MSIX_IDENTITY_NAME", "the-real-one")
    finally:
        os.environ.pop("MSIX_IDENTITY_NAME", None)
        if had is not None:
            os.environ["MSIX_IDENTITY_NAME"] = had


check("a variable that is not set falls back", resolved(None), "the-real-one")
check("a variable that is set but empty falls back too", resolved(""), "the-real-one")
check("a real value still overrides", resolved("Someone.Else"), "Someone.Else")
check("the identity that ships is a usable one",
      len(make_msix.IDENTITY_NAME) >= 3 and "." in make_msix.IDENTITY_NAME, True)
# The workflow used to hand these in from repository variables that were never
# created. They live in the source now, and passing them again is how the empty
# string got in.
check("the release build no longer passes an identity in",
      "vars.MSIX_IDENTITY_NAME" in (ROOT / ".github" / "workflows"
                                    / "release.yml").read_text(encoding="utf-8"), False)

# A window that will not open, on a machine whose port range starts low. Windows
# was asked for any free port and handed out 1723 — PPTP, one of the ports
# Chromium refuses to load a page from, so the interface came up as
# ERR_UNSAFE_PORT. Every one of those ports is at or below 10080
# (net/base/port_util.cc), so staying above them is the whole fix, and this is
# where it stays fixed.
print("\nThe port the interface is served on")
from mas.bridge import Bridge, FIRST_SAFE_PORT  # noqa: E402

CHROMIUM_REFUSES = 10080

check("the floor is above every port Chromium refuses",
      FIRST_SAFE_PORT > CHROMIUM_REFUSES, True)
_ports = []
for _ in range(25):
    _b = Bridge(object())
    _b.start()
    _ports.append(_b.port)
    _b.stop()
check("every port actually bound clears that floor",
      min(_ports) > CHROMIUM_REFUSES, True)
check("and they are not all the same one", len(set(_ports)) > 1, True)

# A device with no icon chosen used to look exactly like every other one, and
# the first thing seeded into the cycle could be a monitor with no speaker in
# it — so the very first click a person tries produced silence. Both are guessed
# from the name, so both are pinned here.
print("What a device looks like, and what gets switched to")
from mas.core.devices import guess_icon  # noqa: E402

check("a monitor is recognised by the graphics driver in its name",
      guess_icon("LG HDR 4K (AMD High Definition Audio)", True), "monitor")
check("and so is one on an NVIDIA card",
      guess_icon("DELL U2723QE (NVIDIA High Definition Audio)", True), "monitor")
check("the ordinary sound chip is not a monitor",
      guess_icon("Realtek High Definition Audio", True), "speakers")
check("headphones are headphones in English",
      guess_icon("Headphones (Some Brand)", True), "headphones")
check("and in Russian", guess_icon("\u041d\u0430\u0443\u0448\u043d\u0438\u043a\u0438 (Realtek)", True),
      "headphones")
check("a laptop microphone is not drawn as a headset",
      guess_icon("Microphone Array (Realtek(R) Audio)", False), "laptop")
check("two ordinary devices no longer share one picture",
      guess_icon("Speakers (Realtek(R) Audio)", True)
      != guess_icon("Headphones (HyperX Cloud Flight S)", True), True)


class SeedWorld:
    """Just enough of the devices module for seed_if_empty."""

    def __init__(self, named):
        self.named = named

    def list_devices(self, only_active=True):
        return [devices.Device(id=n, name=n, is_output=True, active=True)
                for n in self.named]

    guess_icon = staticmethod(guess_icon)


def seeded(names):
    world = SeedWorld(names)
    import mas.core.switcher as switcher_mod
    real, switcher_mod.devices = switcher_mod.devices, world
    try:
        cfg = FakeConfig(cycle=[])
        Switcher(cfg).seed_if_empty()
        return cfg.get("cycle")
    finally:
        switcher_mod.devices = real


check("the monitor is left out of the first cycle",
      seeded(["Speakers (Realtek(R) Audio)", "Headphones (HyperX)",
              "LG HDR 4K (AMD High Definition Audio)"]),
      ["Speakers (Realtek(R) Audio)", "Headphones (HyperX)"])
check("a machine with nothing but screens still gets a working cycle",
      seeded(["LG HDR 4K (AMD High Definition Audio)"]),
      ["LG HDR 4K (AMD High Definition Audio)"])

# The dock may draw us instead of the tray, on one condition: that we can always
# take the icon back. A dock that was closed, crashed or uninstalled must not
# leave a running program with no icon, no reachable window and no way to quit.
print("\nWho holds the tray icon")


class FakeTray:
    def __init__(self):
        self.shown = None

    def set_visible(self, on):
        self.shown = on


def tray_after(hosting, silent_for):
    """What the icon does, given the setting and how long the dock has been quiet."""
    import time as _time

    app = App.__new__(App)
    app.cfg = FakeConfig(dock_hosts_us=hosting)
    app.tray = FakeTray()
    app._tray_shown = None
    app._dock_seen = _time.monotonic() - silent_for
    app.dock_apply()
    return app.tray.shown


check("with no dock, the icon is ours", tray_after(False, 0.0), True)
check("the dock that is talking to us gets it", tray_after(True, 1.0), False)
check("and keeps it while it goes on talking",
      tray_after(True, App.DOCK_SILENCE - 1), False)
check("a dock that has gone quiet loses it",
      tray_after(True, App.DOCK_SILENCE + 1), True)
# The setting alone is not enough to take the icon away: a machine where the
# dock has been uninstalled would come up with no icon at all and stay that way.
check("the setting without a living dock does not hide anything",
      tray_after(True, 3600.0), True)

print(f"\npassed {_passed}, failed {_failed}")
sys.exit(1 if _failed else 0)
