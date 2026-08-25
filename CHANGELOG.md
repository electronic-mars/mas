# Changelog

One section per release, newest first. Version numbers follow
[semantic versioning](https://semver.org/).

## 1.0.1

- the update button now finishes what it starts. In 1.0.0 the program handed
  over to the installer and quit, and the installer — running silently, with
  nobody to answer its questions — took the safe default for both of them and
  gave up: first because the program was still closing, then because the program
  will not close on request, since closing its window means going to the tray.
  The installer now ends the running copy itself and starts the new one. Anyone
  on 1.0.0 gets this by pressing update: the fix is in the installer that arrives,
  not in the copy that is running.

## 1.0.0

The first public release.

- switching audio by clicking the tray icon, cycling through the devices you
  marked;
- priority device: sound moves to it the moment it appears and returns when it
  goes away;
- watching a wireless headset through its USB dongle (HyperX Cloud Flight S),
  plus a learning mode for unknown dongles;
- volume mixer with per-application levels;
- media keys aimed at the player that is actually in front, with verification
  that the command was obeyed;
- a global hotkey that works over a fullscreen game;
- the microphone follows its headset and comes back afterwards;
- a window in the spirit of Braun instruments: dark and light themes, a compact
  view, a first-run welcome;
- an icon set built on Hugeicons: 44 devices and marks in seven sizes, plus 32
  interface icons;
- fifteen languages, with the interface opening in the language Windows is set
  to on the first run;
- a nominated player: media commands address it whatever else is playing, and
  starting it pauses the others.
