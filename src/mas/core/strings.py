"""The words Python says, in the language the person chose.

Everything drawn in the window takes its text from the page, which loads a
locale file itself. But the tray menu, the notifications and the one dialog we
ever show are put on screen by Python, and they used to be English for everyone —
in a program that advertises fifteen languages, with the tray being the surface
people actually use.

The same locale files serve both. English is kept loaded as the fallback, so a
key a translation is missing shows English rather than a key name.
"""
import json

from .. import log
from ..paths import ui_dir

_log = log.get("strings")

FALLBACK = "en"
_tables: dict[str, dict] = {}
_current = FALLBACK


def _load(code: str) -> dict:
    if code in _tables:
        return _tables[code]
    try:
        doc = json.loads((ui_dir() / "locales" / f"{code}.json").read_text(encoding="utf-8"))
        _tables[code] = doc.get("strings", {})
    except Exception:
        # Not fatal: a missing file means English, and English missing means the
        # key name, which is ugly but still tells you what broke.
        _log.warning("locale %s is unreadable", code, exc_info=True)
        _tables[code] = {}
    return _tables[code]


def use(code: str) -> None:
    """Switch language. Called at startup and whenever the setting changes."""
    global _current
    _load(FALLBACK)
    _current = code if code and _load(code) else FALLBACK


# What Windows calls an endpoint, in English, mapped to our own words: an
# English Windows would otherwise say "Headphones" in a Russian program. Names
# Windows already gives in another language are shown as they are.
_PURPOSES = {"headphones": "p_headphones", "headset earphone": "p_headphones",
             "speakers": "p_speakers", "headset": "p_headset",
             "microphone": "p_microphone", "headset microphone": "p_headset_mic",
             "microphone array": "p_mic_array"}


def purpose(word: str) -> str:
    key = _PURPOSES.get(word.lower().strip())
    return t(key) if key else word


def t(key: str, *args) -> str:
    text = _load(_current).get(key) or _load(FALLBACK).get(key) or key
    return text % args if args else text
