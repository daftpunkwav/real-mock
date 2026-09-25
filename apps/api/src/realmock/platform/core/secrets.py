"""At-rest encryption for sensitive fields such as API Keys (AES-256-GCM, depends on cryptography).

Design goals:

- Use **AES-256-GCM** for authenticated encryption (AEAD), with a random salt and nonce for every ciphertext;
- Output format ``enc:v2:<b64-salt16>:<b64-nonce12>:<b64-tag16>:<b64-cipher>`` supports future versioning;
- Explicitly raise :class:`LegacySecretFormatError` for old ``enc:v1:`` ciphertext and direct users to resave the Key
  on the Settings page—avoiding silent migration that makes key-handshake failures difficult to diagnose;
- Key source: environment variable ``SECRET_KEY`` (base64 or plaintext string),
  with a random 32-byte Key persisted to ``data/.secret.key`` by default.

.. note::

    This module depends on ``cryptography`` (>= 42.0); the encryption layer uses genuine authenticated encryption
    (GCM), no longer an XOR stream. ``pyproject.toml`` must include cryptography.
"""

from __future__ import annotations

import base64
import logging
import os
import secrets as _secrets
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from realmock.platform.config import PLATFORM_ROOT  # Single source of truth: master key and DB are in the same directory

logger = logging.getLogger(__name__)

# v1 = old XOR + HMAC; v2 = AES-256-GCM
_VERSION_V1 = "enc:v1"
_VERSION_V2 = "enc:v2"

_SALT_BYTES = 16
_NONCE_BYTES = 12  # GCM standard nonce length
_TAG_BYTES = 16
_KEY_BYTES = 32
_KDF_ITERATIONS = 200_000

# The master key is stored alongside DB / uploads: platform/data/.secret.key
_SHARED_DATA = PLATFORM_ROOT / "data"
_DEFAULT_KEYFILE = _SHARED_DATA / ".secret.key"

_MASTER_SALT = b"app-master-v2"

# Minimum master key strength: plain text ≥16 characters, or base64 decoded ≥16 bytes
_MIN_MASTER_KEY_BYTES = 16


def validate_master_key_env() -> str:
    """Validate the strength of ``SECRET_KEY`` and return ``"ok"`` | ``"missing"`` | ``"too_short"``.

    Pure function: does not read or generate any keyfile and does not populate the
    :func:`_master_bytes` cache; shared by the startup gate and runtime safeguards.
    """
    raw = os.environ.get("SECRET_KEY")
    if not raw:
        return "missing"
    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception:
        decoded = b""
    if len(decoded) >= _MIN_MASTER_KEY_BYTES or len(raw) >= _MIN_MASTER_KEY_BYTES:
        return "ok"
    return "too_short"


class LegacySecretFormatError(ValueError):
    """The old encryption format cannot be decrypted, please save the API Key again."""


@lru_cache(maxsize=128)
def _derive_key(master: bytes, salt: bytes) -> bytes:
    """Derive 32-byte AES keys from master + salt per ciphertext.

    PBKDF2 at ``_KDF_ITERATIONS`` costs tens of milliseconds of pure CPU, and
    the same stored ciphertext (API key, GitHub token) is re-decrypted on
    every client build — the derivation is cached per ``(master, salt)`` so
    repeat decryptions of unchanged rows are free. Bounded LRU: encryptions
    mint a fresh salt each time, so entries are per-ciphertext, not
    per-call; the master key is already cached in process memory, so holding
    a bounded set of derived keys adds no new exposure class.
    """
    import hashlib

    return hashlib.pbkdf2_hmac(
        "sha256", master, salt, _KDF_ITERATIONS, dklen=_KEY_BYTES
    )


