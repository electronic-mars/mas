# Contributing

## Fixing a translation

This is the most useful thing you can do, and the easiest. Twelve of the fifteen
languages were translated by machine and read over once — if something sounds
wrong in your language, it probably is.

Every language is one file: `src/mas/ui/locales/<code>.json`.

```json
{
  "code": "de",
  "name": "Deutsch",
  "strings": {
    "tab_devices": "Geräte",
    ...
  }
}
```

Rules, all of them:

- Keep the keys exactly as they are, and keep every key. A missing one shows the
  English text instead.
- Keep `%s` where it is — a device name is put there.
- Leave product names alone: Windows, Spotify, Discord, Zoom, Teams, HDMI, USB,
  Bluetooth, Ctrl, Alt, Shift, Win.
- Use the words Windows itself uses in your language for system things — people
  look for those exact words.
- Tabs and buttons are narrow. A translation twice the length of the English one
  is cut off, not wrapped. `python tests/test_smoke.py` refuses anything too long.

## Adding a language

Drop a `<code>.json` file in the same folder and run:

```
python tools/translate_locales.py --index-only
```

That rebuilds the list the dropdown is built from. Nothing else to register.

To have the machine do the first pass for a language, add it to `LANGUAGES` and
`ENGLISH_NAMES` in `tools/translate_locales.py` and run the script with a
`DEEPSEEK_API_KEY` in the environment — it sends only the keys that are missing.

## Adding a wireless headset

Windows does not report when a headset on a USB dongle is switched on or off, so
the program reads the dongle's own status report. Only decoded dongles work.

Settings → Diagnostics → **Learn this dongle**, switch the headset on and off
about six times, then open the report file and attach it to an issue using the
"Wireless headset support" template. Nothing is sent by the program itself.

## Code

- Run both suites before proposing a change:
  `python tests/test_smoke.py` and `python tests/test_device_icons.py`.
- Comments here explain **why**, not what. Most of them record something that
  actually broke, with the measurement that proved it. Please keep that habit —
  and please do not delete such a comment without understanding what it is
  protecting.
- The interface is served to a WebView2 window over a local bridge. Python never
  calls JavaScript: it did once, from a background thread, and hung the window
  dead. The page asks; Python answers.
- COM objects belong to the thread that created them. Releasing one on another
  thread crashes the process, which is why garbage collection is disabled and
  why several threads own their own objects. If you are touching that area, read
  the comments in `src/mas/core/meter.py` and `src/mas/app.py` first.

## Reporting a bug

Include the version from the About tab, your Windows build (`winver`), and the
log from Settings → Diagnostics. Note that the log contains the names of tracks
that were playing — remove them if you would rather not share them.
