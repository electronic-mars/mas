# Privacy

Master Audio Switcher collects nothing, sends nothing, and has no accounts.

This is short because there is little to say — but the details matter more than
the promise, so here they are.

## What stays on your computer

- **Settings** — which devices are in the switching cycle, their icons, your
  shortcuts, the chosen language and theme. In
  `%LOCALAPPDATA%\MasterAudioSwitcher\config.json`.
- **A log**, kept so that a problem can be explained rather than guessed at. It
  records device names, which device the sound was moved to, and, while the
  media keys are in use, **the name of the track that is playing**. Keep that in
  mind before attaching a log to a bug report — you can delete lines first.
- **Dongle reports**, only if you use the learning mode for a wireless headset,
  and only in a file you can read yourself.

Nothing in that folder leaves it. Deleting the folder resets the program to a
fresh install; the uninstaller offers to do it for you.

## What leaves your computer

Two things, both only when you press something:

- **Check for updates** opens the releases page of the project in your browser.
- **Support development** and **GitHub** open their pages in your browser.

That is all. There is no telemetry, no usage statistics, no crash reporting, no
automatic update, no license check, and no analytics of any kind. The program
does not ask who you are and has nowhere to send it if it did.

## What the program reads on your computer

To do its job it asks Windows for:

- the list of audio devices, and which one is the default;
- the volume level of the system and of programs that are playing sound, which
  means it also sees **the names of those programs** — that is what the mixer
  shows;
- what the media players report about themselves: the program name, the track,
  and whether it is playing;
- the status report of a wireless headset's USB receiver, read-only.

All of it is read to draw the window and switch the sound, and none of it is
stored beyond the log described above.

## The local connection

The window is a page, and it talks to the program over a local HTTP server bound
to `127.0.0.1` on a random port, protected by a random token generated at every
start. It is not reachable from the network, and it accepts nothing without that
token.

## Questions

Anything unclear or anything that looks wrong: open an issue at
https://github.com/electronic-mars/mas/issues
