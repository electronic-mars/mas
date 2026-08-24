"""Updating from the release page, checked against a key inside the program.

The program downloads an executable and runs it. That is a serious thing to do
on someone else's machine, and it is only defensible if the file can be proved
to be ours. A checksum published next to the file proves nothing: whoever can
serve a false installer serves a false checksum with it. So the release carries
a signature made by a key that exists in one place — the build server's secrets
— and the program carries only the public half, compiled into it. Nobody who
does not hold the private key can produce an update this program will run, no
matter what they manage to put in front of it.

The checking is done by Windows, through its own CNG. It costs no dependency,
and it means no cryptography is written here — only calls into an
implementation whose correctness is somebody's job.

Nothing here runs by itself. The check happens when a person presses the button.
"""
import ctypes
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .. import log
from ..paths import data_dir

_log = log.get("update")

bcrypt = ctypes.WinDLL("bcrypt")
k32 = ctypes.WinDLL("kernel32")

# The public half of the release key. The private half never leaves the build
# server's secrets. Replacing this constant is what changes who is allowed to
# publish an update — see tools/make_update_key.py.
PUBLIC_KEY = bytes.fromhex(
    "bfe40bea68546228719e6ce386b051232a8f2a2d27fa2ce51493276cabcf9d07"
    "f0aea21dd8def972e74b32691537e65ba349133706fb7d06678a361004c8abc9")

FEED = "https://github.com/electronic-mars/mas/releases/latest/download/latest.json"
# Where a download is allowed to come from. The signature already makes a
# substitution useless, but there is no reason to fetch from anywhere else, and
# a feed that points somewhere strange is worth refusing outright rather than
# after ten megabytes.
ALLOWED_HOSTS = ("github.com", "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com")
TIMEOUT_S = 30
CHUNK = 64 * 1024
# Room for the program to grow several times over, and far below anything that
# would fill a disk. A feed claiming more than this is not describing our
# installer.
MAX_BYTES = 200 * 1024 * 1024

BCRYPT_ECDSA_P256_ALGORITHM = "ECDSA_P256"
# The macro is spelled with underscores; the string it stands for is not.
BCRYPT_ECCPUBLIC_BLOB = "ECCPUBLICBLOB"
BCRYPT_ECDSA_PUBLIC_P256_MAGIC = 0x31534345
STATUS_SUCCESS = 0
APPMODEL_ERROR_NO_PACKAGE = 15700


def from_store() -> bool:
    """Was this copy installed from the Microsoft Store?

    Then updating is the Store's job, it does it quietly and better, and doing
    it ourselves is against its rules besides. One program, one build — it just
    asks Windows which of the two lives it is living.
    """
    length = ctypes.c_uint32(0)
    code = k32.GetCurrentPackageFullName(ctypes.byref(length), None)
    return code != APPMODEL_ERROR_NO_PACKAGE


def as_numbers(version: str) -> tuple:
    """"1.2.10" -> (1, 2, 10). Leading v and anything after the numbers go."""
    found = re.findall(r"\d+", version or "")
    return tuple(int(x) for x in found[:3]) or (0,)


def is_newer(offered: str, current: str) -> bool:
    return as_numbers(offered) > as_numbers(current)


