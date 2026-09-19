# Changelog

One section per release, newest first. Version numbers follow
[semantic versioning](https://semver.org/).

## Unreleased

- switched-off sound is visible: the volume window shows a crossed speaker in
  place of the number, the tray icon gets a cross in its corner, and in the
  mixer the speaker tile changes and a muted application gets a mark on its
  icon. It used to show only as a greyed row in the mixer, and a person with
  the sound off by a keyboard key had to find the cause in Windows;
- turning the knob or a mixer slider switches the sound back on, as the Windows
  slider does;
- `dock_hello` also answers the volume and whether the sound is off.

## 1.0.5

- the tray icon beside the dock widget is the person's choice. Master Control
  Dock can draw this program as a widget; whether the tray icon stays as well is
  a switch in Controls, shown only while a dock is actually drawing us, and on
  by default. The dock must now say it is showing the widget, not merely that
  it is alive — a dock that answered for an hour without drawing anything used
  to keep the icon the whole time (docs/DOCK.md, protocol 2);
- starting the program while it is already running opens its window instead of
  leaving in silence, which with no icon anywhere looked like a program that
  would not start;
- a tray icon held back from a start at sign-in and shown later did not always
  appear; every show now clears its place first;
- a settings file that parses but holds the wrong shapes no longer leaves the
  program alive and useless — each key goes back to its default when wrong;
- the notification after a switch cost a quarter of a second of processor to
  draw; it costs nothing now;
- a content-security policy on the window, for the day a device name is not
  escaped somewhere: the page holds the key to the program.

## 1.0.4

The first minute of the program, taken apart after it was installed on a second
machine and looked broken while working perfectly.

- every device gets its own icon before anybody picks one, guessed from its
  name in English and Russian. They all used to wear the same picture, so the
  laptop and the headset looked identical and the tray icon did not change when
  the sound moved between them. A headset's microphone is drawn as a headset;
  the one built into the laptop, as the laptop;
- notifications are on out of the box. Switching sound is invisible, and without
  them a click that worked said nothing at all;
- the microphone follows the headset out of the box, and goes back when the
  sound does;
- a monitor is no longer put into the switching list on first run: most have no
  speaker, and the very first click would have sent the sound into silence.
  Screens are recognised by the graphics driver in their name;
- the welcome screen teaches the two clicks that matter, draws which mouse
  button is meant, and makes the one sentence people miss — that Windows hides
  new tray icons — a card of its own instead of grey small print;
- teaching an unknown headset dongle moved from Diagnostics into the headphones
  section, next to automatic switching, which it is the other half of. That
  setting is called "Automatic switching" now, which is what people search for;
- clicking the tray icon brings the window forward when it is open but buried
  under another program. It used to hide it — a click spent on putting away
  something nobody could see;
- a headset dongle plugged in after the program started is noticed. The
  listener looked for it once, at startup, and gave up for the whole session if
  it was not there — a week with the dongle out of the laptop, and the headset
  could no longer switch the sound on or off. And the sound is no longer handed
  to a headset the dongle says is switched off;
- Master Control Dock can draw this program as one of its widgets instead of a
  tray icon. The icon always comes back on its own if the dock stops answering.
  How a companion program finds and talks to this one is in docs/DOCK.md.

## 1.0.3

- the window opens on machines whose port range starts low. The interface is
  served over a local address, Windows was asked for any free port, and it could
  hand out one that the browser engine refuses to load a page from — the window
  then came up empty with ERR_UNSAFE_PORT. Seen in the wild on 1723, which is
  PPTP. The port is now chosen above all of them.

## 1.0.2

- clicking the tray icon brings the window in front of what is already open. It
  did appear before — behind the browser, behind the editor — because Windows
  gives the foreground to whoever the person last interacted with, and clicking a
  tray icon counts as talking to the shell, not to us;
- the tray icon is the right one from the moment it appears. It used to show the
  default speakers and change to the real device a second later, at the wrong
  size on a scaled display into the bargain.

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
