"""URL policy extra tests for apps/api/src/realmock/platform/core/security/url.py and url_pin.py.

Covers: _resolve_all literal/failure/bad-IP branches, _ip_is_safe exception paths,
is_safe_http_url bad/unresolvable/urlparse-error branches, pin_safe_http_url scheme
guards and make_pinned_async_client transport wiring.

Conventions: no real network (DNS/httpx faked via monkeypatch); asyncio_mode=auto.
"""

from __future__ import annotations

import ipaddress

import pytest

import realmock.platform.core.security.url as url_mod



@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def test_resolve_literal_and_failure(monkeypatch) -> None:
    assert url_mod._resolve_all("8.8.8.8") == [ipaddress.ip_address("8.8.8.8")]
    assert url_mod._resolve_all("[::1]") == [ipaddress.ip_address("::1")]

    def _boom(host, *a, **k):
        raise OSError("dns down")

    monkeypatch.setattr(url_mod.socket, "getaddrinfo", _boom)
    with pytest.raises(ValueError, match="Unable to resolve"):
        url_mod._resolve_all("example.com")

    # getaddrinfo returns an unparsable IP -> skipped, empty list returned.
    def _bad_ip(host, *a, **k):
        return [(2, 1, 6, "", ("not-an-ip", 0))]

    monkeypatch.setattr(url_mod.socket, "getaddrinfo", _bad_ip)
    assert url_mod._resolve_all("example.com") == []


def test_ip_safe_exception_path(monkeypatch) -> None:
    from types import SimpleNamespace

    # Empty the network lists so the try-block is reached with fake IPs.
    monkeypatch.setattr(url_mod, "_PROVIDER_NETWORKS", ())
    monkeypatch.setattr(url_mod, "_DEFAULT_BLOCKED_NETS", [])
    public = SimpleNamespace(is_private=False, is_multicast=False, is_reserved=False, is_unspecified=False)
    assert url_mod._ip_is_safe(public, allow_local=False) is True  # type: ignore[arg-type]
    multi = SimpleNamespace(is_private=False, is_multicast=True, is_reserved=False, is_unspecified=False)
    assert url_mod._ip_is_safe(multi, allow_local=False) is False  # type: ignore[arg-type]
    unspec = SimpleNamespace(is_private=False, is_multicast=False, is_reserved=False, is_unspecified=True)
    assert url_mod._ip_is_safe(unspec, allow_local=False) is False  # type: ignore[arg-type]

    class _Boom:
        @property
        def is_private(self):
            raise RuntimeError("boom")

    assert url_mod._ip_is_safe(_Boom(), allow_local=False) is True  # type: ignore[arg-type]


def test_is_safe_bad_url_and_unresolvable(monkeypatch) -> None:
    assert url_mod.is_safe_http_url("") is False
    assert url_mod.is_safe_http_url("ftp://x") is False
    assert url_mod.is_safe_http_url("http://") is False
    monkeypatch.setattr(url_mod, "_resolve_all", lambda h: (_ for _ in ()).throw(ValueError("no")))
    assert url_mod.is_safe_http_url("http://example.com") is False
    # urlparse raising -> False (line 161-162).
    monkeypatch.setattr(url_mod, "urlparse", lambda u: (_ for _ in ()).throw(ValueError("bad")))
    assert url_mod.is_safe_http_url("http://example.com") is False


def test_pin_empty_and_bad_scheme(monkeypatch) -> None:
    with pytest.raises(url_mod.UnsafeURLError):
        url_mod.pin_safe_http_url("")
    with pytest.raises(url_mod.UnsafeURLError):
        url_mod.pin_safe_http_url("ftp://example.com/x")
    with pytest.raises(url_mod.UnsafeURLError):
        url_mod.pin_safe_http_url("http://")
    # urlparse raising -> UnsafeURLError (line 223-224).
    monkeypatch.setattr(url_mod, "urlparse", lambda u: (_ for _ in ()).throw(ValueError("bad")))
    with pytest.raises(url_mod.UnsafeURLError):
        url_mod.pin_safe_http_url("http://example.com")


@pytest.mark.asyncio
async def test_pinned_client_uses_pin(monkeypatch) -> None:
    # Patch pin to avoid DNS, patch httpx.AsyncClient to avoid network.
    target = url_mod.PinnedHttpTarget(
        original_url="http://example.com/x", hostname="example.com",
        pinned_ip="93.184.216.34", scheme="http", port=None,
    )
    monkeypatch.setattr(url_mod, "pin_safe_http_url", lambda *a, **k: target)
    seen: dict = {}

    class _FakeClient:
        def __init__(self, **k):
            seen.update(k)

    monkeypatch.setattr(url_mod.httpx, "AsyncClient", _FakeClient)
    # url_pin.make_pinned_async_client imports pin lazily from url.py
    from realmock.platform.core.security.url_pin import make_pinned_async_client

    make_pinned_async_client("http://example.com/x")
    assert "transport" in seen
