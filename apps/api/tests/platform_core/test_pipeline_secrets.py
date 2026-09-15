"""Pipeline secrets tests for realmock.platform.services.pipeline.secrets.

Covers: conditional encryption, safe decryption, JSON parsing,
  and public/runtime extras redaction.
Conventions: no DB; encryption uses the test master key.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from realmock.platform.services.pipeline import secrets as psec


class TestPipelineSecrets:
    def test_maybe_encrypt_variants(self) -> None:
        assert psec.maybe_encrypt(None, "cur") == "cur"
        assert psec.maybe_encrypt("", "cur") == "cur"
        assert psec.maybe_encrypt("keep", "cur") == "cur"
        assert psec.maybe_encrypt("enc:v2:x", "cur") == "enc:v2:x"
        enc = psec.maybe_encrypt("plain-key", "cur")
        assert enc.startswith("enc:")

    def test_dec_empty_and_plain(self) -> None:
        assert psec._dec(SimpleNamespace(api_key=""), "api_key") == ""
        assert psec._dec(SimpleNamespace(api_key="plain"), "api_key") == "plain"
        assert psec._dec(SimpleNamespace(), "api_key") == ""

    def test_dec_enc_roundtrip_and_failure(self) -> None:
        from realmock.platform.core.secrets import encrypt_secret

        enc = encrypt_secret("s3kret")
        assert psec._dec(SimpleNamespace(api_key=enc), "api_key") == "s3kret"
        with pytest.raises(ValueError, match="Decryption failed"):
            psec._dec(SimpleNamespace(api_key="enc:v2:bad:bad:bad:bad"), "api_key")

    def test_parse_json_variants(self) -> None:
        assert psec.parse_json(None) == {}
        assert psec.parse_json("") == {}
        assert psec.parse_json("{bad") == {}
        assert psec.parse_json("[1,2]") == {}
        assert psec.parse_json('{"a": 1}') == {"a": 1}

    def test_public_and_runtime_extras(self) -> None:
        from realmock.platform.core.secrets import encrypt_secret

        extras = {"asr_api_secret": "x", "keep": "y"}
        assert psec.public_extras(extras) == {"keep": "y"}
        enc = encrypt_secret("hidden")
        rt = psec.runtime_extras({"asr_api_secret": enc, "plain": "v"})
        assert rt["asr_api_secret"] == "hidden"
        assert rt["plain"] == "v"
        # non-enc values pass through
        assert psec.runtime_extras({"asr_api_secret": "plain"})["asr_api_secret"] == "plain"
