"""Make the pair of keys that decides who may publish an update.

Run once, on a machine you trust, and never again unless the private half is
lost or leaked. The private half signs releases and lives only in the
repository's secrets; the public half is compiled into the program, and it is
what makes an update from anybody else impossible to install.

    pip install cryptography
    python tools/make_update_key.py

It prints the line to paste into src/mas/core/update.py and writes the private
key to a file the repository ignores. Put that file's contents into the
repository secret named below, then delete it.

Losing the private key is not fatal — a new pair goes out with the next release
and everyone updates once by hand. Leaking it is: whoever has it can hand a
running program on someone else's machine any executable they like.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAME = "UPDATE_SIGNING_KEY"
PRIVATE_FILE = ROOT / ".update-signing-key.pem"

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:
    raise SystemExit("pip install cryptography")

if PRIVATE_FILE.exists():
    raise SystemExit(f"{PRIVATE_FILE.name} is already here. Delete it on purpose "
                     "if you really mean to replace the release key.")

private = ec.generate_private_key(ec.SECP256R1())
numbers = private.public_key().public_numbers()
public = numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")

PRIVATE_FILE.write_bytes(private.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption()))

hexed = public.hex()
print("Paste this into PUBLIC_KEY in src/mas/core/update.py:\n")
print(f'    "{hexed[:64]}"')
print(f'    "{hexed[64:]}")')
print(f"\nThe private key is in {PRIVATE_FILE.name} (the repository ignores it).")
print(f"Put its whole contents into the repository secret {SECRET_NAME}:")
print(f"    gh secret set {SECRET_NAME} < {PRIVATE_FILE.name}")
print("Then delete the file. It is not needed again on this machine.")
sys.exit(0)
