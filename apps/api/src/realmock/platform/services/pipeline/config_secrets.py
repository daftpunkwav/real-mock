"""Helpers for pipeline configuration secrets and extras JSON (leaf module).

- Encryption semantics for the ``enc:`` prefix (``SECRET_KEEP`` means retaining the current value);
- Redaction of extras in responses (``public_extras``) and runtime decryption (``runtime_extras``).
"""

from __future__ import annotations

import json
from typing import Any

from realmock.platform.core.secrets import decrypt_secret, encrypt_secret

SECRET_KEEP = "keep"
SECRET_EXTRA_KEYS = frozenset({"asr_api_secret", "asr_access_key", "asr_app_key"})


def maybe_encrypt(value: str | None, current: str) -> str:
    if value is None or value == "" or value == SECRET_KEEP:
        return current
    if str(value).startswith("enc:"):
        return str(value)
    return encrypt_secret(value) or ""


def _dec(row: Any, name: str) -> str:
    raw = getattr(row, name, None) or ""
    if not raw:
        return ""
    text = str(raw)
    if not text.startswith("enc:"):
        return text
    try:
        return decrypt_secret(text) or ""
    except Exception as e:
        raise ValueError(f"key field {name} Decryption failed, please go to the settings page to save the key again.") from e


def parse_json(field: str | None) -> dict[str, Any]:
    if not field:
        return {}
    try:
        value = json.loads(field)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def public_extras(extras: dict[str, Any]) -> dict[str, Any]:
    """Don't pass legacy extra keys back to the browser."""
    return {key: value for key, value in extras.items() if key not in SECRET_EXTRA_KEYS}


def runtime_extras(extras: dict[str, Any]) -> dict[str, Any]:
    """Decrypt legacy extra credentials when reading compatible fields."""
    result = dict(extras)
    for key in SECRET_EXTRA_KEYS:
        value = result.get(key)
        if isinstance(value, str) and value.startswith("enc:"):
            result[key] = decrypt_secret(value) or ""
    return result
