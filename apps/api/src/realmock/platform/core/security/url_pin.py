"""URL DNS pinning: resolve once, then connect to a fixed IP to mitigate DNS-rebinding TOCTOU.

Extracted from :mod:`realmock.platform.core.security.url` (monkeypatch invariant: ``_resolve_all`` and policy
validation functions remain in ``url.py``, so tests patching ``url._resolve_all`` still reach them).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

# Do not import url.py at the top level of the module: this module will be imported at the end of url.py.
# Resolve pin_safe_http_url lazily inside make_pinned_async_client to avoid a circular import.


@dataclass(frozen=True)
class PinnedHttpTarget:
    """The connection target is locked after SSRF verification passes."""

    original_url: str
    hostname: str
    pinned_ip: str
    scheme: str
    port: int | None


def _pinned_request(
    request: httpx.Request,
    hostname: str,
    pinned_ip: str,
) -> httpx.Request | None:
    """Rewrite ``request`` onto the pinned IP, or return None when it is a different host."""
    host = request.url.host
    if not host or host.lower() not in {
        hostname.lower(),
        pinned_ip.lower().strip("[]"),
    }:
        return None

    headers = httpx.Headers(request.headers)
    port = request.url.port
    if port and port not in (80, 443):
        headers["host"] = f"{hostname}:{port}"
    else:
        headers["host"] = hostname

    extensions = dict(request.extensions or {})
    extensions["sni_hostname"] = hostname
    return httpx.Request(
        method=request.method,
        url=request.url.copy_with(host=pinned_ip),
        headers=headers,
        stream=request.stream,
        extensions=extensions,
    )


class PinnedHostTransport(httpx.AsyncBaseTransport):
    """Rewrite the hostname in the request to the pinned IP and keep the Host/SNI."""

    def __init__(
        self,
        hostname: str,
        pinned_ip: str,
        **transport_kwargs: Any,
    ) -> None:
        self._hostname = hostname
        self._pinned_ip = pinned_ip
        self._inner = httpx.AsyncHTTPTransport(**transport_kwargs)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        pinned = _pinned_request(request, self._hostname, self._pinned_ip)
        if pinned is None:
            return await self._inner.handle_async_request(request)
        return await self._inner.handle_async_request(pinned)

    async def aclose(self) -> None:
        await self._inner.aclose()


class PinnedHostSyncTransport(httpx.BaseTransport):
    """Synchronous twin of :class:`PinnedHostTransport`."""

    def __init__(
        self,
        hostname: str,
        pinned_ip: str,
        **transport_kwargs: Any,
    ) -> None:
        self._hostname = hostname
        self._pinned_ip = pinned_ip
        self._inner = httpx.HTTPTransport(**transport_kwargs)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        pinned = _pinned_request(request, self._hostname, self._pinned_ip)
        if pinned is None:
            return self._inner.handle_request(request)
        return self._inner.handle_request(pinned)

    def close(self) -> None:
        self._inner.close()


def make_pinned_async_client(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    timeout: float = 60.0,
    allowed_ports: frozenset[int] | None = None,
) -> httpx.AsyncClient:
    """Create an :class:`httpx.AsyncClient` with DNS pinning for the host in ``url``."""
    from .url import pin_safe_http_url

    target = pin_safe_http_url(
        url,
        allow_local=allow_local,
        require_https=require_https,
        allowed_ports=allowed_ports,
    )
    transport = PinnedHostTransport(
        hostname=target.hostname,
        pinned_ip=target.pinned_ip,
    )
    return httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
    )


def make_pinned_client(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    timeout: float = 60.0,
    allowed_ports: frozenset[int] | None = None,
) -> httpx.Client:
    """Synchronous :class:`httpx.Client` with the same DNS pin as :func:`make_pinned_async_client`.

    Redirects stay off: a 3xx must not escape the pin onto a different host.
    """
    from .url import pin_safe_http_url

    target = pin_safe_http_url(
        url,
        allow_local=allow_local,
        require_https=require_https,
        allowed_ports=allowed_ports,
    )
    transport = PinnedHostSyncTransport(
        hostname=target.hostname,
        pinned_ip=target.pinned_ip,
    )
    return httpx.Client(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
    )