def _allow(url: str) -> str:
    where = urlparse(url)
    if where.scheme != "https":
        raise ValueError("updates are only fetched over https")
    if where.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"{where.hostname} is not a host we fetch updates from")
    return url


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Every hop gets the same test as the first one.

    The address we ask for is checked, and then GitHub answers with a redirect
    to its own file store — which is why that store is on the list. But a
    redirect is somebody else's instruction, and following it unexamined would
    make the check on the first address decorative. The signature would still
    catch a substituted file; this is about not going there at all.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _allow(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_fetch = urllib.request.build_opener(_CheckedRedirects)


def _open(url: str):
    return _fetch.open(_allow(url), timeout=TIMEOUT_S)


def latest() -> dict:
    """What the release page offers. Raises when it cannot be read."""
    with _open(FEED) as answer:
        feed = json.loads(answer.read(256 * 1024).decode("utf-8"))
    windows = (feed.get("platforms") or {}).get("windows-x86_64") or {}
    url, signature = windows.get("url", ""), windows.get("signature", "")
    if not feed.get("version") or not url or not signature:
        raise ValueError("the release description is incomplete")
    if urlparse(url).hostname not in ALLOWED_HOSTS:
        raise ValueError(f"the release points at {urlparse(url).hostname}")
    return {"version": str(feed["version"]), "notes": str(feed.get("notes", "")),
            "url": url, "signature": signature}


def verify(path: Path, signature: bytes) -> bool:
    """Is this file the one our key signed? Windows answers, not us."""
    if len(PUBLIC_KEY) != 64 or not any(PUBLIC_KEY):
        _log.error("this build carries no release key — nothing can be verified")
        return False
    if len(signature) != 64:
        _log.warning("the signature is %d bytes, not 64", len(signature))
        return False

    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    digest = digest.digest()

    alg = ctypes.c_void_p()
    if bcrypt.BCryptOpenAlgorithmProvider(
            ctypes.byref(alg), BCRYPT_ECDSA_P256_ALGORITHM, None, 0) != STATUS_SUCCESS:
        _log.error("this Windows has no ECDSA P-256 to check the signature with")
        return False
    try:
        blob = (BCRYPT_ECDSA_PUBLIC_P256_MAGIC.to_bytes(4, "little")
                + (32).to_bytes(4, "little") + PUBLIC_KEY)
        key = ctypes.c_void_p()
        status = bcrypt.BCryptImportKeyPair(
            alg, None, BCRYPT_ECCPUBLIC_BLOB, ctypes.byref(key),
            ctypes.create_string_buffer(blob), len(blob), 0)
        if status != STATUS_SUCCESS:
            _log.error("the release key was refused: 0x%08X", status & 0xFFFFFFFF)
            return False
        try:
            return bcrypt.BCryptVerifySignature(
                key, None, ctypes.create_string_buffer(digest), len(digest),
                ctypes.create_string_buffer(signature), len(signature),
                0) == STATUS_SUCCESS
        finally:
            bcrypt.BCryptDestroyKey(key)
    finally:
        bcrypt.BCryptCloseAlgorithmProvider(alg, 0)


def folder() -> Path:
    """Downloads land beside the settings, never in the program's own folder —
    that folder is what the installer is about to replace."""
    d = data_dir() / "update"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download(url: str, on_progress=None) -> Path:
    """Fetch the installer, reporting how far along it is. Returns the file."""
    # One fixed name, never one taken from the address. A name that arrives from
    # outside is a name somebody else chose, and we would be choosing where to
    # write from it; there is also only ever one of these, so a fresh download
    # replacing the last is exactly right.
    target = folder() / "update-setup.exe"
    with _open(url) as answer:
        total = int(answer.headers.get("Content-Length") or 0)
        if total > MAX_BYTES:
            raise ValueError(f"the installer is {total} bytes, which is not credible")
        got = 0
        # Written under another name and renamed at the end: a download cut off
        # halfway must not leave something that looks like a finished installer.
        part = target.with_suffix(target.suffix + ".part")
        with open(part, "wb") as f:
            while True:
                block = answer.read(CHUNK)
                if not block:
                    break
                got += len(block)
                if got > MAX_BYTES:
                    raise ValueError("the download outgrew what was promised")
                f.write(block)
                if on_progress:
                    on_progress(got, total)
    part.replace(target)
    _log.info("downloaded %s, %d bytes", target.name, got)
    return target


def install(path: Path) -> None:
    """Hand over to the installer and get out of its way.

    Silent, because the person already said yes by pressing the button, and
    being asked the same questions again is not a second decision. It puts the
    program back up itself: the flag is ours, and the installer only acts on it
    when it was started this way.
    """
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                      "/NOCANCEL", "/RELAUNCH=1"], close_fds=True)
    _log.info("the installer is running, this copy is stepping aside")
