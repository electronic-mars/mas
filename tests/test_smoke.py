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


class FakeInfo:
    def __init__(self, status):
        self.playback_status = status


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
hushing._hush([loud, quiet, mine])
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
check("updates go to the latest release",
      'data-url="https://github.com/electronic-mars/mas/releases/latest"' in APP_JS, True)

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

print(f"\npassed {_passed}, failed {_failed}")
sys.exit(1 if _failed else 0)
