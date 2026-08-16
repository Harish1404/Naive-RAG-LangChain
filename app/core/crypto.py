"""
Symmetric encryption for third-party credentials we have to keep usable.

This is deliberately *not* the same tool as `hash_token` in app/core/security.py,
and the difference is worth stating once:

    hash_token   one-way. Used for refresh tokens, which we only ever COMPARE.
                 A leak of the database yields nothing usable.
    encrypt      reversible. Used for OAuth access tokens, which we have to SEND
                 to GitHub as a bearer credential. A hash cannot be sent, so
                 hashing is not an option here no matter how much we would
                 prefer it.

Reversible means the ciphertext is only as safe as the key, so the key lives in
`.env` (CONNECTOR_ENC_KEY) and never in the database next to what it protects.

AES-256-GCM is authenticated encryption: `decrypt` raises on any tampering
rather than returning corrupted plaintext, so a modified `token_ciphertext`
fails loudly instead of producing a garbage bearer token and a confusing 401
from GitHub.
"""

import base64
import logging
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

logger = logging.getLogger(__name__)

# Stored on each encrypted document so the key can be rotated later without
# guessing which key a given ciphertext was written with.
KEY_VERSION = 1

# 96 bits is the size AES-GCM is specified for; a fresh one per encryption.
_NONCE_BYTES = 12

_KEY_BYTES = 32  # AES-256

# Warned rather than raised, matching app/core/security.py: a missing key must
# not stop the whole app from booting, it must stop *connectors* from working.
if not settings.connector_enc_key:
    logger.warning(
        "CONNECTOR_ENC_KEY is not set — connecting a provider will fail. "
        "Generate one with: python -c \"import base64,os; "
        "print(base64.b64encode(os.urandom(32)).decode())\""
    )


class CryptoError(Exception):
    """Raised when the key is unusable or a ciphertext fails to authenticate."""


def _key() -> bytes:
    """The configured key, validated. Raises rather than defaulting."""
    raw = settings.connector_enc_key
    if not raw:
        raise CryptoError(
            "CONNECTOR_ENC_KEY is not set; refusing to store a credential in plaintext"
        )

    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as e:
        raise CryptoError("CONNECTOR_ENC_KEY is not valid base64") from e

    if len(key) != _KEY_BYTES:
        raise CryptoError(
            f"CONNECTOR_ENC_KEY must decode to {_KEY_BYTES} bytes, got {len(key)}"
        )

    return key


def encrypt(plaintext: str) -> str:
    """
    Encrypt a credential for storage. Returns base64 of `nonce || ciphertext`.

    The nonce is generated per call and carried with the ciphertext rather than
    stored separately — it is not a secret, and reusing one under the same key
    would break GCM's security outright.
    """
    if not isinstance(plaintext, str) or not plaintext:
        raise CryptoError("Refusing to encrypt an empty value")

    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(stored: str) -> str:
    """
    Reverse `encrypt`. Raises CryptoError if the value was tampered with, was
    written under a different key, or is not a value we produced.
    """
    if not stored:
        raise CryptoError("Nothing to decrypt")

    try:
        blob = base64.b64decode(stored, validate=True)
    except Exception as e:
        raise CryptoError("Stored credential is not valid base64") from e

    if len(blob) <= _NONCE_BYTES:
        raise CryptoError("Stored credential is too short to contain a nonce")

    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]

    try:
        return AESGCM(_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
    except InvalidTag as e:
        # Wrong key or modified bytes — indistinguishable by design, and both
        # mean the same thing to the caller: this credential cannot be trusted.
        raise CryptoError(
            "Stored credential failed authentication (wrong key or tampered)"
        ) from e
