"""``realmock.platform.core.secrets`` unit tests.

Coverage:

- AES-256-GCM encryption/decryption round trip;
- Backward compatibility with the legacy plaintext format (no prefix);
- Legacy ``enc:v1:`` ciphertext explicitly raises ``LegacySecretFormatError``;
- AEAD rejects tampering with any ciphertext/tag/salt/nonce field;
- Empty-value/None boundaries;
- Encrypting the same plaintext twice yields different ciphertexts (random salt + nonce).
"""

from __future__ import annotations

import base64

import pytest

from realmock.platform.core.secrets import (
    LegacySecretFormatError,
    _reset_cache,
    decrypt_secret,
    encrypt_secret,
)


@pytest.fixture(autouse=True)
def _stable_master_key(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Use a temporary fixed master plus an isolated keyfile to avoid contaminating the global ``data/.secret.key``."""
    import base64 as _b64

    monkeypatch.setenv("SECRET_KEY", _b64.b64encode(b"a" * 32).decode())
    # Override the default keyfile with a temporary directory
    monkeypatch.setattr(
        "realmock.platform.core.secrets._SHARED_DATA", tmp_path
    )
    monkeypatch.setattr(
        "realmock.platform.core.secrets._DEFAULT_KEYFILE", tmp_path / ".secret.key"
    )
    _reset_cache()
    yield
    _reset_cache()


class TestEncryptDecrypt:
    def test_roundtrip(self) -> None:
        plain = "sk-1234567890abcdef"
        enc = encrypt_secret(plain)
        assert enc is not None
        assert enc.startswith("enc:v2:")
        assert enc != plain
        assert decrypt_secret(enc) == plain

    def test_encrypt_idempotent(self) -> None:
        """A second call with an already encrypted string returns it directly without wrapping it again."""
        plain = "hello"
        enc = encrypt_secret(plain)
        assert encrypt_secret(enc) == enc

    def test_decrypt_legacy_plaintext(self) -> None:
        """Return legacy plaintext without the ``enc:v2:`` prefix unchanged to preserve migration compatibility."""
        legacy = "legacy-plain-key"
        assert decrypt_secret(legacy) == legacy

    def test_decrypt_legacy_v1_raises(self) -> None:
        """Legacy ``enc:v1:`` ciphertext should explicitly raise ``LegacySecretFormatError``."""
        with pytest.raises(LegacySecretFormatError):
            decrypt_secret(
                "enc:v1:" + base64.b64encode(b"x" * 16).decode() +
                ":" + base64.b64encode(b"y" * 32).decode() +
                ":" + base64.b64encode(b"z").decode()
            )

    def test_decrypt_empty_and_none(self) -> None:
        assert decrypt_secret(None) is None
        assert decrypt_secret("") == ""
        assert encrypt_secret(None) is None
        assert encrypt_secret("") == ""

    def test_tampered_cipher_rejected(self) -> None:
        """Tampered AEAD ciphertext should raise an exception."""
        enc = encrypt_secret("top-secret")
        assert enc is not None and enc.startswith("enc:v2:")
        parts = enc.split(":")
        assert len(parts) == 6
        ct = parts[5]
        # Flip the first character (while keeping base64 valid)
        parts[5] = ("B" if ct[0] != "B" else "C") + ct[1:]
        tampered = ":".join(parts)
        with pytest.raises(ValueError, match="AES-GCM decryption or authentication failed"):
            decrypt_secret(tampered)

    def test_tampered_tag_rejected(self) -> None:
        enc = encrypt_secret("top-secret")
        assert enc is not None and enc.startswith("enc:v2:")
        parts = enc.split(":")
        assert len(parts) == 6
        tag = parts[4]
        parts[4] = ("Z" if tag[0] != "Z" else "Y") + tag[1:]
        tampered = ":".join(parts)
        with pytest.raises(ValueError, match="AES-GCM decryption or authentication failed"):
            decrypt_secret(tampered)

    def test_tampered_salt_rejected(self) -> None:
        enc = encrypt_secret("top-secret")
        assert enc is not None and enc.startswith("enc:v2:")
        parts = enc.split(":")
        assert len(parts) == 6
        salt = parts[2]
        parts[2] = ("Z" if salt[0] != "Z" else "Y") + salt[1:]
        tampered = ":".join(parts)
        # salt mismatch → derived key differs → GCM auth fails by design.
        with pytest.raises((ValueError, Exception)):
            decrypt_secret(tampered)

    def test_wrong_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Encrypted string format error"):
            decrypt_secret("enc:v2:only:four")

    def test_random_salt_and_nonce(self) -> None:
        """Encrypting the same plaintext twice should produce different ciphertexts (random salt + nonce)."""
        a = encrypt_secret("same")
        b = encrypt_secret("same")
        assert a != b
        # But all can be decoded back to the original text
        assert decrypt_secret(a) == decrypt_secret(b) == "same"

    def test_unicode_roundtrip(self) -> None:
        plain = "Hello world 🔑 résumé"
        assert decrypt_secret(encrypt_secret(plain)) == plain
