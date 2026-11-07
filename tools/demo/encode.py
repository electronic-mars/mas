"""Turns a recorded clip into what the README and the site show.

    python tools/demo/encode.py tools/demo/out/hero.mp4 --poster 5.0 --to docs/demo

Writes, next to each other:
  hero.gif   for the README: GitHub plays a GIF by itself, and an MP4 only as a
             player somebody has to start. 960 wide, 12 frames a second.
  hero.mp4   for the site, H.264, no sound track, streams from the first byte.
  hero.webm  for the site, VP9, usually the smaller of the two.
  hero.jpg   the still the site shows before the video plays, and instead of
             it for anyone who asked for less motion.

Only the scripted part is kept: the recording's sidecar (hero.json) says how
long it lasted, and that much is taken from the end of the file - the end is
exact, the start waits on the screen grabber.
"""
import argparse
import json
import subprocess
from pathlib import Path

from democap import ffmpeg


def run(*args: str) -> None:
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def duration(path: Path) -> float:
    probe = Path(ffmpeg()).with_name("ffprobe.exe")
    out = subprocess.run(
        [str(probe) if probe.exists() else "ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True).stdout
    return float(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("--crop", default="", help="WxH from the top left, e.g. 1280x400")
    ap.add_argument("--poster", type=float, default=0.0, help="seconds into the kept part")
    ap.add_argument("--gif-width", type=int, default=960)
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--to", type=Path, default=None)
    a = ap.parse_args()

    clip: Path = a.clip
    to: Path = a.to or clip.parent
    to.mkdir(parents=True, exist_ok=True)
    name = clip.stem

    kept = json.loads(clip.with_suffix(".json").read_text(encoding="utf-8"))["seconds"]
    start = max(0.0, duration(clip) - kept)
    cut = ["-ss", f"{start:.2f}", "-i", str(clip), "-t", f"{kept:.2f}"]

    crop = ""
    if a.crop:
        w, h = a.crop.split("x")
        crop = f"crop={w}:{h}:0:0,"

    # One palette for the whole clip, dithered gently: the bar's thin lines
    # and small figures blur under heavy dithering.
    run(*cut, "-vf",
        f"{crop}fps={a.fps},scale={a.gif_width}:-1:flags=lanczos,split[a][b];"
        "[a]palettegen=max_colors=128:stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
        "-loop", "0", str(to / f"{name}.gif"))

    vf = crop.rstrip(",") or "null"
    run(*cut, "-vf", vf, "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "24",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(to / f"{name}.mp4"))
    run(*cut, "-vf", vf, "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "38",
        "-row-mt", "1", str(to / f"{name}.webm"))
    run("-ss", f"{start + a.poster:.2f}", "-i", str(clip), "-frames:v", "1", "-vf", vf,
        "-q:v", "3", str(to / f"{name}.jpg"))

    for ext in ("gif", "mp4", "webm", "jpg"):
        f = to / f"{name}.{ext}"
        print(f"{f}  {f.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
