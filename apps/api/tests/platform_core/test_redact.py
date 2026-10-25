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

    def test_bearer_base64_payload_is_masked(self) -> None:
        # A standard-base64 payload carries +/ and trailing = padding; the
        # scheme form must consume the whole alphabet or the standalone-run
        # rule splits at the separator and the halves survive.
        out = redact_secrets_in_text("rejected: Bearer dXNlci9wYXNz012345== refused")
        assert "dXNlci9wYXNz012345" not in out

    def test_single_unrecognized_token_is_masked(self) -> None:
        # The whole-value heuristic needs letters AND digits, so a pure
        # alphabetic run escapes it; the token scan runs regardless of the
        # fragment's whitespace. The full masked form is pinned so a scanner
        # that alters a single character cannot pass.
        assert redact_secrets_in_text("internationalization") == "inte***"

    def test_url_query_basic_payload_is_masked(self) -> None:
        # A Basic payload inside a query is masked wholesale by the query
        # treatment: the query value carries the credential whatever its
        # scheme, and path/fragment never hold unencoded spaces.
        out = redact_secrets_in_text(
            "denied at https://api.example.com/v1/token?auth=Basic+YQ== retry"
        )
        assert "YQ==" not in out
        assert "auth=***" in out

    def test_url_fragment_short_assignment_is_masked(self) -> None:
        # A fragment is where OAuth flows park access_token=..., and its
        # payload can be shorter than the free-text assignment floor.
        out = redact_secrets_in_text("denied at https://api.example.com/v1#access_token=abc123 end")
        assert "abc123" not in out

    def test_url_path_mixed_token_is_masked(self) -> None:
        # A path or fragment can also carry an unprefixed token (a signed
        # path is ``/files/<token>/content``), so a 20+ mixed-alphanumeric
        # segment is masked by the URL standalone rule.
        url = "https://files.example.com/dl/Abc123Def456Ghi789Jkl0/content"
        out = redact_secrets_in_text(f"lookup failed for {url}")
        assert "Abc123Def456Ghi789Jkl0" not in out
        assert "/dl/" in out and "/content" in out

    def test_url_path_ordinary_identifiers_stay_diagnosable(self) -> None:
        # Pins the diagnosability boundary that survives the URL standalone
        # rule: slugs, pure-digit and pure-alpha segments are not token
        # shapes (no letter-digit mix), and masking them would cost the
        # URL's readability — even at 20+ characters.
        for segment in ("session-445566", "20241024143022123456", "quarterly-financial-report"):
            url = f"https://api.example.com/v1/sessions/{segment}"
            assert redact_secrets_in_text(f"lookup failed for {url}") == (
                f"lookup failed for {url}"
            )

    def test_ipv6_url_query_credential_is_masked(self) -> None:
        # The closing bracket of an IPv6 literal authority is mid-URL, not
        # the end of it: cutting there would hand the query to the prose
        # path, which cannot mask a short named value.
        out = redact_secrets_in_text(
            "connect failed: http://[2001:db8::1]:8080/v1?api_key=shortsecret retry"
        )
        assert "shortsecret" not in out
        assert "api_key=***" in out
        assert "2001:db8::1" in out

    def test_url_fragment_without_query_is_scanned(self) -> None:
        # A credential parked after ``#`` in a query-less URL must not ride
        # along inside the path segment: the fragment is partitioned off
        # first and scanned with its own short assignment floor.
        out = redact_secrets_in_text("denied at https://api.example.com/v1#token=abc end")
        assert "token=abc" not in out
        assert "denied at" in out and "end" in out

    def test_url_fragment_percent_encoded_value_is_masked(self) -> None:
        # A percent-encoded payload character must not end the match: the
        # assignment class accepts ``%`` so an encoded fragment credential
        # is consumed whole. The full masked form is pinned so a scanner
        # that only strips the escapes cannot pass.
        out = redact_secrets_in_text(
            "denied at https://api.example.com/v1#access_token=abc%2Fdef%3D end"
        )
        assert out == "denied at https://api.example.com/v1#access_toke*** end"

    def test_url_path_percent_encoded_value_is_masked(self) -> None:
        out = redact_secrets_in_text(
            "denied at https://api.example.com/v1/files/token%3DAbc123Def456Ghi789/retrieve"
        )
        assert "token%3DAbc123Def456Ghi789" not in out
        assert "/files/" in out and "/retrieve" in out

    def test_url_username_credential_is_masked(self) -> None:
        # A credential supplied as the userinfo username is as sensitive as
        # one in the password; the URL treatment scans both.
        out = redact_secrets_in_text(
            "denied at https://sk-abcdefghijklmnopqrst@host.example.com/v1 end"
        )
        assert "sk-abcdefghijklmnopqrst" not in out
        assert "sk-a***@host.example.com" in out

    def test_url_path_base64_plus_token_is_masked(self) -> None:
        # A standard-base64 token carries ``+``; the URL standalone class
        # must not split at it, or the short halves survive.
        out = redact_secrets_in_text(
            "denied at https://api.example.com/v1/files/Abc123+Def456+Ghi789+Jkl0/retrieve"
        )
        assert "Abc123+Def456+Ghi789+Jkl0" not in out

    def test_url_path_uuid_identifier_stays_diagnosable(self) -> None:
        # A canonical UUID is the one mixed 20+ run that stays readable:
        # resource ids are UUID-shaped and correlation needs them whole.
        url = "https://api.example.com/v1/sessions/550e8400-e29b-41d4-a716-446655440000"
        assert redact_secrets_in_text(f"lookup failed for {url}") == f"lookup failed for {url}"

    def test_labeled_short_key_is_masked(self) -> None:
        # An unprefixed key shorter than the standalone floor survives when
        # it is bare, but a key-label assignment ("api_key: abc123") is a
        # credential shape at any length above 4.
        out = redact_secrets_in_text("rejected: api_key: abc123 outright")
        assert "abc123" not in out

    def test_labeled_prose_is_preserved(self) -> None:
        # The label form's digit lookahead keeps ordinary prose out: a bare
        # short value and a pure-alphabetic word after a label both stay.
        text = "the apikey is fine and api_key=required stays"
        assert redact_secrets_in_text(text) == text

    def test_query_value_with_percent_sequence_credential_is_masked(self) -> None:
        # A value carrying a percent sequence that reads like a format
        # specifier ("%a") must still lose its credential payload: the
        # specifier is kept, the surrounding text is masked.
        out = redact_secrets_in_text(
            "connect failed: https://x.example.com/v1?token=ab%aecd refused"
        )
        assert "ab%aecd" not in out
        assert "refused" in out

    def test_bearer_token_with_underscores_is_masked(self) -> None:
        # URL-safe tokens carry underscores; the scheme payload class must
        # consume them or the scan stops mid-token and the tail survives.
        out = redact_secrets_in_text("rejected: Bearer ab.dEf_ghIJKlmnoP refused")
        assert "dEf_ghIJKlmnoP" not in out
        assert "refused" in out

    def test_url_fragment_underscored_value_is_masked(self) -> None:
        out = redact_secrets_in_text("denied at https://api.example.com/v1#token=ab_cdef end")
        assert "ab_cdef" not in out

    def test_short_bearer_credential_is_masked(self) -> None:
        # A compact quoted credential is shorter than the 12-char scheme
        # floor; the short alternative catches it when it carries a digit.
        out = redact_secrets_in_text("provider rejected Bearer abc123 outright")
        assert "abc123" not in out
        assert "provider rejected" in out and "outright" in out

    def test_prose_after_scheme_words_is_preserved(self) -> None:
        # The short alternative's digit lookahead keeps pure-alphabetic prose
        # out of the net: the words that follow a scheme word in an error
        # sentence are usually exactly that. (A sentence that STARTS with
        # "authorization" is a whole-value header shape by design.)
        text = "the request says authorization required and the token is expired"
        assert redact_secrets_in_text(text) == text
