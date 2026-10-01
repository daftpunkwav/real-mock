"""Hardening for local management API access.

Local management endpoints such as profiles / resumes / settings allow only loopback peers by default,
preventing arbitrary LAN clients from modifying BYOK configuration when ``HOST=0.0.0.0``.
"""

from __future__ import annotations

import ipaddress

from typing import Any

from fastapi import Depends, Request
from urllib.parse import urlparse

from realmock.platform.core.errors import raise_error
from realmock.platform.core.session_auth.csrf import is_origin_in_cors_allowlist


def _is_loopback_peer(peer: str) -> bool:
    """True for loopback peers, including IPv4-mapped ``::ffff:127.0.0.1`` forms."""
    try:
        ip = ipaddress.ip_address(peer.strip("[]"))
    except ValueError:
        return False
    if ip.is_loopback:
        return True
    # Dual-stack servers report IPv4 loopback peers as "::ffff:a.b.c.d";
    # that mapped address is loopback too.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped.is_loopback
    return False


def require_local_peer(  # noqa: B008 - WS scopes cannot inject Request; see docstring
    # None default serves direct WS-scope calls; a Request|None annotation would stop FastAPI injection.
    request: Request = None,  # type: ignore[assignment]
) -> None:
    """Allow direct loopback connections only; otherwise return 403.

    Starlette TestClient uses ``testclient`` as its peer and is always allowed.
    ``TEST_MODE=1`` does NOT bypass the loopback check: the flag only skips
    startup work, and an exported leftover variable must never expose
    management endpoints to the LAN (``env=prod`` never honored it either).

    WebSocket-scope dependencies cannot inject ``Request``, so this guard
    is called with ``request=None`` on WS endpoints; it short-circuits there —
    WS endpoints authenticate through session capability tokens instead.
    """
    if request is None:
        return
    # No client (such as specific ASGI scenarios) and empty host are also rejected, and the peer is always str.
    peer = (request.client.host if request.client else "") or ""
    if not peer:
        raise_error("A0405")
    if peer == "testclient":
        return
    if not _is_loopback_peer(peer):
        raise_error("A0405")


def reject_cross_site_fetch(  # noqa: B008 - WS scopes cannot inject Request; see docstring
    # None default serves direct WS-scope calls; a Request|None annotation would stop FastAPI injection.
    request: Request = None,  # type: ignore[assignment]
) -> None:
    """Reject browser-driven cross-site requests (``Sec-Fetch-Site: cross-site``) → A0403.

    Like :func:`require_local_peer`, this guard is HTTP-only; on WebSocket
    endpoints (``request=None``) it short-circuits.

    Loopback authentication also permits requests initiated by any webpage (because the peer is still 127.0.0.1).
    The practical threat is a malicious webpage driving local endpoints (render amplification / metadata probing / rate-limit lockout).
    Browsers always include ``Sec-Fetch-Site`` on subresource requests; non-browser clients (such as curl)
    do not send this header and are allowed through directly, preserving previous behavior.
    """
    if request is None:
        return
    site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if site == "cross-site":
        raise_error("A0403")


_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def require_same_origin_for_writes(  # noqa: B008 - WS scopes cannot inject Request; see docstring
    # None default serves direct WS-scope calls; a Request|None annotation would stop FastAPI injection.
    request: Request = None,  # type: ignore[assignment]
) -> None:
    """Reject browser writes whose Origin/Referer is not an allowlisted origin → A0403.

    :func:`reject_cross_site_fetch` cannot cover this: a page served from another
    localhost port is ``same-site`` (the scheme and port are ignored), and a
    body-less POST/DELETE is a CORS *simple request*, so no preflight runs and
    the side effect still executes. Endpoints that take no capability token had
    no CSRF control at all, while cookie-authenticated ones do (see
    :func:`realmock.platform.core.session_auth.csrf.assert_csrf_if_cookie_only`).

    Like the other guards this is HTTP-only (``request=None`` on WS scopes), and
    non-browser clients that send neither Origin nor Referer pass unchanged.
    """
    if request is None:
        return
    if request.method.upper() not in _UNSAFE_METHODS:
        return
    if not (request.headers.get("origin") or request.headers.get("referer")):
        return
    if not is_origin_in_cors_allowlist(request):
        raise_error("A0403")


# Unified access control for local management APIs (single truth for app/include_router level mounts):
# loopback authentication + browser cross-site rejection + same-origin writes.
# Each router no longer declares itself.
# Avoid missing new endpoints/services (historical lesson: Settings global and interview endpoints streak).
LOCAL_API_DEPENDENCIES: list = [
    Depends(require_local_peer),
    Depends(reject_cross_site_fetch),
    Depends(require_same_origin_for_writes),
]


async def guard_ws_origin(websocket: Any) -> bool:
    """Browser-driven cross-site WS handshakes → close before accept (A0403).

    Dependency guards cannot run on WebSocket scopes (FastAPI cannot inject
    ``Request`` there), so WS endpoints call this from the route body instead.
    Browsers always send ``Origin`` on WS handshakes; non-browser clients
    (curl / test probes) send none and pass — same semantics as the HTTP
    guard's treatment of curl. Session capability tokens remain the real auth.
    """
    origin = str(websocket.headers.get("origin") or "").strip()
    if not origin:
        return True
    hostname = (urlparse(origin).hostname or "").lower()
    if hostname == "testclient":
        return True
    # hostname is bracket-stripped by urlparse, so IPv6 loopback is "::1".
    if hostname in ("localhost", "::1"):
        return True
    try:
        host = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        await _close_ws_forbidden(websocket)
        return False
    if not host.is_loopback:
        await _close_ws_forbidden(websocket)
        return False
    return True


async def _close_ws_forbidden(websocket: Any) -> None:
    from starlette.websockets import WebSocketState

    code = 1008  # policy violation
    if websocket.client_state == WebSocketState.CONNECTING:
        await websocket.close(code=code)
        return
    if websocket.client_state == WebSocketState.CONNECTED:
        await websocket.close(code=code)
