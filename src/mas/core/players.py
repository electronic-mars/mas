"""We decide which player the media keys control, not the Windows arbiter.

Windows hands the media key to the "current session", and it considers current
whoever did something last. Measured on a live machine: with Spotify and a
browser both open, the target hops between them every one to eight seconds, and
two presses in a row land in different programs. There is no way to explain
that to a person.

Here the target is chosen by a rule you can state. A player the person has
nominated wins outright, whatever else is going on. Otherwise the command goes
to whoever is **playing**; if nobody is playing, to whoever we controlled last
time; if that one is gone too, to whoever the system picked. Players that do not
appear in the session list at all (VLC 3.x never shows up there) are served the
old way — by tapping a media key.

Nominating a player also means starting it *instead* of what is going on: the
others get paused first. Without that, a short video in a browser and the music
would simply play on top of each other, which is the very thing the setting is
there to end.

The WinRT work lives in a separate thread with its own COM model: calls from
there are blocking, and in the single-threaded model they are forbidden. Event
subscriptions are deliberately not used: their handlers arrive on foreign
threads, and releasing objects on a foreign thread has already crashed this
program before.
"""
import queue
import threading
import time

from .. import log
from . import media

_log = log.get("players")

# The Windows enumeration: 0 closed, 1 opened, 2 changing, 3 stopped,
# 4 PLAYING, 5 paused. Taken from the library itself
# (`GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING`) rather
# than guessed from observation: four and five sit here in the opposite order
# from the one you expect, and swapping them turns all the logic below inside
# out.
PLAYING = 4
PAUSED = 5

ACTIVE_EVERY_S = 4.0    # how often we refresh the snapshot while a player exists
IDLE_EVERY_S = 12.0     # and when there is none
VERIFY_WAIT_S = 0.9     # total time we wait for the player to obey
VERIFY_STEP_S = 0.03    # and how often we re-ask while waiting


class Track:
    """What to show the person: who we control and what is playing."""

    def __init__(self, app: str = "", title: str = "", artist: str = "", playing: bool = False):
        self.app = app
        self.title = title
        self.artist = artist
        self.playing = playing

    def as_dict(self) -> dict:
        return {"app": self.app, "title": self.title,
                "artist": self.artist, "playing": self.playing}


