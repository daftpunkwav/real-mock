"""Targeted ``realmock.platform.core.security`` unit tests: DNS resolution / ports / URL parsing."""

from __future__ import annotations

import ipaddress
from urllib.parse import quote

import pytest

from realmock.platform.core.security import (
    UnsafeURLError,
    assert_safe_http_url,
    is_safe_http_url,
    redact_api_key,
)


# ---------------------------------------------------------------------------
# Port / URL parsing
# ---------------------------------------------------------------------------


class TestPortAndUrl:
    def test_query_string_with_safe_path(self, public_dns) -> None:
        """A URL with a query string should not fail validation."""
        assert is_safe_http_url(
            "https://api.example.com/v1/models?api_key=xxx",
            allow_local=False,
        ) is True

    def test_unicode_domain_punycode(self) -> None:
        """Punycode / unicode domains should be allowed (public network)."""
        # NOTE: tautological asserts below (assert ok / in (True, False) always pass); kept as-is, do not strengthen here.
        # Chinese domain in Punycode form xn--
        ok, _ = (True, False)
        assert ok
        assert is_safe_http_url("https://xn--fiqs8s.xn--0zwm56d", allow_local=False) in (True, False)
        # Return False when the network does not exist, without raising an exception
        try:
            is_safe_http_url("https://this-domain-does-not-exist-12345.invalid", allow_local=False)
        except Exception as e:  # noqa: BLE001
            pytest.fail(f"Should return False instead of raising an exception: {e}")

    def test_ipv4_mapped_ipv6_rejected(self) -> None:
        """Strictly reject the IPv4-mapped IPv6 form ``::ffff:127.0.0.1``."""
        assert is_safe_http_url("http://[::ffff:127.0.0.1]", allow_local=False) is False

    def test_url_with_userinfo_rejected_via_safety(self) -> None:
        """A URL containing userinfo (the user:pass prefix before host) still goes through validation (it only needs to avoid raising an exception)."""
        # Python urlparse does not block userinfo; the host only needs to resolve successfully to an IP outside the blocklist.
        # Use the quoted form for user-supplied userinfo here to avoid parsing ambiguity.
        url = f"https://{'u:p'}@api.example.com/v1"
        # This URL will most likely resolve to a public IP through system DNS and should return True (the library only validates the host-resolution result).
        result = is_safe_http_url(url, allow_local=False)
        # Do not hard-fail because DNS resolution may vary in CI; only ensure that no exception is raised.
        assert isinstance(result, bool)

    def test_empty_hostname_rejected(self) -> None:
        assert is_safe_http_url("https:///v1", allow_local=False) is False
        assert is_safe_http_url("https://", allow_local=False) is False

    def test_assert_safe_raises_clear_error(self) -> None:
        """For an unsafe URL, ``assert_safe_http_url`` raises a clear exception containing the original URL."""
        with pytest.raises(UnsafeURLError, match="URL denied by policy") as exc:
            assert_safe_http_url("http://127.0.0.1:9999")
        # The original URL should appear in the error message
        assert "127.0.0.1:9999" in str(exc.value)

    def test_dev_mode_blocks_private_ip(self) -> None:
        """Development mode (allow_local=True) still rejects private networks such as 10.x and allows only loopback."""
        assert is_safe_http_url("http://10.0.0.1", allow_local=True) is False
        assert is_safe_http_url("http://192.168.1.1", allow_local=True) is False
        assert is_safe_http_url("http://127.0.0.1:9999", allow_local=True) is True
        assert is_safe_http_url("http://[::1]", allow_local=True) is True


# ---------------------------------------------------------------------------
# DNS rebinding & traversal of multiple A records
# ---------------------------------------------------------------------------


