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

    def test_prose_without_secrets_is_preserved(self) -> None:
        text = (
            "Connection timeout after 30 seconds to https://api.example.com/v1 "
            "(attempt 2 of 3); check network and retry"
        )
        assert redact_secrets_in_text(text) == text

    def test_pem_inside_text_is_fully_redacted(self) -> None:
        out = redact_secrets_in_text("load key failed: -----BEGIN RSA PRIVATE KEY-----")
        assert out == "***PEM_REDACTED***"

    def test_empty_value_returns_empty(self) -> None:
        assert redact_secrets_in_text("") == ""
        assert redact_secrets_in_text(None) == ""
