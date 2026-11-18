"""Ed25519 identity of the gateway. The private key never leaves the device."""
import base64
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KEY_FILE = 'gateway_ed25519.key'


def load_or_create(data_dir):
    path = os.path.join(data_dir, KEY_FILE)
    if os.path.exists(path):
        with open(path, 'rb') as fh:
            return Ed25519PrivateKey.from_private_bytes(base64.b64decode(fh.read()))
    os.makedirs(data_dir, mode=0o700, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                            serialization.NoEncryption())
    # Create with 0600 atomically: there is no window where it is world-readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as fh:
        fh.write(base64.b64encode(raw))
    return key


def public_b64(key):
    return base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
