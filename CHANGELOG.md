# Changelog

One section per release, newest first. Version numbers follow
[semantic versioning](https://semver.org/).

## 1.1.0

A redesign, every piece of it compared blind against the old screens before it
went in.

- the front panel has one display: the device playing, the volume in segment
  digits with the signal beside it, and a volume bar that turns with the knob
  and can be dragged instead of it; a fourth key switches the sound off;
- the device list is one card: each device by its own name ("HyperX Cloud
  Flight S") with what it is underneath ("Headphones"), a green "Playing now"
  on the one playing;
- sound input: a key on the microphone row switches it off; the main
  microphone is picked with a round mark and remembered across restarts; a
  microphone can be pinned to each output in the settings, automatic by default;
- the mixer: one grid, a live level under every slider, a mark and a count of
  the applications making sound;
- the notification after a switch is a card with the volume, and the same card
  with the track comes up while the pointer rests on the tray icon;
- the first run shows the taskbar, the icon and what a click does, and lets the
  devices it goes through be ticked right there;
- the window can hide itself when another window is clicked (Controls, off by
  default).

## 1.0.9

- the sound after a switch is two soft short notes instead of a hard beep;
- the window no longer opens with the mini-view button outlined and its
  tooltip hanging over the desktop: the engine gave that button the focus as
  though it had been reached with the keyboard.

## 1.0.8

- headphones chosen by hand give the sound back when they are switched off,
  just as the ones the program took by itself. Any manual switch used to drop
  that, including a switch onto the headphones: switched away and back by hand,
  the headset was turned off and the sound stayed on it, silent. Choosing a
  microphone by hand no longer affects it at all.

## 1.0.7

Three things the speed-up in 1.0.6 got wrong, found in review:

- a headset plugged in could be missed: the device list was re-read before the
  change was reported, and a read failing on a device half-way through
  arriving lost the change;
- a click within two seconds of Windows switching the sound on its own could
  land on the device already playing and do nothing;
- turning the volume right after pressing the mute key could leave the sound
  off.

## 1.0.6

- a click on the Master Control Dock widget switches in a fifth of a second
  again; it had come to take two and a half, and up to ten on a bad day. The
  dock asks for the state every second, and every third question enumerated
  all fifty audio endpoints of the system while each one built a new device
  enumerator — enough to keep the Windows audio service busy for everybody,
  including this program's own switches. The answers now come from what the
  program already watches in its own thread, in two milliseconds;
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
