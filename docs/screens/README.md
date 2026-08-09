# Screenshots

Taken with one command. The data in them is made up, so a screenshot does not
depend on which speakers happen to be plugged into the machine that took it:

```
python tools/shots.py
```

They are at double resolution: 880×1544 is the real 440×772 window. Long tabs
were shot with a taller window so that nothing is cut off.

| File | What is on it |
|---|---|
| `01-devices-dark` / `02-devices-light` | Devices, dark and light theme |
| `03-devices-mics` | Devices with the microphone list unfolded |
| `04-mixer-dark` / `05-mixer-light` | Mixer: master volume and applications |
| `06-settings-dark` / `07-settings-light` | Settings, first screen |
| `08-settings-full-dark` / `09-settings-full-light` | Settings in full, no scrolling |
| `10-settings-learn` | Unknown dongle: the Diagnostics section with learning mode |
| `11-hotkey-capture` | Waiting for a shortcut — "Press a shortcut…" |
| `12-hotkey-empty` | No shortcut set |
| `13-icons-sheet` / `14-icons-sheet-light` | The device icon palette |
| `15-welcome` / `16-welcome-light` | First-run welcome |
| `17-about-dark` / `18-about-light` | About |
| `19-notify-*` … `24-notify-*` | Switch notifications: the panel as it is (with transparency) and the same panel over a backdrop, `-on-desktop` |

Notifications are drawn by the overlay module itself, so these are exactly the
pixels that appear on screen next to the tray.
