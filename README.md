# Master Audio Switcher

A tray utility for Windows 11 that switches audio between speakers and
headphones with one click on the tray icon.

![Devices](docs/screens/01-devices-dark.png)

## What it does

- **One click on the tray icon** cycles through the devices you marked.
- **Priority device.** The moment a chosen device appears, sound moves to it.
  When it goes away, sound returns to where it was.
- **Wireless headsets that Windows cannot see.** A headset on a USB dongle keeps
  its audio endpoint alive whether it is powered on or off, so Windows never
  reports the change. Master Audio Switcher reads the dongle's own status report
  over HID — read-only, nothing is ever written to the device.
- **Volume mixer** with per-application levels.
- **Media keys** for the player that is actually in front.
- **A global hotkey** that works over a fullscreen game.
- **A microphone follows its headset**, and comes back when you switch away.

Nothing is sent anywhere. No telemetry, no accounts, no network calls except an
explicit check for a newer release.

## Screenshots

| Mixer | Settings | About |
|---|---|---|
| ![](docs/screens/04-mixer-dark.png) | ![](docs/screens/06-settings-dark.png) | ![](docs/screens/17-about-dark.png) |

Light theme, the welcome screen and the rest are in [docs/screens](docs/screens).

## Requirements

- Windows 11 (Windows 10 should work; less tested)
- [WebView2 runtime](https://developer.microsoft.com/microsoft-edge/webview2/) —
  present on Windows 11 by default

## Running from source

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m mas
```

Building the executable:

```
.venv\Scripts\pyinstaller build\mas.spec --distpath build\mas --workpath build\work
```

Note: PyInstaller does not re-embed the application icon when only the `.ico`
changes. Delete `build\work` first, or you will ship the previous icon.

Tests:

```
.venv\Scripts\python tests\test_smoke.py
.venv\Scripts\python tests\test_device_icons.py
```

## Wireless headsets

Only dongles whose status report has been decoded are supported. Right now that
is **HyperX Cloud Flight S** (`0951:16EA`).

If you have a different wireless headset, the program can learn it: it records
the reports the dongle sends while you switch the headset on and off, and the
recording stays in a file on your computer. Nothing is uploaded — sending that
file in is a separate, deliberate step you take yourself.

## Languages

Russian, Ukrainian, English. More are planned; corrections and new translations
are welcome.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).

Third-party components and their licenses: [THIRD-PARTY.md](THIRD-PARTY.md).
Icons are from the free [Hugeicons](https://hugeicons.com) set (MIT).
