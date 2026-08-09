# Security

If you find something that could put people at risk, please report it privately
first: **Security → Report a vulnerability** on this repository, which opens a
private advisory only the maintainer can see. Please do not open a public issue
for it.

Say what you found, how to reproduce it, and what an attacker would get. You
will get an answer within a few days; this is one person working in their own
time, so a fix may take longer than the reply.

## What is worth looking at

- **The local bridge** (`src/mas/bridge.py`). The window is a page, and it talks
  to the program over HTTP bound to `127.0.0.1` on a random port, with a random
  token generated at every start, an `Origin` check, and a path guard on the
  files it serves. Anything that gets past those matters.
- **The autostart entry** and the installer, both of which write to `HKCU` and
  to `%LOCALAPPDATA%` — a path that another program could tamper with is worth
  reporting.
- **The dongle reader** (`src/mas/core/dongle.py`), which opens HID devices. It
  only ever reads, and it must stay that way.

## What is known and deliberate

- **The program is not code-signed.** SmartScreen warns about it. Checksums are
  published with every release and the binaries are built in public from a
  tagged commit — that is the verification available today.
- **The log records the names of tracks that are playing.** It stays on the
  machine, and this is stated in [PRIVACY.md](PRIVACY.md), but it is worth
  knowing before attaching a log to a bug report.
- **There is no auto-update.** A fix reaches people only when they download it,
  which is a real limitation and a deliberate one — see
  [docs/RELEASING.md](docs/RELEASING.md).

## Supported versions

The latest release. There is no back-porting.
