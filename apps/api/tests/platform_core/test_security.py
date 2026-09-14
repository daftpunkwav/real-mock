"""``realmock.platform.core.security`` unit tests.

Coverage:
- Multiple input forms for ``redact_api_key``;
- Path-traversal prevention in ``sanitize_filename``;
- Out-of-bounds detection in ``assert_within_dir``;
- SSRF protection in ``is_safe_http_url`` (loopback / private network / link-local).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from realmock.platform.core.security import (
    PinnedHostTransport,
    UnsafeURLError,
    assert_safe_http_url,
    assert_within_dir,
    is_safe_http_url,
    pin_safe_http_url,
    redact_api_key,
    sanitize_filename,
    sniff_extension,
)


# ---------------------------------------------------------------------------
# redact_api_key
# ---------------------------------------------------------------------------


class TestRedactApiKey:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("", ""),
            (None, ""),
            # Normal Key
            ("sk-12345678abcdefgh", "sk-1***efgh"),
            ("sk-proj-abc123def456ghi789", "sk-p***i789"),
            ("sk-verylongapikeywithmanychars", "sk-v***hars"),
            # Authorization / Bearer / Token forms
            ("authorization: Bearer abc123def456", "authorization: ***"),
            ("Authorization: Bearer abc123def456", "Authorization: ***"),
            ("authorization=abc123def456", "authorization= ***"),
            ("bearer abc123def456", "Bearer ***"),
            ("token abc123def456", "Token ***"),
            ("basic dXNlcjpwYXNz", "Basic ***"),
            # Vendor-specific prefixes
            ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234", "sk-a***1234"),
            ("AIzaSyAbcDefGhiJklMnoPqrStuVwxYz1234567", "AIza***4567"),
            ("step-3.7-flash-abcdefghijklmnop", "step***mnop"),
            # Short strings and everyday phrases are no longer misclassified as ***
            ("short", "short"),
            ("RAG settings", "RAG settings"),
            ("HTTP/1.1", "HTTP/1.1"),
            # Redact only heuristic secrets (>=20 + mixed letters and digits)
            ("abcdef1234567890abcdef1234567890abcd", "abcd***abcd"),
            # Long sentences (>8 characters + containing spaces) are not redacted, avoiding false positives in log lines
            ("this is a long log message", "this is a long log message"),
        ],
    )
    def test_redact_variants(self, raw: str | None, expected: str) -> None:
        assert redact_api_key(raw) == expected

    def test_short_strings_not_overredacted(self) -> None:
        """Short strings (≤8 characters) should be returned unchanged to avoid false positives for terms such as RAG / hh:mm."""
        assert redact_api_key("RAG") == "RAG"
        assert redact_api_key("RAG settings") == "RAG settings"
        assert redact_api_key("main.py") == "main.py"

    def test_secret_shaped_strings(self) -> None:
        """A long string with mixed letters and digits and no spaces uses "first and last 4 characters" redaction."""
        token = "abcdef1234567890abcdef1234567890abcd"
        assert redact_api_key(token) == "abcd***abcd"

    def test_url_with_credentials(self) -> None:
        """The user:password segment in a URL must not be mistaken for an API Key (do not redact it)."""
        url = "https://user:pass@example.com/api"
        assert redact_api_key(url) == url  # The URL does not match a built-in Key pattern

    def test_pem_block_redacted(self) -> None:
        pem = "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC...\n-----END PRIVATE KEY-----"
        assert redact_api_key(pem) == "***PEM_REDACTED***"


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        "raw,expected_substr",
        [
            ("../../../etc/passwd", "passwd"),
            ("..\\..\\windows\\system32", "system32"),
            ("file with spaces.pdf", "file_with_spaces.pdf"),
            # After sanitizing a Chinese path, only the extension remains because only ASCII letters and digits plus . _ - are retained.
            # NOTE: ASCII name preserved; add ("U+7B80 U+5386.pdf", ".pdf") case for real CJK.
            ("Chinese Resume.pdf", ".pdf"),
            ("...hidden", "hidden"),  # Strip the "." prefix while preserving the core content
            ("", "file"),
            ("\x00evil\x00.exe", "_evil_.exe"),
            ("a" * 200 + ".pdf", ".pdf"),
        ],
    )
    def test_sanitization(self, raw: str, expected_substr: str) -> None:
        result = sanitize_filename(raw)
        assert expected_substr in result
        # Must never contain path separators or control characters
        assert "/" not in result
        assert "\\" not in result
        assert "\x00" not in result

    def test_long_suffix_capped(self) -> None:
        """Long-suffix filename: negative slicing must not retain an oversized result; the final length must be capped."""
        result = sanitize_filename("a." + "x" * 5000 + "." + "y" * 300)
        assert len(result) <= 120


class TestSniffExtension:
    @pytest.mark.parametrize(
        "head,ext,expected",
        [
            (b"%PDF-1.7", "pdf", True),
            (b"%PDF-", "pdf", True),
            (b"PK\x03\x04xxxx", "docx", True),
            (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "doc", True),
            # The header does not match the actual magic number: a spoofed extension is rejected
            (b"PK\x03\x04xxxx", "pdf", False),
            (b"%PDF-1.7", "docx", False),
            (b"", "pdf", False),
            # Unregistered formats (plain-text types) are not strictly validated and are always allowed
            (b"<html>", "md", True),
            (b"anything", "txt", True),
            (b"", "txt", True),
        ],
    )
    def test_classification(self, head: bytes, ext: str, expected: bool) -> None:
        assert sniff_extension(head, ext) is expected


# ---------------------------------------------------------------------------
# assert_within_dir
# ---------------------------------------------------------------------------


class TestAssertWithinDir:
    def test_relative_path_inside(self, tmp_path: Path) -> None:
        p = assert_within_dir(Path("subdir/file.txt"), tmp_path)
        assert p == (tmp_path / "subdir" / "file.txt").resolve()

    def test_relative_path_traversal_blocked(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Path out of bounds"):
            assert_within_dir(Path("../escape.txt"), tmp_path)

    def test_absolute_path_inside(self, tmp_path: Path) -> None:
        inner = tmp_path / "inner.txt"
        inner.write_text("ok")
        resolved = assert_within_dir(inner, tmp_path)
        assert resolved == inner.resolve()

    def test_absolute_path_outside_blocked(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("ok")
        with pytest.raises(ValueError, match="Path out of bounds"):
            assert_within_dir(outside, tmp_path)


# ---------------------------------------------------------------------------
# is_safe_http_url / assert_safe_http_url
# ---------------------------------------------------------------------------


class TestIsSafeHttpUrl:
    @pytest.mark.parametrize(
        "url,allow_local,expected",
        [
            # Protocol validation
            ("javascript:alert(1)", False, False),
            ("file:///etc/passwd", False, False),
            ("ftp://example.com", False, False),
            ("", False, False),
            # Public network https
            ("https://api.openai.com/v1", False, True),
            ("http://api.example.com/v1", False, True),
            # Reject loopback / private networks in strict mode
            ("http://127.0.0.1:8000", False, False),
            ("http://10.0.0.1", False, False),
            ("http://192.168.1.1", False, False),
            ("http://172.16.0.1", False, False),
            ("http://169.254.169.254/latest/meta-data", False, False),
            ("http://[::1]", False, False),
            # fake-ip range: when the proxy TUN takes over DNS, public domains resolve to this range and are forwarded by the proxy to
            # Treat the real target as safe and allow it globally (the behavior is the same regardless of allow_local).
            ("http://198.18.0.10", False, True),  # RFC 2544 range = fake-ip range
            ("http://198.18.0.10", True, True),
            ("http://192.0.2.1", False, False),  # TEST-NET-1
            ("http://198.51.100.1", False, False),  # TEST-NET-2
            ("http://203.0.113.1", False, False),  # TEST-NET-3
            # IANA exception: is_private=False but the address is reserved for PCP anycast, so it must be blocked explicitly.
            ("http://192.0.0.9", False, False),
            ("http://192.0.0.10", False, False),
            # Dev mode allows local access
            ("http://127.0.0.1:8000", True, True),
            ("http://localhost:8000", True, True),
        ],
    )
    def test_classification(self, url: str, allow_local: bool, expected: bool, public_dns) -> None:
        assert is_safe_http_url(url, allow_local=allow_local) is expected

    def test_assert_raises_unsafe(self) -> None:
        with pytest.raises(UnsafeURLError):
            assert_safe_http_url("http://127.0.0.1:8000")

    def test_non_standard_port_default_rejected(self, public_dns) -> None:
        """Reject ports other than 80/443 in strict mode."""
        assert is_safe_http_url("https://api.example.com:8443", allow_local=False) is False
        assert is_safe_http_url("https://api.example.com:443", allow_local=False) is True

    def test_port_whitelist_override(self, public_dns) -> None:
        allowed = frozenset({80, 443, 8443})
        assert is_safe_http_url(
            "https://api.example.com:8443", allow_local=False, allowed_ports=allowed
        ) is True

    def test_ipv6_literal_loopback_rejected(self) -> None:
        """The IPv6 literal [::1] is also strictly rejected."""
        assert is_safe_http_url("http://[::1]", allow_local=False) is False
        assert is_safe_http_url("http://[::ffff:127.0.0.1]", allow_local=False) is False


class TestPinSafeHttpUrl:
    def test_pin_literal_ip_loopback_dev(self) -> None:
        target = pin_safe_http_url("http://127.0.0.1:11434/v1", allow_local=True)
        assert target.hostname == "127.0.0.1"
        assert target.pinned_ip == "127.0.0.1"
        assert target.port == 11434

    def test_pin_rejects_unsafe(self) -> None:
        with pytest.raises(UnsafeURLError):
            pin_safe_http_url("http://127.0.0.1:11434/v1", allow_local=False)

    def test_pin_public_hostname(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ipaddress

        monkeypatch.setattr(
            "realmock.platform.core.security.url._resolve_all",
            lambda host: [ipaddress.ip_address("93.184.216.34")],
        )
        target = pin_safe_http_url("https://example.com/v1", allow_local=False)
        assert target.hostname == "example.com"
        assert target.pinned_ip == "93.184.216.34"


@pytest.mark.asyncio
async def test_pinned_host_transport_rewrites_to_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Change the outbound request host to the pinned IP while preserving the original domain in the Host header and sni_hostname."""
    captured: dict = {}

    class _Inner(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured["host"] = request.url.host
            captured["header_host"] = request.headers.get("host")
            captured["sni"] = (request.extensions or {}).get("sni_hostname")
            return httpx.Response(200, json={"ok": True}, request=request)

    import realmock.platform.core.security.url as sec_url

    monkeypatch.setattr(
        sec_url.httpx,
        "AsyncHTTPTransport",
        lambda **kw: _Inner(),
    )
    transport = PinnedHostTransport(hostname="api.example.com", pinned_ip="1.2.3.4")
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await client.get("https://api.example.com/v1/models")
    assert resp.status_code == 200
    assert captured["host"] == "1.2.3.4"
    assert captured["header_host"] == "api.example.com"
    assert captured["sni"] == "api.example.com"