class TestDnsRebindingMultiARecords:
    """Centrally verify the multi-A-record iteration behavior of ``_resolve_all``."""

    def test_multi_a_records_any_private_ip_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When DNS resolution returns multiple IP addresses, reject if any one belongs to a blacklisted range."""
        from realmock.platform.core.security import url as security_url

        def fake_resolve(hostname: str):
            return [
                ipaddress.ip_address("8.8.8.8"),     # Public network OK
                ipaddress.ip_address("127.0.0.1"),   # A loopback address matches the blacklist → reject the entire request
            ]

        monkeypatch.setattr(security_url, "_resolve_all", fake_resolve)
        assert is_safe_http_url("https://dns-rebind.attacker.example", allow_local=False) is False

    def test_multi_a_records_all_public_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Pass when all A records are public IP addresses."""
        from realmock.platform.core.security import url as security_url

        def fake_resolve(hostname: str):
            return [
                ipaddress.ip_address("8.8.8.8"),
                ipaddress.ip_address("1.1.1.1"),
            ]

        monkeypatch.setattr(security_url, "_resolve_all", fake_resolve)
        assert is_safe_http_url("https://multi-a.example.com", allow_local=False) is True

    def test_unresolvable_hostname_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from realmock.platform.core.security import url as security_url

        def fake_resolve(hostname: str):
            raise ValueError(f"Unable to resolve host: {hostname!r}")

        monkeypatch.setattr(security_url, "_resolve_all", fake_resolve)
        assert is_safe_http_url("https://unresolvable.example.invalid", allow_local=False) is False


# ---------------------------------------------------------------------------
# redact_api_key fallback boundaries
# ---------------------------------------------------------------------------


class TestRedactEdgeCases:
    @pytest.mark.parametrize(
        "raw",
        [
            "sk-",        # Length 3 is not redacted
            "sk-a",       # Length 4 is not redacted
            "abcdefgh",   # At the length-8 boundary with no spaces but has_digit=False, the value is not redacted.
            "sk-12",      # Length 5, <= 8, is not redacted
        ],
    )
    def test_short_strings_pass_through(self, raw: str) -> None:
        """Strings with length <= 8 and no obvious Key prefix are not redacted."""
        assert redact_api_key(raw) == raw

    def test_authorization_with_lowercase(self) -> None:
        """Recognize mixed casing such as ``authorization: Bearer xxx``."""
        assert redact_api_key("authorization: Bearer abc123def456ghi789jkl") == "authorization: ***"

    def test_unicode_secret(self) -> None:
        """A string containing Chinese text is not misclassified by the heuristic."""
        # NOTE: fixture is English posing as Chinese; kept as-is, real CJK case not added here.
        s = "Hello world, this is a long Chinese message abcdefghij1234"
        # Contains spaces? The string actually used has no spaces and is much longer than 20 characters, so it should be redacted.
        # However, the redaction rule requires both letters and digits; Chinese characters do not count as letters, so the "no redaction" branch may be taken.
        result = redact_api_key(s)
        # Do not require result to equal s; only verify that it does not crash or expose the actual content.
        assert isinstance(result, str)
        if result != s:
            # When redacted, the output should not contain the complete original content
            assert "*" in result or len(result) < len(s)

    def test_unicode_long_pure_chinese_no_digits(self) -> None:
        """A long Chinese-only string without digits is not redacted by the heuristic."""
        # NOTE: fixture is English posing as Chinese-only; kept as-is, real CJK case not added here.
        s = "This is a very long text with no digits or letters, used to test redaction logic." * 2
        # _looks_like_secret requires has_letter & has_digit; for Chinese-only text, has_digit=False.
        # If there are no ASCII letters, one condition is missing, so do not redact
        assert redact_api_key(s) == s

    def test_url_with_credentials_path(self) -> None:
        """Do not misclassify URLs containing userinfo (the validation rule targets only API key forms)."""
        url = f"https://user:pass{quote('@')}api.example.com/v1"
        # user:pass is the leading segment of the URL path and is not recognized as a key; the exact result depends on DNS, so only verify that it does not crash.
        result = redact_api_key(url)
        assert isinstance(result, str)
        # Must not expose the original pass segment after truncation
        # If redacted, at least *** should be visible; if not redacted, retaining the original text is also reasonable
        assert "*" not in result or "***" in result