class Players(threading.Thread):
    def __init__(self, on_track=None, on_dead=None, on_new_app=None):
        super().__init__(daemon=True, name="mas-players")
        self._on_track = on_track      # call when the track or the player changed
        self._on_dead = on_dead        # call when the player does not respond at all
        # Call when a player is seen for the first time. Without it the settings
        # list is whatever existed at the moment the window was opened, and a
        # player that started later never appears in it — the page only refetches
        # the state when it is told the state changed.
        self._on_new_app = on_new_app
        # Player -> the state it froze in. A closed tab leaves a record of
        # itself in the system, and that record stays frozen in "playing"
        # forever: there is nobody left to send commands to. We skip such
        # records when picking a target, otherwise the ghost intercepts every
        # press meant for a live player.
        self._dead: dict[str, int] = {}
        self._jobs: queue.SimpleQueue = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._snap = Track()
        self._last_app: str | None = None
        # Players that answer True and do nothing: Chromium-based browsers
        # behave exactly like that. The list fills itself, from experience.
        self._keys_only: set[str] = set()
        # The player the person nominated. While it has a session, every command
        # goes to it and the rule below is not consulted at all.
        self._priority = ""
        # Every player we have seen, system id -> the name a person calls it by.
        # The settings need a list to choose from, and the chosen one has to keep
        # its name even while it is not running.
        self._seen: dict[str, str] = {}
        self._mgr = None
        self.available = False

    # --- what is called from outside ------------------------------------
    def command(self, action: str) -> None:
        """Pause or skip. Runs on our own thread, we do not wait for an answer."""
        self._jobs.put(("cmd", action))

    def set_priority(self, app_id: str) -> None:
        was = self._priority
        self._priority = app_id or ""
        if self._priority:
            with self._lock:
                self._seen.setdefault(self._priority, self._short(self._priority))
        # Taking the nomination away has to take the habit away with it. When
        # nobody is playing the command goes to whoever we controlled last, and
        # that is the player just un-nominated: it would keep winning by inertia,
        # and from the outside the setting would look as if it had not applied.
        elif was and self._last_app == was:
            self._last_app = None
            _log.info("%s is no longer nominated — forgetting it as the last target",
                      self._short(was))
        _log.info("priority player: %s",
                  self._short(self._priority) if self._priority else "not chosen")

    def known_apps(self) -> list[dict]:
        """For the settings list. The chosen one is always in it, running or not."""
        with self._lock:
            seen = dict(self._seen)
        return [{"id": i, "name": n} for i, n in sorted(seen.items(), key=lambda kv: kv[1])]

    def refresh(self) -> None:
        """Refresh the snapshot: who is playing and what exactly."""
        self._jobs.put(("refresh", None))

    def snapshot(self) -> dict:
        with self._lock:
            return self._snap.as_dict()

    def stop(self) -> None:
        self._jobs.put(("stop", None))

    # --- internals -------------------------------------------------------
    # Tails that system names drag along: without them what is left is the name
    # a person calls the program by.
    _TAILS = ("webbrowser", "browser", "music", "player", "desktop", "app")

    @classmethod
    def _short(cls, app_id: str) -> str:
        """System name into a human one.

        `SpotifyAB.SpotifyMusic_zpd…!Spotify` -> `Spotify`,
        `OperaSoftware.OperaWebBrowser.1779790930` -> `Opera`,
        `chrome.exe` -> `Chrome`.
        """
        name = app_id.split("!")[-1]
        if name.lower().endswith(".exe"):
            name = name[:-4]
        parts = [p for p in name.replace("_", ".").split(".") if p and not p.isdigit()]
        if not parts:
            return app_id
        word = parts[-1]
        low = word.lower()
        for tail in cls._TAILS:
            if low.endswith(tail) and len(low) > len(tail):
                word = word[:-len(tail)]
                break
        return word[:1].upper() + word[1:]

    def _sessions(self):
        return list(self._mgr.get_sessions()) if self._mgr else []

    def _revive(self, sessions) -> None:
        """A frozen player that suddenly changed state is alive again."""
        for s in sessions:
            app = s.source_app_user_model_id
            was = self._dead.get(app)
            if was is not None and int(s.get_playback_info().playback_status) != was:
                del self._dead[app]
                _log.info("%s responds again", self._short(app))

    def _note(self, sessions) -> None:
        """Remember everyone we have seen, so the settings have a list to offer."""
        fresh = []
        with self._lock:
            for s in sessions:
                app = s.source_app_user_model_id
                if app and app not in self._seen:
                    self._seen[app] = self._short(app)
                    fresh.append(self._seen[app])
        if fresh and self._on_new_app:
            _log.info("a player we had not seen before: %s", ", ".join(fresh))
            self._on_new_app()          # outside the lock: it goes off to the window

    def _pick(self, sessions):
        """Who to address the command to. The rule is described in the module header."""
        if not sessions:
            return None
        alive = [s for s in sessions if s.source_app_user_model_id not in self._dead]
        if alive:
            sessions = alive       # pick a ghost only if there is nobody else
        # A nominated player outranks every guess below, including the system's.
        # That is the whole point of nominating one: a video starts in a browser,
        # and without this the next press would land there instead of the music.
        if self._priority:
            for s in sessions:
                if s.source_app_user_model_id == self._priority:
                    return s
        playing = [s for s in sessions
                   if int(s.get_playback_info().playback_status) == PLAYING]
        if playing:
            # If several are playing, stay with the one we controlled last time.
            for s in playing:
                if s.source_app_user_model_id == self._last_app:
                    return s
            return playing[0]
        for s in sessions:
            if s.source_app_user_model_id == self._last_app:
                return s
        cur = self._mgr.get_current_session() if self._mgr else None
        if cur is not None and cur.source_app_user_model_id not in self._dead:
            return cur
        return sessions[0]

    def _read(self, sessions) -> Track:
        self._revive(sessions)
        self._note(sessions)
        target = self._pick(sessions)
        if target is None:
            return Track()
        app = self._short(target.source_app_user_model_id)
        playing = int(target.get_playback_info().playback_status) == PLAYING
        title = artist = ""
        try:
            import asyncio
            props = asyncio.run(target.try_get_media_properties_async())
            title, artist = props.title or "", props.artist or ""
        except Exception:
            pass        # properties can be unavailable — the app name is still there
        return Track(app=app, title=title, artist=artist, playing=playing)

    def _describe(self, sessions) -> str:
        """A line for the log: who is there and what they can do. Without it there
        is nothing to work from when someone reports "the buttons do not affect
        such-and-such player"."""
        out = []
        for s in sessions:
            info = s.get_playback_info()
            ctrl = info.controls
            can = "".join(c for c, ok in (("P", ctrl.is_play_enabled),
                                          ("p", ctrl.is_pause_enabled),
                                          ("→", ctrl.is_next_enabled),
                                          ("←", ctrl.is_previous_enabled)) if ok)
            state = "playing" if int(info.playback_status) == PLAYING else \
                f"not playing ({int(info.playback_status)})"
            if s.source_app_user_model_id in self._dead:
                state += ", not responding"
            out.append(f"{self._short(s.source_app_user_model_id)}"
                       f"[{state}, can do {can or '—'}]")
        return ", ".join(out) or "no sessions"

    def _do(self, action: str) -> None:
        import asyncio

        # Read once, at the top. Both of these are written from the bridge thread
        # when the setting changes, and a change landing halfway through a command
        # used to be able to make us hush the very player we were about to start.
        priority = self._priority

        sessions = self._sessions()
        self._revive(sessions)
        self._note(sessions)
        target = self._pick(sessions)
        _log.info("%s: %s", action, self._describe(sessions))
        if target is None:
            # There is no player the system knows about: we tap the key blindly —
            # that is how, for example, VLC of the third branch works, and any
            # player without support for the system transport controls.
            media.tap(action)
            return
        self._last_app = target.source_app_user_model_id
        who = self._short(self._last_app)
        playing = int(target.get_playback_info().playback_status) == PLAYING

        # Can a media key reach the one we are addressing? It cannot be aimed: it
        # goes to whoever the system calls current. When that is somebody else and
        # we have been told which player matters, pressing it would hit the wrong
        # program — very possibly the one we are about to hush. Deciding this once
        # here, rather than in each fallback, is what keeps the two from
        # disagreeing.
        cur = self._mgr.get_current_session() if self._mgr else None
        key_reaches = not (priority and self._last_app == priority
                           and cur is not None
                           and cur.source_app_user_model_id != priority)

        # A player that lied once is served by the key right away: without this
        # every press would cost an extra second on verification.
        if self._last_app in self._keys_only:
            if not key_reaches:
                self._refuse(who, cur)
                return
            _log.info("%s -> %s: straight to the key, it ignores addressed commands",
                      action, who)
            self._key(action, target, playing, who)
            return

        # Starting the nominated player means starting it *instead*, not as well.
        # The case this exists for: a short video is playing in a browser, the
        # person wants the music. Silencing the others by hand is exactly the
        # chore the setting is meant to remove, so it happens before we start —
        # the other way round they overlap for a moment and it sounds broken.
        hushed = []
        if action == "play" and not playing and self._last_app == priority:
            hushed = self._hush(sessions, priority)

        call = {"play": target.try_pause_async if playing else target.try_play_async,
                "next": target.try_skip_next_async,
                "prev": target.try_skip_previous_async}[action]
        ok = asyncio.run(call())

        # We check by the deed, not by the answer: a player with nobody behind it
        # answers True and does nothing. For skipping, the state does not change
        # in essence — there we trust the answer and do not wait at all.
        moved = self._wait_change(target, playing) if action == "play" else ok
        _log.info("%s -> %s: answer %s, state %s", action, who, ok,
                  "changed" if moved else "unchanged")
        if moved:
            return

        if not key_reaches:
            # Nothing left to try. Whatever we silenced has to come back, or the
            # person is left with no music at all and no explanation — which is a
            # worse outcome than the press simply not working.
            self._resume(hushed)
            self._refuse(who, cur)
            return
        # Only now, with the key actually about to be pressed, is it fair to
        # conclude anything about addressed commands. Recording it before trying
        # the key marked players broken on the strength of an experiment that
        # never happened, and nothing ever cleared that mark.
        self._keys_only.add(self._last_app)
        _log.info("%s does not obey addressed commands, key only from now on", who)
        self._key(action, target, playing, who)

    def _refuse(self, who: str, cur) -> None:
        """Say out loud that we are not going to press anything.

        Silence here is the worst of all outcomes: the person presses, the music
        does not start, nothing is said, and the natural conclusion is that the
        program is broken.
        """
        other = self._short(cur.source_app_user_model_id) if cur is not None else "another player"
        _log.warning("%s does not answer addressed commands, and the media key would "
                     "go to %s instead — not pressing it", who, other)
        if self._on_dead:
            self._on_dead(who)

    def _hush(self, sessions, priority: str) -> list:
        """Pause everyone except the nominated player, and report who was paused.

        Only those actually playing are touched: pausing a paused player is at
        best pointless and at worst wakes a browser tab that had gone quiet on
        its own. We do not wait for them to obey — the person is waiting for
        their music, not for a report on the neighbours — but we do remember
        them, because if the music then fails to start they have to come back.
        """
        import asyncio

        paused = []
        for s in sessions:
            app = s.source_app_user_model_id
            if app == priority or app in self._dead:
                continue
            if int(s.get_playback_info().playback_status) != PLAYING:
                continue
            try:
                asyncio.run(s.try_pause_async())
                paused.append(s)
                _log.info("hushing %s: the nominated player is starting",
                          self._short(app))
            except Exception:
                _log.warning("could not hush %s", self._short(app), exc_info=True)
        return paused

    def _resume(self, sessions) -> None:
        """Undo a hush that turned out to be for nothing."""
        import asyncio

        for s in sessions:
            try:
                asyncio.run(s.try_play_async())
                _log.info("%s back on: the nominated player did not start",
                          self._short(s.source_app_user_model_id))
            except Exception:
                _log.warning("could not bring %s back",
                             self._short(s.source_app_user_model_id), exc_info=True)

    def _wait_change(self, target, playing: bool) -> bool:
        """Wait for the player to obey, and exactly as long as needed.

        There used to be a blind pause of nine tenths of a second here, and every
        press cost that much: three quick presses queued up into two and a half
        seconds. The player responds in a couple of tenths, and reading the state
        costs fractions of a microsecond — we can re-ask freely.
        """
        deadline = time.monotonic() + VERIFY_WAIT_S
        while True:
            if (int(target.get_playback_info().playback_status) == PLAYING) != playing:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(VERIFY_STEP_S)

    def _key(self, action: str, target, playing: bool, who: str) -> None:
        """A media key tap. It cannot be addressed.

        The key goes not to the one we picked, but to the one the system
        considers current. While there is a single player these are the same
        thing; as soon as there are two, the command goes to the neighbour. That
        is why the result has to be read from the current session too — otherwise
        the program sees "state did not change" on an unrelated player and
        declares it unresponsive, having never touched it at all.

        Whether pressing it is acceptable at all is decided by the caller, in one
        place, so that the two fallbacks cannot disagree about it.
        """
        cur = self._mgr.get_current_session() if self._mgr else None
        if cur is not None and cur.source_app_user_model_id != self._last_app:
            who = self._short(cur.source_app_user_model_id)
            target = cur
            playing = int(cur.get_playback_info().playback_status) == PLAYING
            _log.info("the key goes to the system's current player, not ours: %s", who)
        media.tap(action)
        self._check_alive(target, playing, action, who)

    def _check_alive(self, target, playing: bool, action: str, who: str) -> None:
        """No response even to the key — then there is nobody behind the session.

        Windows keeps showing a session after the tab has been closed: the state
        freezes, the properties stay from the previous clip, and there is nobody
        to accept commands. We must not stay silent about it — the person presses
        and does not understand why nothing happens.
        """
        if action != "play":
            return
        app = target.source_app_user_model_id
        if self._wait_change(target, playing):
            self._dead.pop(app, None)
            return
        _log.warning("%s ignores even the key — the tab was probably closed", who)
        first = app not in self._dead
        self._dead[app] = int(target.get_playback_info().playback_status)
        if first and self._on_dead:
            self._on_dead(who)

    def run(self) -> None:
        import asyncio

        import winrt.windows.media.control as ctl
        try:
            self._mgr = asyncio.run(
                ctl.GlobalSystemMediaTransportControlsSessionManager.request_async())
            self.available = True
            _log.info("the player list is available")
            # Look straight away rather than on the next tick. With nothing
            # playing yet the tick is twelve seconds out, and for those twelve
            # seconds the settings offered an empty list of players — which is
            # exactly the window in which a person opens the program they have
            # just started.
            self._jobs.put(("refresh", None))
        except Exception:
            _log.warning("the player list is unavailable, staying on media keys",
                         exc_info=True)
        while True:
            # We wake ourselves up: the tray tooltip must know the track even when
            # the window is closed. While nothing is playing we ask three times
            # less often.
            wait = ACTIVE_EVERY_S if self._snap.app else IDLE_EVERY_S
            try:
                kind, arg = self._jobs.get(timeout=wait)
            except queue.Empty:
                kind, arg = ("refresh", None)
            if kind == "stop":
                break
            try:
                if kind == "cmd" and not self.available:
                    media.tap(arg)
                elif kind == "cmd":
                    self._do(arg)
                elif kind == "refresh" and self.available:
                    snap = self._read(self._sessions())
                    with self._lock:
                        # A pause changes the tooltip too: while the music plays
                        # there is a track there, and once it stops — the device.
                        changed = (snap.app, snap.title, snap.playing) != \
                            (self._snap.app, self._snap.title, self._snap.playing)
                        self._snap = snap
                    if changed and self._on_track:
                        self._on_track()
            except Exception:
                _log.warning("failed to carry out %s", kind, exc_info=True)
                # The key always works, but it cannot be aimed — with a player
                # nominated it could easily hit the wrong one, so we leave it.
                if kind == "cmd" and not self._priority:
                    media.tap(arg)
        self._mgr = None
