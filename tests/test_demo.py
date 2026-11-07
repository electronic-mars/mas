"""The made-up sound setup behind MAS_DEMO=1. Same runner as test_smoke.py."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["MAS_DEMO"] = "1"
os.environ["MAS_DEMO_DATA"] = tempfile.mkdtemp(prefix="mas-demo-tests-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mas.core import demo  # noqa: E402

demo.install()

from mas.core import devices, meter, mixer  # noqa: E402
from mas.core.config import Config  # noqa: E402
from mas.paths import data_dir  # noqa: E402

_passed, _failed = 0, 0


def check(label: str, got, want):
    global _passed, _failed
    if got == want:
        _passed += 1
    else:
        _failed += 1
        print(f"  FAILED: {label}\n    got: {got!r}\n    expected: {want!r}")


def headset(on: bool) -> None:
    flag = data_dir() / demo.HEADSET
    flag.touch() if on else flag.unlink(missing_ok=True)


print("Nothing real is touched")
check("the settings are in the demo's own folder",
      str(data_dir()).startswith(os.environ["MAS_DEMO_DATA"]), True)
cfg = Config()
check("it speaks English", cfg.get("language"), "en")
check("the welcome is already done", cfg.get("onboarded"), True)
check("the wireless headset takes over when it comes", cfg.get("auto_device"), demo.WIRELESS)

print("\nThe devices")
names = {d.name for d in devices.list_devices(max_age=0)}
check("the speakers are there", "Speakers (Demo Audio)" in names, True)
check("the wireless headset is away at the start", "Headset (Demo Wireless)" in names, False)
check("the sound starts on the speakers", devices.default_id(), demo.SPEAKERS)
check("the microphone starts on the webcam", devices.default_id(is_output=False), demo.WEBCAM)

print("\nA switch only moves the mark")
check("switching succeeds", devices.set_default(demo.HEADPHONES), True)
check("the headphones are the default", devices.default_id(), demo.HEADPHONES)
devices.set_default(demo.SPEAKERS)

print("\nThe headset comes and goes")
presence = devices.Presence()
was = presence.read()
headset(True)
now = presence.read()
check("its endpoint turns active", (was[demo.WIRELESS], now[demo.WIRELESS]), (4, 1))
devices.invalidate()
check("it is in the list", demo.WIRELESS in {d.id for d in devices.list_devices(max_age=0)}, True)
check("its microphone is found by its name", devices.microphone_of(demo.WIRELESS).id, demo.WIRELESS_MIC)
devices.set_default(demo.WIRELESS)
headset(False)
check("gone, the sound falls back to the speakers", devices.default_id(), demo.SPEAKERS)

print("\nEvery volume starts at 21")
vol, _ = meter._open(output=True)
check("the device", vol.GetMasterVolumeLevelScalar(), demo.VOLUME)
check("every application", {s.volume for s in mixer.list_sessions()}, {demo.VOLUME})
mixer.set_volume("music.exe", 1.0)
check("the mixer moves an application", next(s.volume for s in mixer.list_sessions() if s.key == "music.exe"), 1.0)
check("the meter of a playing application moves", 0 < mixer.session_meters()["music.exe"].GetPeakValue() <= 1, True)

print(f"\npassed {_passed}, failed {_failed}")
sys.exit(1 if _failed else 0)
