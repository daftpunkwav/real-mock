"""Secrets tests for realmock.platform.core.secrets.

Covers: master-key validation states, secret loading (plain/keyfile/
  corrupt fallback), decrypt failure branches, and the derived-key
  LRU (hit on repeat decrypt, cleared by _reset_cache).
Conventions: isolated tmp keyfiles; cache reset after each branch.
"""

from __future__ import annotations

import pytest


class TestSecretsExtras:
    def test_validate_master(self, monkeypatch) -> None:
        from realmock.platform.core import secrets as sec

        monkeypatch.delenv("SECRET_KEY", raising=False)
        assert sec.validate_master_key_env() == "missing"
        monkeypatch.setenv("SECRET_KEY", "short")
        assert sec.validate_master_key_env() == "too_short"
        monkeypatch.setenv("SECRET_KEY", "long-enough-secret-123")
        assert sec.validate_master_key_env() == "ok"

    def test_load_plain_and_keyfile(self, tmp_path, monkeypatch) -> None:
        import base64 as _b64

        from realmock.platform.core import secrets as sec

        monkeypatch.setattr(sec, "_SHARED_DATA", tmp_path)
        monkeypatch.setattr(sec, "_DEFAULT_KEYFILE", tmp_path / ".secret.key")
        sec._reset_cache()
        monkeypatch.setenv("SECRET_KEY", "plain-text-key-long-enough-xyz")
        assert len(sec._load_secret_bytes()) == 32
        sec._reset_cache()
        # Short valid base64 (decodes to <16 bytes) falls through to the KDF
        # path over the raw string — NOT the zero-pad decode path.
        monkeypatch.setenv("SECRET_KEY", _b64.b64encode(b"short").decode())
        sec._reset_cache()
        assert sec._load_secret_bytes() == sec._derive_key(
            _b64.b64encode(b"short").decode().encode(), sec._MASTER_SALT
        )
        sec._reset_cache()
        # file fallback + corrupt file regenerate
        monkeypatch.delenv("SECRET_KEY", raising=False)
        sec._reset_cache()
        assert len(sec._load_secret_bytes()) == 32
        (tmp_path / ".secret.key").write_text("!!!not-base64!!!")
        sec._reset_cache()
        assert len(sec._load_secret_bytes()) == 32
        # The unreadable file is preserved as a timestamped backup before the
        # regeneration, so the overwrite stays recoverable.
        backups = list(tmp_path.glob(".secret.key.bak-*"))
        assert len(backups) == 1
        assert backups[0].read_text() == "!!!not-base64!!!"
        sec._reset_cache()

    def test_keyfile_read_failure_never_overwrites(self, tmp_path, monkeypatch) -> None:
        """A transient read failure (AV / backup lock on Windows) must fail
        loud instead of regenerating: the keyfile content is most likely
        intact and overwriting it would irreversibly orphan every existing
        enc:v2 ciphertext."""
        import base64 as _b64
        import pathlib

        from realmock.platform.core import secrets as sec

        monkeypatch.setattr(sec, "_SHARED_DATA", tmp_path)
        keyfile = tmp_path / ".secret.key"
        monkeypatch.setattr(sec, "_DEFAULT_KEYFILE", keyfile)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        original = _b64.b64encode(b"k" * 32).decode()
        keyfile.write_text(original)

        real_read_text = pathlib.Path.read_text

        def _locked(path_self, *args, **kwargs):
            if path_self == keyfile:
                raise PermissionError(13, "locked by antivirus")
            return real_read_text(path_self, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, "read_text", _locked)
        sec._reset_cache()
        with pytest.raises(PermissionError):
            sec._load_secret_bytes()
        # The original key survives untouched (read_bytes bypasses the lock
        # patch) and no backup was made.
        assert keyfile.read_bytes().decode() == original
        assert list(tmp_path.glob(".secret.key.bak-*")) == []
        sec._reset_cache()

    def test_keyfile_short_key_treated_as_corrupt(self, tmp_path, monkeypatch) -> None:
        """An empty/truncated keyfile still base64-decodes to a useless short
        key; it must take the corrupt path (backup + regenerate) instead of
        silently running with a sub-32-byte master."""
        import base64 as _b64

        from realmock.platform.core import secrets as sec

        monkeypatch.setattr(sec, "_SHARED_DATA", tmp_path)
        keyfile = tmp_path / ".secret.key"
        monkeypatch.setattr(sec, "_DEFAULT_KEYFILE", keyfile)
        monkeypatch.delenv("SECRET_KEY", raising=False)

        for corrupt in ("", _b64.b64encode(b"short").decode()):
            keyfile.write_text(corrupt)
            sec._reset_cache()
            assert len(sec._load_secret_bytes()) == 32
        # Each corrupt generation preserved the previous file as a backup.
        assert len(list(tmp_path.glob(".secret.key.bak-*"))) == 2
        sec._reset_cache()

    def test_master_key_path_selection_boundary(self, tmp_path, monkeypatch) -> None:
        """Pin the two master-key paths for base64-shaped plain text.

        A SECRET_KEY of valid base64 charset always attempts the decode path
        first; the split depends solely on the decoded length (>=16 bytes vs
        not), regardless of whether the user meant plain text.
        """
        import base64 as _b64

        from realmock.platform.core import secrets as sec

        monkeypatch.setattr(sec, "_SHARED_DATA", tmp_path)
        monkeypatch.setattr(sec, "_DEFAULT_KEYFILE", tmp_path / ".secret.key")

        # Valid base64 charset decoding to >=16 bytes: zero-pad decode path,
        # even though the user typed plain text.
        monkeypatch.setenv("SECRET_KEY", "abcdefghijklmnopqrstuvwx")
        sec._reset_cache()
        assert sec._load_secret_bytes() == _b64.b64decode(
            "abcdefghijklmnopqrstuvwx"
        ).ljust(sec._KEY_BYTES, b"0")

        # Valid base64 charset decoding to <16 bytes: KDF path over the raw
        # string, not the decoded bytes.
        monkeypatch.setenv("SECRET_KEY", "abcdefghijklmnop")
        sec._reset_cache()
        assert sec._load_secret_bytes() == sec._derive_key(
            b"abcdefghijklmnop", sec._MASTER_SALT
        )

        # Non-base64 plain text always takes the KDF path.
        monkeypatch.setenv("SECRET_KEY", "long-enough-secret-123")
        sec._reset_cache()
        assert sec._load_secret_bytes() == sec._derive_key(
            b"long-enough-secret-123", sec._MASTER_SALT
        )
        sec._reset_cache()

    def test_decrypt_bad_base64_and_wrong_key(self, monkeypatch, tmp_path) -> None:
        import base64 as _b64

        from realmock.platform.core import secrets as sec

        monkeypatch.setattr(sec, "_SHARED_DATA", tmp_path)
        monkeypatch.setattr(sec, "_DEFAULT_KEYFILE", tmp_path / ".secret.key")
        monkeypatch.setenv("SECRET_KEY", _b64.b64encode(b"a" * 32).decode())
        sec._reset_cache()
        try:
            with pytest.raises(ValueError, match="base64"):
                sec.decrypt_secret("enc:v2:a:a:a:a")
            enc = sec.encrypt_secret("hello")
            assert enc is not None
            monkeypatch.setenv("SECRET_KEY", _b64.b64encode(b"b" * 32).decode())
            sec._reset_cache()
            with pytest.raises(ValueError, match="AES-GCM"):
                sec.decrypt_secret(enc)
        finally:
            sec._reset_cache()

    def test_derived_key_cache_hit_and_reset(self, monkeypatch, tmp_path) -> None:
        """PBKDF2 derivations are cached per (master, salt): re-decrypting one
        ciphertext re-derives nothing, and ``_reset_cache`` drops the derived
        keys so the next decrypt pays the derivation again."""
        import base64 as _b64

        from realmock.platform.core import secrets as sec

        monkeypatch.setattr(sec, "_SHARED_DATA", tmp_path)
        monkeypatch.setattr(sec, "_DEFAULT_KEYFILE", tmp_path / ".secret.key")
        monkeypatch.setenv("SECRET_KEY", _b64.b64encode(b"a" * 32).decode())
        sec._reset_cache()
        try:
            enc = sec.encrypt_secret("cached-key")
            assert enc is not None
            assert sec.decrypt_secret(enc) == "cached-key"
            first = sec._derive_key.cache_info()
            assert first.misses == 1  # one derivation: the fresh encrypt salt
            # Same ciphertext again: cache hit, no new derivation.
            assert sec.decrypt_secret(enc) == "cached-key"
            second = sec._derive_key.cache_info()
            assert second.hits == first.hits + 1
            assert second.misses == first.misses
            # _reset_cache clears derived keys too (counters reset with the LRU);
            # the next decrypt pays the derivation again.
            sec._reset_cache()
            assert sec._derive_key.cache_info().currsize == 0
            assert sec.decrypt_secret(enc) == "cached-key"
            assert sec._derive_key.cache_info().misses == 1
        finally:
            sec._reset_cache()