def _load_secret_bytes() -> bytes:
    """Return the raw master key (≥32 bytes).

    Key strength (≥16 bytes) is validated by :func:`validate_master_key_env`, and the startup
    gate in ``asgi.py:_check_secret_key_policy`` enforces it when ``env=prod``; do not reject it again here, to avoid
    breaking existing deployments that use short keys in dev.
    """
    raw = os.environ.get("SECRET_KEY")
    if raw:
        # Supports both base64 encoding and plain text strings (automatic normalization)
        try:
            decoded = base64.b64decode(raw, validate=True)
            if len(decoded) >= 16:
                # Intentional retention of zero padding rather than KDF derivation: using derivation instead makes the same SECRET_KEY
                # After obtaining different masters, all existing ciphertexts deployed by the existing short keys cannot be decrypted.
                # Zero padding does not increase entropy at a known cost (effective entropy ≥16 bytes, prod gating enforced).
                return decoded.ljust(_KEY_BYTES, b"0")[:_KEY_BYTES]
        except Exception:
            logger.debug("SECRET_KEY is not base64, derived from a plain text string")
        return _derive_key(raw.encode("utf-8"), _MASTER_SALT)

    # persistence fallback
    _SHARED_DATA.mkdir(parents=True, exist_ok=True)
    if _DEFAULT_KEYFILE.exists():
        try:
            return base64.b64decode(_DEFAULT_KEYFILE.read_text().strip())
        except Exception:
            # The unavailability of the old key means that all existing enc: ciphertext cannot be decrypted and must be explicitly exposed
            logger.warning(
                "Key file reading/decoding failed and will be regenerated (existing encrypted data cannot be decrypted)",
                exc_info=True,
            )

    fresh = _secrets.token_bytes(_KEY_BYTES)
    _DEFAULT_KEYFILE.write_text(base64.b64encode(fresh).decode())
    try:
        os.chmod(_DEFAULT_KEYFILE, 0o600)
    except OSError:
        pass
    logger.warning(
        "SECRET_KEY not detected, one-time key generated: %s; please provide environment variables explicitly for production environment",
        _DEFAULT_KEYFILE,
    )
    return fresh


@lru_cache
def _master_bytes() -> bytes:
    """Cache the master key to avoid re-parsing the env/ file every time it is encrypted or decrypted."""
    return _load_secret_bytes()


def _reset_cache() -> None:
    """For testing purposes only: clear both the master-key cache and the derived-key LRU.

    The next encrypt/decrypt reloads the master from env/keyfile and pays the
    PBKDF2 derivation again.
    """
    _master_bytes.cache_clear()
    _derive_key.cache_clear()


def encrypt_secret(plaintext: str | None) -> str | None:
    """Encrypted string; ``None`` / NULL value is returned unchanged."""
    if not plaintext:
        return plaintext
    if plaintext.startswith(f"{_VERSION_V2}:"):
        return plaintext  # Encrypted
    salt = os.urandom(_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    master = _master_bytes()
    key = _derive_key(master, salt)
    cipher_with_tag = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    # GCM output = ciphertext || tag; write format after splitting
    if len(cipher_with_tag) < _TAG_BYTES:
        raise ValueError("AES-GCM output length abnormality")
    ct = cipher_with_tag[:-_TAG_BYTES]
    tag = cipher_with_tag[-_TAG_BYTES:]
    return (
        f"{_VERSION_V2}:"
        f"{base64.b64encode(salt).decode()}:"
        f"{base64.b64encode(nonce).decode()}:"
        f"{base64.b64encode(tag).decode()}:"
        f"{base64.b64encode(ct).decode()}"
    )


def decrypt_secret(value: str | None) -> str | None:
    """Decrypt; on failure, raise :class:`ValueError` or :class:`LegacySecretFormatError`."""
    if not value:
        return value
    if value.startswith(f"{_VERSION_V1}:"):
        # Old formats cannot be decrypted backwards-compatible—avoid silent migration misidentification key errors.
        raise LegacySecretFormatError(
            "An old version (enc:v1) encrypted API Key was detected. Please go to the \"Settings\" page to save it again."
        )
    if not value.startswith(f"{_VERSION_V2}:"):
        # Unencrypted plain text: migration period or development environment compatibility.
        return value
    parts = value.split(":", 5)
    if len(parts) != 6:
        raise ValueError("Encrypted string format error")
    _, _, salt_b64, nonce_b64, tag_b64, ct_b64 = parts
    try:
        salt = base64.b64decode(salt_b64)
        nonce = base64.b64decode(nonce_b64)
        tag = base64.b64decode(tag_b64)
        ct = base64.b64decode(ct_b64)
    except Exception as exc:
        raise ValueError("Encrypted string base64 parsing failed") from exc
    master = _master_bytes()
    key = _derive_key(master, salt)
    try:
        plain_bytes = AESGCM(key).decrypt(nonce, ct + tag, None)
    except Exception as exc:
        raise ValueError("AES-GCM decryption or authentication failed: the key may have been changed or the data has been tampered with") from exc
    return plain_bytes.decode("utf-8")


__all__ = [
    "LegacySecretFormatError",
    "encrypt_secret",
    "decrypt_secret",
    "validate_master_key_env",
    "_reset_cache",
    "_master_bytes",
    "_VERSION_V2",
]
