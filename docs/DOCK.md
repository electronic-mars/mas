# Drawing this program somewhere else

Master Audio Switcher lives in the tray. It can live in another program's panel
instead — Master Control Dock is the one this was written for — and this is
everything that companion needs to know. Nothing here requires a build of ours,
a shared library, or a header file: it is a local HTTP interface that already
existed, because it is how our own window talks to the program.

## Finding us

The port is chosen at random on every start and so is the token. That is
deliberate — it keeps a web page from driving the program — and it means a
companion cannot guess either. So we leave a note:

```
%LOCALAPPDATA%\MasterAudioSwitcher\bridge.json
```

```json
{
  "protocol": 2,
  "url": "http://127.0.0.1:41235/",
  "token": "…",
  "pid": 15084,
  "version": "1.0.3"
}
```

Written when the program starts, removed when it exits.

**Look in two places.** The copy from the Microsoft Store runs inside a package,
and what it writes to `%LOCALAPPDATA%` may be redirected into the package's own
store. Check the plain path first, then:

```
%LOCALAPPDATA%\Packages\ElectronicMARS.MasterAudioSwitcher_8b14r1jdzqs64\LocalCache\Local\MasterAudioSwitcher\bridge.json
```

**Do not trust the file — call.** A crash leaves it behind, and a stale port may
by then belong to something else. Treat "the program is running" as the answer
to `dock_hello`, never as the presence of a file. If `protocol` is a number you
do not know, stop and say so rather than guessing.

**Installed but not running** is a different question, and the answer is in the
registry, not here:
`HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{7C4E3F2A-9B51-4D8E-A6C7-2F1D0B8E5A34}_is1`
carries `DisplayIcon` and `InstallLocation` for the ordinary install. For the
Store copy, ask Windows for the package family name above.

## Talking to us

```
POST <url>api/<method>
X-MAS-Token: <token>
Content-Type: application/json

{ …arguments by name… }
```

Answers are `{"ok": true, "result": …}` or `{"ok": false, "error": "…"}` with
status 500. A missing or wrong token is 403.

There is an `Origin` check as well, and it lets through any request that carries
no `Origin` header at all — which is every request a desktop program makes. It
exists to keep a browser page out, not you.

## The methods you want

| method | arguments | what it does |
|---|---|---|
| `dock_hello` | `showing: bool` | says you are there and whether our widget is on screen; returns the whole state |
| `dock_take_over` | `hosting: bool` | take the tray icon away, or hand it back |
| `switch_next` | — | exactly what a click on the tray icon does |
| `bring_forward` | — | opens our window in front — what the other tray button does |
| `switch_to` | `device_id: str` | move the sound to one device |
| `get_state` | — | the same state without the heartbeat |
| `media` | `action: str` — `play`, `next`, `prev` | the media keys, aimed at the chosen player |
| `now_playing` | — | what is playing, for a label |
| `set_master` | `value: float` 0…1 | the volume of the current device |
| `set_master_mute` | `muted: bool` | |

`dock_hello` returns:

```json
{
  "protocol": 2,
  "version": "1.0.3",
  "hosting": false,
  "state": {
    "outputs": [
      {"id": "{0.0.0…}", "name": "Speakers (Realtek(R) Audio)",
       "kind": "output", "icon": "speakers",
       "in_cycle": true, "is_default": true}
    ],
    "inputs": [ … the microphones, same shape … ],
    "known_outputs": [ … devices seen before, present or not … ],
    "settings": { … every setting, including "theme" … }
  }
}
```

**Leave `get_meter` alone.** It is our own window's poll and it consumes signals
meant for that window — calling it from outside makes our interface miss things.
Ask `dock_hello` once a second instead; it costs nothing worth counting and it
doubles as the heartbeat.

## Icons

Do not go looking in our installation folder. Every device carries an `icon`
name, and the picture for it is served by the same address:

```
GET <url>icons/devices/<icon>_<dark|light>_<16|20|24|32|40|48|64>.png
GET <url>icons/devices/<icon>.svg
```

No token needed for these. The SVG is a single-colour outline and is the better
choice for a panel that tints its own glyphs.

## Taking the tray icon

Call `dock_take_over` with `hosting: true` and our icon leaves the tray. The
setting is remembered, so it stays that way after a restart.

**And then you must keep saying hello — with `showing: true`.** If nothing
calls `dock_hello` or `dock_take_over` for fifteen seconds, or the last hello did
not say `showing: true`, the icon comes back by itself. This is not
a quirk to work around — it is the whole reason we are willing to give the icon
up at all. A dock that has been closed, has crashed, or has been uninstalled
would otherwise leave a running program with no icon, no window anybody can
reach, and no way to quit it short of the task manager. Once a second is plenty.

**`showing` means our widget is on a screen the person can see, now.** Not
"configured", not "about to be": drawn. Protocol 1 took a hello as enough, and a
dock that was alive and answering but never drew the widget kept the tray icon
for an hour — the program was running with no way into it at all. If the widget
is removed, hidden with its bar, or not placed on any bar, say `showing: false`,
or stop asking for the icon.

Only call `dock_take_over` with `hosting: true` once the widget is actually on
screen. Calling it at startup, before anything is drawn, is exactly the case
above.

Hand it back explicitly (`hosting: false`) when your widget is removed or the
program is shutting down. Do not rely on the timeout for the tidy case: fifteen
seconds of a missing icon is fifteen seconds of a person wondering what
happened.

## What not to do

- Do not read or write our settings file. `set_setting` exists.
- Do not start us by launching the exe from a path you found in the registry
  while a copy may already be running — we allow one instance, and the second
  exits without saying much.
- Do not cache the port. Re-read the note when a call fails; we may have been
  restarted, by an update among other things.
- Do not poll faster than you draw. The state is small, but it costs us a device
  enumeration, and that is the one expensive thing in this program.
