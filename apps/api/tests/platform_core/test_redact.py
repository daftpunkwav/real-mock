# -*- coding: utf-8 -*-
"""Secret-redaction tests for platform/core/security/redact.py.

Covers both entry points:
- ``redact_api_key``: whole-value classification (PEM block, Authorization
  header, provider prefixes, mixed-alphanumeric heuristic);
- ``redact_secrets_in_text``: token-level scanning of free-form text
  (exception messages), where a key is embedded inside prose and the
  whole-value heuristic would miss it.
"""

from __future__ import annotations

from realmock.platform.core.security.redact import (
    redact_api_key,
    redact_secrets_in_text,
)


class TestRedactApiKey:
    def test_provider_key_prefixes_are_masked(self) -> None:
        assert redact_api_key("sk-abc123def456ghi789") == "sk-a***i789"
        assert redact_api_key("sk-ant-admin-01-xyzxyzxyz").startswith("sk-a")
        assert "xyzxyzxyz" not in redact_api_key("sk-ant-admin-01-xyzxyzxyz")
        assert redact_api_key("aizaAIzaSyLongTokenValue123").startswith("aiza")

    def test_authorization_and_bearer_headers(self) -> None:
        assert redact_api_key("Authorization: Bearer abcdefghijklmnop") == "Authorization: ***"
        assert redact_api_key("bearer 0123456789abcdef") == "Bearer ***"

    def test_pem_block_is_fully_redacted(self) -> None:
        pem = "-----BEGIN PRIVATE KEY-----\nMIIEvQ\n-----END PRIVATE KEY-----"
        assert redact_api_key(pem) == "***PEM_REDACTED***"

    def test_mixed_alnum_secret_is_masked(self) -> None:
        out = redact_api_key("Abcdef123456Xyz789Qrst1234")
        assert out == "Abcd***1234"

    def test_short_and_benign_values_pass_through(self) -> None:
        assert redact_api_key("") == ""
        assert redact_api_key("short") == "short"
        assert redact_api_key("/api/v1/resume/list") == "/api/v1/resume/list"
        assert redact_api_key("HTTP 502 bad gateway") == "HTTP 502 bad gateway"


class TestRedactSecretsInText:
    def test_embedded_provider_key_is_masked(self) -> None:
        out = redact_secrets_in_text(
            "request failed: 401, key sk-abc123def456ghi789jkl rejected by provider"
        )
        assert "sk-abc123def456ghi789jkl" not in out
        assert out.startswith("request failed: 401, key sk-a***")
        assert out.endswith("rejected by provider")

    def test_bearer_substring_is_masked(self) -> None:
        out = redact_secrets_in_text("auth error: Bearer 0123456789abcdefg refused")
        assert "0123456789abcdefg" not in out
        assert "auth error:" in out

    def test_standalone_mixed_token_is_masked(self) -> None:
        out = redact_secrets_in_text("token T1x9Ab2cD3eF4gH5iJ6kL rejected")
        assert "T1x9Ab2cD3eF4gH5iJ6kL" not in out

    def test_overlong_pure_alpha_run_is_also_masked(self) -> None:
        # Pins the documented conservative behavior: the standalone-run rule
        # has no mixed-alphanumeric requirement, so a 20+ pure-letter run is
        # masked too (over-masking beats leaking an unusual secret shape).
        out = redact_secrets_in_text("failed with internationalization anyway")
        assert "internationalization" not in out

    def test_prose_without_secrets_is_preserved(self) -> None:
        text = (
            "Connection timeout after 30 seconds to https://api.example.com/v1 "
            "(attempt 2 of 3); check network and retry"
        )
        assert redact_secrets_in_text(text) == text

    def test_pem_inside_text_is_fully_redacted(self) -> None:
        out = redact_secrets_in_text("load key failed: -----BEGIN RSA PRIVATE KEY-----")
        assert out == "***PEM_REDACTED***"

    def test_basic_authorization_substring_is_masked(self) -> None:
        # A Basic payload is base64: the "+/=" separator and padding
        # characters break the standalone-run rule, so the scheme form is
        # the only net that catches it.
        out = redact_secrets_in_text("401 rejected: Basic dXNlcjpwYXNz0123 required")
        assert "dXNlcjpwYXNz0123" not in out
        assert out.startswith("401 rejected: Basi***")

    def test_basic_short_payload_is_masked(self) -> None:
        out = redact_secrets_in_text("auth failed: Basic abc123")
        assert "abc123" not in out

    def test_basic_minimal_base64_payload_is_masked(self) -> None:
        # Valid base64 lengths are multiples of 4, so 4 chars is the floor a
        # payload can have; anything shorter encodes nothing.
        out = redact_secrets_in_text("401 for Basic YQ==")
        assert "YQ==" not in out

    def test_basic_base64_padding_is_masked_whole(self) -> None:
        out = redact_secrets_in_text("server said: Basic dXNlci9wYXNzOnBhc3M=")
        assert "dXNlci9wYXNzOnBhc3M=" not in out

    def test_basic_prose_with_short_words_is_preserved(self) -> None:
        # The word after "basic" is shorter than the payload floor, so this
        # prose survives; words of 4+ chars after "basic" are masked, the
        # module's documented over-masking tradeoff.
        text = "the basic is not the only scheme"
        assert redact_secrets_in_text(text) == text

    def test_url_query_credential_is_masked(self) -> None:
        # A vendor that puts the secret in the query (OAuth token endpoints)
        # makes the exception text carry it; the URL treatment masks the
        # value and keeps the parameter name.
        out = redact_secrets_in_text(
            "connect failed: https://api.vendor.com/v1?api_key=shortsecret123 refused"
        )
        assert "shortsecret123" not in out
        assert "api_key=***" in out
        assert "connect failed:" in out
        assert "refused" in out

    def test_url_userinfo_password_is_masked(self) -> None:
        out = redact_secrets_in_text("login to https://user:secretpw@host.example.com/v1 failed")
        assert "secretpw" not in out
        assert "user:***@host.example.com" in out

    def test_bare_authorization_header_is_masked_whole(self) -> None:
        # The whole-value rule runs before the token scan: a message that IS
        # the header is caught whole, including payloads shorter than the
        # scanner thresholds.
        out = redact_secrets_in_text("Authorization: Basic YQ")
        assert "YQ" not in out

    def test_empty_value_returns_empty(self) -> None:
        assert redact_secrets_in_text("") == ""
        assert redact_secrets_in_text(None) == ""
