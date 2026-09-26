import hashlib, json, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()

def canonical_checksum(payload):
    return sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())

def encrypt_backup(plaintext, key):
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24 or 32 bytes")
    nonce = os.urandom(12)
    return nonce, AESGCM(key).encrypt(nonce, plaintext, None)

def decrypt_backup(nonce, ciphertext, key):
    return AESGCM(key).decrypt(nonce, ciphertext, None)
