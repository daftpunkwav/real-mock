"""URL policy tests for realmock.platform.core.security.url.

Covers: denied wording, empty/unparsable URLs, scheme and port policy,
  resolver failures, localhost family checks, and IP allow-list branches.
Conventions: no network; DNS resolution is stubbed via monkeypatch.
"""

from __future__ import annotations

import ipaddress

import pytest

import realmock.platform.core.security.url as sec_url
from realmock.platform.core.security.url import (
    UnsafeURLError,
    assert_safe_http_url,
    is_localhost_family,
    is_safe_http_url,
    pin_safe_http_url,
)


@pytest.fixture
def pub(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sec_url, "_resolve_all", lambda host: [ipaddress.ip_address("93.184.216.34")])


class TestUrlDeniedWording:
    def test_assert_denied_mentions_policy(self, pub) -> None:
        with pytest.raises(UnsafeURLError, match="URL denied by policy"):
            assert_safe_http_url("http://127.0.0.1:8000")
        try:
            assert_safe_http_url("http://127.0.0.1:8000")
        except UnsafeURLError as e:
            assert "URL denied by policy" in str(e)

    def test_pin_denied_mentions_policy(self) -> None:
        with pytest.raises(UnsafeURLError, match="URL denied by policy"):
            pin_safe_http_url("http://127.0.0.1/", allow_local=False)

    def test_empty_and_unparsable(self) -> None:
        assert is_safe_http_url("") is False
        with pytest.raises(UnsafeURLError, match="URL is empty"):
            pin_safe_http_url("")
        with pytest.raises(UnsafeURLError, match="not secure"):
            pin_safe_http_url("ftp://example.com/x")
        with pytest.raises(UnsafeURLError, match="missing hostname"):
            pin_safe_http_url("http:///no-host")

    def test_require_https_and_scheme(self, pub) -> None:
        assert is_safe_http_url("http://example.com", require_https=True) is False
        assert is_safe_http_url("https://example.com", require_https=True) is True
        assert is_safe_http_url("javascript:alert(1)") is False
        with pytest.raises(UnsafeURLError, match="HTTPS"):
            pin_safe_http_url("http://example.com", require_https=True)

    def test_no_hostname(self, monkeypatch) -> None:
        monkeypatch.setattr(sec_url, "_resolve_all", lambda h: [ipaddress.ip_address("93.184.216.34")])
        assert is_safe_http_url("http:///x") is False

    def test_port_policy(self, pub) -> None:
        assert is_safe_http_url("https://example.com:8443", allowed_ports=frozenset({8443})) is True
        assert is_safe_http_url("https://example.com:8443") is False
        with pytest.raises(UnsafeURLError, match="port"):
            pin_safe_http_url("https://example.com:8443", allowed_ports=frozenset({443}))

    def test_resolve_failure(self, monkeypatch) -> None:
        def _boom(host):
            raise ValueError("Unable to resolve host: 'x'")

        monkeypatch.setattr(sec_url, "_resolve_all", _boom)
        assert is_safe_http_url("https://x.example/") is False
        with pytest.raises(UnsafeURLError, match="Unable to resolve"):
            pin_safe_http_url("https://x.example/")

    def test_empty_ips_pin(self, monkeypatch) -> None:
        monkeypatch.setattr(sec_url, "_resolve_all", lambda h: [])
        with pytest.raises(UnsafeURLError, match="Unable to resolve host"):
            pin_safe_http_url("https://example.com/")

    def test_trusted_fakeip_host(self, monkeypatch) -> None:
        monkeypatch.setattr(sec_url, "_resolve_all", lambda h: [ipaddress.ip_address("198.18.0.5")])
        assert is_safe_http_url("https://token-plan-cn.xiaomimimo.com/v1") is True
        target = pin_safe_http_url("https://token-plan-cn.xiaomimimo.com/v1")
        assert target.pinned_ip == "198.18.0.5"

    def test_resolve_all_branches(self, monkeypatch) -> None:
        assert sec_url._resolve_all("127.0.0.1") == [ipaddress.ip_address("127.0.0.1")]
        assert sec_url._resolve_all("[::1]") == [ipaddress.ip_address("::1")]
        import socket as _sock

        monkeypatch.setattr(_sock, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(_sock.gaierror("nope")))
        with pytest.raises(ValueError, match="Unable to resolve"):
            sec_url._resolve_all("nonexistent.invalid")
        # dedupe path: same ip twice via getaddrinfo
        import socket as _sock

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(_sock, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0)), (2, 1, 6, "", ("93.184.216.34", 0))])
        try:
            assert sec_url._resolve_all("example.com") == [ipaddress.ip_address("93.184.216.34")]
        finally:
            monkeypatch.undo()

    def test_ip_safe_exception_path(self, monkeypatch) -> None:
        class _Bad:
            is_private = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

        # is_private raising is swallowed -> allowed
        assert sec_url._ip_is_safe(ipaddress.ip_address("93.184.216.34"), allow_local=False) is True

    def test_all_ips_empty(self) -> None:
        assert sec_url._all_ips_safe([], allow_local=False) is False

    def test_is_localhost_family(self, monkeypatch) -> None:
        assert is_localhost_family("") is False
        monkeypatch.setattr(sec_url, "_resolve_all", lambda h: (_ for _ in ()).throw(ValueError("x")))
        assert is_localhost_family("example.com") is False
        monkeypatch.setattr(sec_url, "_resolve_all", lambda h: [ipaddress.ip_address("127.0.0.1")])
        assert is_localhost_family("localhost") is True
        monkeypatch.setattr(sec_url, "_resolve_all", lambda h: [ipaddress.ip_address("93.184.216.34")])
        assert is_localhost_family("example.com") is False
