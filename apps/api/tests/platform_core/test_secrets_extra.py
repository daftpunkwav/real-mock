"""Secrets tests for realmock.platform.core.secrets.

Covers: master-key validation states, secret loading (plain/keyfile/
  corrupt fallback), and decrypt failure branches.
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
        # short base64 -> zero padded
        monkeypatch.setenv("SECRET_KEY", _b64.b64encode(b"short").decode())
        sec._reset_cache()
        assert len(sec._load_secret_bytes()) == 32
        # file fallback + corrupt file regenerate
        monkeypatch.delenv("SECRET_KEY", raising=False)
        sec._reset_cache()
        assert len(sec._load_secret_bytes()) == 32
        (tmp_path / ".secret.key").write_text("!!!not-base64!!!")
        sec._reset_cache()
        assert len(sec._load_secret_bytes()) == 32
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
