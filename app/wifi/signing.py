"""Cloud signing key (used for offline licenses in Phase 8).

The PRIVATE key lives only in the server environment (UWZ_LICENSE_SIGNING_KEY,
base64 of the 32-byte Ed25519 seed). Gateways receive the PUBLIC key only.
In production a missing key is an error; in dev/test an ephemeral key is used.
"""
import base64
import os

from flask import current_app
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ENV_VAR = 'UWZ_LICENSE_SIGNING_KEY'
_ephemeral = {}


class SigningKeyMissing(RuntimeError):
    pass


def _private_key():
    raw = os.environ.get(ENV_VAR)
    if raw:
        try:
            return Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw))
        except Exception as e:
            raise SigningKeyMissing(f'{ENV_VAR} is invalid: {e}')
    if current_app.testing or current_app.debug:
        return _ephemeral.setdefault('k', Ed25519PrivateKey.generate())
    raise SigningKeyMissing(f'{ENV_VAR} is not configured')


def cloud_public_key_b64():
    pub = _private_key().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(pub).decode()


def sign_bytes(data: bytes) -> bytes:
    """Ed25519 signature with the cloud's PRIVATE key (never leaves the server)."""
    return _private_key().sign(data)
