"""Is the engine our window is drawn with actually present.

The interface is a page, and pywebview draws it with the WebView2 runtime — the
Chromium that comes with Edge. When that runtime is missing, pywebview does not
say so: it quietly falls back to the Internet Explorer engine, where a page
written with ES modules, async/await and pointer events renders as an empty
rectangle. The person gets a window with a title bar and nothing inside, and the
log says only that the bridge is silent.

Windows 11 ships the runtime, so this is not visible here. Windows 10 does not
always: LTSC and N editions, freshly imaged machines and stripped-down builds
come without it.

Microsoft publishes the runtime's presence in the registry under a fixed client
id, and that is the check they document. We read it rather than try to start the
engine, because by the time starting fails the window already exists.
"""
import winreg

from .. import log

_log = log.get("runtime")

# The Evergreen WebView2 Runtime, as registered by Edge Update.
CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
EDGE_UPDATE = r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
# Machine-wide installs land in the 32-bit view even on 64-bit Windows, which is
# why the plain path is not enough; per-user installs live under HKCU.
PLACES = (
    (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{CLIENT}"),
    (winreg.HKEY_LOCAL_MACHINE, rf"{EDGE_UPDATE}\{CLIENT}"),
    (winreg.HKEY_CURRENT_USER, rf"{EDGE_UPDATE}\{CLIENT}"),
)

DOWNLOAD_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"


def webview2_version() -> str | None:
    """The installed runtime version, or None if there is none.

    An empty version or 0.0.0.0 means the entry is left over from an install
    that was removed — Edge Update keeps the key and blanks the value.
    """
    for root, path in PLACES:
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return str(version)
    return None
