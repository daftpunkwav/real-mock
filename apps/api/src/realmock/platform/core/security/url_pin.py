"""URL DNS pinning: resolve once, then connect to a fixed IP to mitigate DNS-rebinding TOCTOU.

Extracted from :mod:`realmock.platform.core.security.url` (monkeypatch invariant: ``_resolve_all`` and policy
validation functions remain in ``url.py``, so tests patching ``url._resolve_all`` still reach them).
"""

from __future__ import annotations

import httpx
from dataclasses import dataclass
from typing import Any
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
        host = request.url.host
        if not host or host.lower() not in {
            self._hostname.lower(),
            self._pinned_ip.lower().strip("[]"),
        }:
            return await self._inner.handle_async_request(request)

        headers = httpx.Headers(request.headers)
        port = request.url.port
        if port and port not in (80, 443):
            headers["host"] = f"{self._hostname}:{port}"
        else:
            headers["host"] = self._hostname

        new_url = request.url.copy_with(host=self._pinned_ip)
        extensions = dict(request.extensions or {})
        extensions["sni_hostname"] = self._hostname

        pinned_request = httpx.Request(
            method=request.method,
            url=new_url,
            headers=headers,
            stream=request.stream,
            extensions=extensions,
        )
        return await self._inner.handle_async_request(pinned_request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def make_pinned_async_client(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    timeout: float = 60.0,
    allowed_ports: frozenset[int] | None = None,
    trusted_hosts: frozenset[str] | None = None,
) -> httpx.AsyncClient:
    """Create an :class:`httpx.AsyncClient` with DNS pinning for the host in ``url``."""
    from .url import pin_safe_http_url

    target = pin_safe_http_url(
        url,
        allow_local=allow_local,
        require_https=require_https,
        allowed_ports=allowed_ports,
        trusted_hosts=trusted_hosts,
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
