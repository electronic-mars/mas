"""Which language to open in on the very first run.

Windows knows what language the person reads — asking it is better than showing
everyone the language the author happens to write in, and better than an opening
dialog nobody wants to answer. The choice is written into the settings once, so
that afterwards it belongs to the person and not to the system.
"""
import ctypes
import json

from .. import log
from ..paths import ui_dir

_log = log.get("language")


def available() -> dict[str, str]:
    """Codes we actually ship, from the locale folder itself."""
    try:
        index = json.loads((ui_dir() / "locales" / "index.json").read_text(encoding="utf-8"))
        return {item["code"]: item["name"] for item in index}
    except Exception:
        _log.warning("the list of languages is unreadable", exc_info=True)
        return {"en": "English"}


def windows_language() -> str:
    """The primary language of the Windows interface: 'de', 'pt', 'zh'…

    GetUserDefaultUILanguage returns the language of Windows itself, which is
    what a person reads, rather than the regional format settings — those follow
    where you live and say nothing about the language you want to read in.
    """
    try:
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        buf = ctypes.create_unicode_buffer(85)
        # LOCALE_SNAME gives a tag like "pt-BR"; the part before the dash is the
        # language, and that is all we keep.
        if ctypes.windll.kernel32.LCIDToLocaleName(langid, buf, 85, 0):
            return buf.value.split("-")[0].lower()
    except Exception:
        _log.warning("could not ask Windows for its language", exc_info=True)
    return ""


def pick() -> str:
    """A language we ship, matching Windows if we can, otherwise English."""
    have = available()
    wanted = windows_language()
    if wanted in have:
        _log.info("first run: Windows speaks %s, taking it", wanted)
        return wanted
    _log.info("first run: Windows speaks %s, which we do not have — English",
              wanted or "an unknown language")
    return "en" if "en" in have else next(iter(have), "en")
