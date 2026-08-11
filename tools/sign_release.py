"""Sign the installer and write the description the program reads.

Runs on the build server, after the installer is built and before the release
is created. The private key arrives through the environment from a repository
secret and is never written to disk.

    python tools/sign_release.py <installer> <version> <download-url> [notes-file]

Writes latest.json next to the installer. That file goes onto the release under
exactly that name: the program asks for it by a fixed address that always
points at the newest release.
"""
import json
import os
import sys
from pathlib import Path

SECRET_NAME = "UPDATE_SIGNING_KEY"

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils
except ImportError:
    raise SystemExit("pip install cryptography")


def main() -> int:
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    installer, version, url = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    notes = Path(sys.argv[4]).read_text(encoding="utf-8") if len(sys.argv) > 4 else ""

    pem = os.environ.get(SECRET_NAME, "").strip()
    if not pem:
        raise SystemExit(f"{SECRET_NAME} is not set — nothing would be signed, and a "
                         "release nobody can install is worse than no release")
    private = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    if not isinstance(private, ec.EllipticCurvePrivateKey):
        raise SystemExit("the release key is not an elliptic curve key")

    payload = installer.read_bytes()
    der = private.sign(payload, ec.ECDSA(hashes.SHA256()))
    # Windows wants the two halves laid end to end, not the DER wrapping that
    # everyone else uses. Fixed width, so a short one is padded rather than cut.
    r, s = utils.decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    feed = {
        "version": version.lstrip("v"),
        "notes": notes.strip(),
        "platforms": {
            "windows-x86_64": {"url": url, "signature": raw.hex()},
        },
    }
    out = installer.parent / "latest.json"
    out.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"signed {installer.name} ({len(payload)} bytes) -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
