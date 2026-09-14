"""Session Cookie utilities: naming / writing / clearing / Secure detection.

Extracted from ``session_auth``; public symbols are still exported centrally by ``session_auth``.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Request, Response

from realmock.platform.config import get_settings

CookieScope = Literal["iv", "prep"]
# Long-lived on purpose: capability cookies are the only access proof for history
# rows, and expiry orphans them (listed but permanently locked). 90 days bounds
# the window while surviving real-world gaps between visits.
COOKIE_MAX_AGE = 90 * 24 * 3600


def _peer_is_trusted_proxy(peer: str) -> bool:
    """Whether the directly connected peer falls within the CIDR of the trusted proxy (consistent with the semantics of the current limiting module)."""
    from realmock.platform.core.ratelimit import _peer_is_trusted_proxy as _rl_peer

    return _rl_peer(peer)


def cookie_name(scope: CookieScope, session_id: int) -> str:
    """Constructs the session cookie name."""
    return f"{scope}_{int(session_id)}"


def cookie_should_be_secure(request: Request) -> bool:
    """Whether to set Secure on the session Cookie.

    - ``COOKIE_SECURE=true/false`` explicitly overrides the default;
    - Otherwise: the request scheme is https, or the proxy is trusted and ``X-Forwarded-Proto=https``.
    """
    settings = get_settings()
    if settings.cookie_secure is True:
        return True
    if settings.cookie_secure is False:
        return False
    if request.url.scheme == "https":
        return True
    peer = request.client.host if request.client else None
    if peer and _peer_is_trusted_proxy(peer):
        proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        if proto == "https":
            return True
    return False


def set_session_cookie(
    response: Response,
    *,
    scope: CookieScope,
    session_id: int,
    token: str,
    secure: bool,
) -> None:
    """Write HttpOnly session cookie."""
    response.set_cookie(
        key=cookie_name(scope, session_id),
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def clear_session_cookie(
    response: Response,
    *,
    scope: CookieScope,
    session_id: int,
) -> None:
    response.delete_cookie(key=cookie_name(scope, session_id), path="/")
