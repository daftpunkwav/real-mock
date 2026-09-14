"""Session fix: SSRF DNS pinning (pin_safe_http_url + PinnedHostTransport)."""

from __future__ import annotations

import ipaddress

import httpx
import pytest

from realmock.platform.core.security import (
    PinnedHostTransport,
    UnsafeURLError,
    pin_safe_http_url,
)


def test_pin_rejects_loopback_without_allow_local() -> None:
    with pytest.raises(UnsafeURLError):
        pin_safe_http_url("http://127.0.0.1:11434/v1", allow_local=False)


def test_pin_allows_loopback_with_allow_local() -> None:
    t = pin_safe_http_url("http://127.0.0.1:11434/v1", allow_local=True)
    assert t.pinned_ip == "127.0.0.1"
    assert t.hostname == "127.0.0.1"


def test_pin_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "realmock.platform.core.security.url._resolve_all",
        lambda host: [ipaddress.ip_address("93.184.216.34")],
    )
    t = pin_safe_http_url("https://example.com/v1", allow_local=False)
    assert t.hostname == "example.com"
    assert t.pinned_ip == "93.184.216.34"


def test_pin_single_resolve_no_toctou(monkeypatch: pytest.MonkeyPatch) -> None:
    """pin calls _resolve_all only once and validates against that result (no second DNS lookup)."""
    calls: list[str] = []

    def _once(host: str):
        calls.append(host)
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr("realmock.platform.core.security.url._resolve_all", _once)
    t = pin_safe_http_url("https://example.com/v1", allow_local=False)
    assert len(calls) == 1
    assert t.pinned_ip == "93.184.216.34"


def test_allow_local_rejects_mixed_loopback_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """allow_local must not allow a multi-A record carrying metadata merely because the first address is loopback."""
    from realmock.platform.core.security import is_safe_http_url

    monkeypatch.setattr(
        "realmock.platform.core.security.url._resolve_all",
        lambda host: [
            ipaddress.ip_address("127.0.0.1"),
            ipaddress.ip_address("169.254.169.254"),
        ],
    )
    assert is_safe_http_url("http://evil.example/v1", allow_local=True) is False
    with pytest.raises(UnsafeURLError):
        pin_safe_http_url("http://evil.example/v1", allow_local=True)


@pytest.mark.asyncio
async def test_transport_rewrites_host_to_pinned_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class _Inner(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured["host"] = request.url.host
            captured["header_host"] = request.headers.get("host")
            captured["sni"] = (request.extensions or {}).get("sni_hostname")
            return httpx.Response(200, json={"ok": True}, request=request)

    import realmock.platform.core.security.url as sec_url

    monkeypatch.setattr(sec_url.httpx, "AsyncHTTPTransport", lambda **kw: _Inner())
    transport = PinnedHostTransport(hostname="api.example.com", pinned_ip="1.2.3.4")
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await client.get("https://api.example.com/v1/models")
    assert resp.status_code == 200
    assert captured["host"] == "1.2.3.4"
    assert captured["header_host"] == "api.example.com"
    assert captured["sni"] == "api.example.com"
