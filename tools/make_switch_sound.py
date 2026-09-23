"""The sound played after a switch — src/mas/ui/sounds/switch.wav.

Two short notes going up, G5 then C6: a "done" rather than an alarm. Sine
tones with a small second harmonic, each with a 4 ms attack and an
exponential decay, and an 8 ms fade at the end so nothing clicks. It replaced
winsound.Beep, a hard-edged 880 Hz tone at full level that started and stopped
dead. The level was picked by ear: 60% quieter than the first draft.

    python tools/make_switch_sound.py
"""
import math
import struct
import wave
from pathlib import Path

RATE = 44100
LENGTH = 0.15
LEVEL = 0.128                     # peak, of full scale
NOTES = [(0.0, 784.0, 0.8), (0.06, 1047.0, 1.0)]    # start s, Hz, gain
ATTACK, DECAY, FADE = 0.004, 0.04, 0.008
OUT = Path(__file__).resolve().parents[1] / "src" / "mas" / "ui" / "sounds" / "switch.wav"


def samples() -> list[float]:
    n = int(RATE * LENGTH)
    buf = [0.0] * n
    for start, freq, gain in NOTES:
        s0 = int(start * RATE)
        for i in range(s0, n):
            t = (i - s0) / RATE
            ph = 2 * math.pi * freq * t
            env = min(1.0, t / ATTACK) * math.exp(-t / DECAY)
            buf[i] += gain * env * (math.sin(ph) + 0.18 * math.sin(2 * ph))
    fade = int(RATE * FADE)
    for k in range(fade):
        buf[n - 1 - k] *= k / fade
    peak = max(abs(x) for x in buf)
    return [x / peak * LEVEL for x in buf]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", round(s * 32767)) for s in samples()))
    print(f"{OUT}  {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
