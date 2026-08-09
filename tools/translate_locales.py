"""Fill in the locale files with a machine translation, English as the source.

    set DEEPSEEK_API_KEY=...
    python tools/translate_locales.py            # only what is missing
    python tools/translate_locales.py --all      # everything, overwriting
    python tools/translate_locales.py --only de,pl

Only the missing keys are sent, not the whole file. That is the difference from
how this was done in the previous project, and it is the important one: there the
entire locale went into one request, and once it grew past the model's answer
limit the reply came back as truncated JSON that would not parse. Four languages
never finished at all because their translations run longer than the English
source. Sending the difference keeps every request small, makes a re-run cheap,
and turns adding one string into a two-second job instead of a full re-translation.

Nothing is written until the answer has been parsed, checked key by key, and put
through a temporary file: a half-received reply must not overwrite a good locale.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "src" / "mas" / "ui" / "locales"
SOURCE = "en"

API = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
CHUNK = 30              # keys per request: small enough that no answer is cut off
ATTEMPTS = 3
TIMEOUT_S = 240

# Названия на самом языке: в списке выбора человек ищет своё слово, а не наше.
LANGUAGES = {
    "de": "Deutsch", "es": "Español", "fr": "Français", "it": "Italiano",
    "pt": "Português", "pl": "Polski", "cs": "Čeština", "nl": "Nederlands",
    "tr": "Türkçe", "zh": "中文", "ja": "日本語", "ko": "한국어",
}
# What the model must be told to call each language, in English.
ENGLISH_NAMES = {
    "de": "German", "es": "Spanish", "fr": "French", "it": "Italian",
    "pt": "Portuguese (Brazilian usage)", "pl": "Polish", "cs": "Czech",
    "nl": "Dutch", "tr": "Turkish", "zh": "Simplified Chinese",
    "ja": "Japanese", "ko": "Korean",
}
# Hand-written and never machine-translated.
HAND_WRITTEN = ("en", "ru", "uk")

# Names that must survive untouched. Product names, and the words Windows itself
# uses — a person looks for those exact words in the system settings.
KEEP = ("Master Audio Switcher", "Windows", "WebView2", "GitHub", "Spotify",
        "Discord", "Zoom", "Teams", "HyperX Cloud Flight S", "Powerbeats Pro",
        "Realtek", "HDMI", "USB", "Bluetooth", "Ctrl", "Alt", "Shift", "Win")

# Keys whose text sits in a tight place: a tab, a button, a segment, a caption on
# the panel. A translation twice the length of the English does not wrap there,
# it is simply cut off.
TIGHT = {
    "tab_devices": 12, "tab_mixer": 12, "tab_settings": 14, "tab_about": 16,
    "lcd_level": 10, "lcd_signal": 10, "btn_left": 10, "btn_right": 10,
    "theme_system": 16, "theme_dark": 10, "theme_light": 10,
    "hk_none": 16, "hk_clear": 10, "open_btn": 12, "welcome_ok": 14,
    "player_none": 18, "muted": 12,
}


# By name, in this order. Never "whichever line mentions KEY": a file like that
# also holds keys for other services, and sending one of those here costs a
# confusing 401 and, worse, hands a key to a service it does not belong to.
KEY_NAMES = ("DEEPSEEK_API_KEY", "OPENAI_COMPATIBLE_API_KEY")


def load_key(explicit: str | None) -> str:
    if explicit:
        found = {}
        for line in Path(explicit).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                name, _, value = line.partition("=")
                found[name.strip().upper()] = value.strip().strip('"').strip("'")
        for name in KEY_NAMES:
            if found.get(name):
                print(f"key taken from {name}")
                return found[name]
        raise SystemExit(f"{explicit} holds none of {', '.join(KEY_NAMES)}")
    for name in KEY_NAMES:
        if os.environ.get(name):
            return os.environ[name]
    raise SystemExit(f"Set {KEY_NAMES[0]}, or pass --key-file. "
                     "The key is never written into this repository.")


def ask(key: str, prompt: str) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system",
             "content": "You are a professional software localizer. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
        answer = json.loads(res.read())
    return json.loads(answer["choices"][0]["message"]["content"])


def prompt_for(code: str, part: dict, source: dict) -> str:
    limits = "\n".join(f'  "{k}": at most {TIGHT[k]} characters' for k in part if k in TIGHT)
    return (
        f"Translate the VALUES of this JSON object into {ENGLISH_NAMES[code]}.\n"
        "This is the interface of a small Windows utility that switches sound "
        "between speakers and headphones from the tray.\n\n"
        "Rules:\n"
        "- Keep every KEY exactly as it is. Return the same set of keys.\n"
        "- Keep the placeholder %s exactly where it is; it is replaced with a device name.\n"
        f"- Do not translate these names: {', '.join(KEEP)}.\n"
        "- Use the wording Windows itself uses in that language for system terms "
        "(tray, sign in, default device, microphone, shortcut).\n"
        "- Address the person directly and informally, the way a small utility "
        "talks. Short and plain, no marketing, no exclamation marks.\n"
        "- A description explains why the setting matters; do not turn it into a "
        "literal word-for-word rendering if that reads unnatural.\n"
        + (f"- These must fit in a narrow control:\n{limits}\n" if limits else "")
        + "\nReturn ONLY the JSON object.\n\n"
        + json.dumps(part, ensure_ascii=False, indent=1)
    )


def translate(key: str, code: str, missing: dict, source: dict) -> dict:
    done: dict[str, str] = {}
    items = list(missing.items())
    for start in range(0, len(items), CHUNK):
        part = dict(items[start:start + CHUNK])
        for attempt in range(1, ATTEMPTS + 1):
            try:
                got = ask(key, prompt_for(code, part, source))
                absent = [k for k in part if not isinstance(got.get(k), str) or not got[k].strip()]
                if absent:
                    raise ValueError(f"answer is missing keys: {absent[:5]}")
                done.update({k: got[k].strip() for k in part})
                break
            except Exception as e:
                where = f"{code} {start + 1}-{start + len(part)}"
                if attempt == ATTEMPTS:
                    print(f"  {where}: giving up — {e}")
                else:
                    print(f"  {where}: attempt {attempt} failed ({e}), retrying")
                    time.sleep(2 * attempt)
        time.sleep(1)
    return done


def write_locale(code: str, strings: dict, untranslated: list) -> None:
    """Through a temporary file, and only after it has been read back."""
    doc = {"code": code, "name": LANGUAGES.get(code, code)}
    # Keys that fell back to English are named, not silently baked in. Without
    # this list the English value looks like a finished translation: the next run
    # sees a non-empty string, calls the language complete, and never tries
    # again — which is how the previous project ended up with English text sitting
    # in fifteen locales with nothing to show which.
    if untranslated:
        doc["untranslated"] = sorted(untranslated)
    doc["strings"] = strings
    tmp = LOCALES / f".{code}.json.new"
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))      # would raise before we replace
    tmp.replace(LOCALES / f"{code}.json")


def rebuild_index() -> None:
    """The dropdown is built from the folder, so adding a language is dropping a
    file in. English first, then the rest by their own name."""
    items = []
    for path in sorted(LOCALES.glob("*.json")):
        if path.name == "index.json":
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        items.append({"code": doc["code"], "name": doc["name"]})
    items.sort(key=lambda i: (i["code"] != "en", i["name"]))
    (LOCALES / "index.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("index.json:", ", ".join(i["code"] for i in items))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="re-translate everything")
    ap.add_argument("--only", default="", help="comma separated language codes")
    ap.add_argument("--key-file", default=None, help="file holding the API key")
    ap.add_argument("--index-only", action="store_true", help="just rebuild index.json")
    args = ap.parse_args()

    if args.index_only:
        rebuild_index()
        return 0

    source = json.loads((LOCALES / f"{SOURCE}.json").read_text(encoding="utf-8"))["strings"]
    codes = [c.strip() for c in args.only.split(",") if c.strip()] or list(LANGUAGES)
    unknown = [c for c in codes if c not in LANGUAGES]
    if unknown:
        raise SystemExit(f"unknown languages: {unknown}")

    key = load_key(args.key_file)
    trouble: list[str] = []
    for code in codes:
        path = LOCALES / f"{code}.json"
        have, failed_before = {}, set()
        if path.is_file() and not args.all:
            doc = json.loads(path.read_text(encoding="utf-8"))
            have = doc.get("strings", {})
            failed_before = set(doc.get("untranslated", []))
        missing = {k: v for k, v in source.items()
                   if k not in have or not have[k].strip() or k in failed_before}
        stale = [k for k in have if k not in source]
        if not missing and not stale:
            print(f"{code}: already complete ({len(have)} strings)")
            continue
        print(f"{code}: {len(missing)} to translate, {len(stale)} no longer used")
        got = translate(key, code, missing, source) if missing else {}
        merged = {k: got.get(k, have.get(k, "")) for k in source}
        blank = [k for k, v in merged.items() if not v]
        if blank:
            print(f"  {code}: {len(blank)} left untranslated, English stays "
                  f"and will be retried next run: {blank[:5]}")
            for k in blank:
                merged[k] = source[k]
            trouble.append(code)
        write_locale(code, merged, blank)
        print(f"  {code}: written, {len(merged)} strings")

    rebuild_index()
    if trouble:
        # Loudly, and with a non-zero code: a half-translated language that
        # reports success is how this goes unnoticed for months.
        print("\nincomplete: " + ", ".join(trouble))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
