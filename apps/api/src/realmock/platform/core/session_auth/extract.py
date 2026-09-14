"""Extract session capability tokens for HTTP (Header > Cookie > query) and WebSocket.

Extracted from ``session_auth``; public symbols are still exported centrally by ``session_auth``.
"""

from __future__ import annotations

import logging

from fastapi import Header, Query, Request, WebSocket

from realmock.platform.config import get_settings
from realmock.platform.core.session_auth.cookies import CookieScope, cookie_name
from realmock.platform.core.session_auth.csrf import assert_csrf_if_cookie_only

logger = logging.getLogger(__name__)

HEADER_NAME = "X-Interview-Token"
# WebSocket sub-protocol prefix: mock.<token> (token is url-safe)
WS_SUBPROTOCOL_PREFIX = "mock."


def _extract_from_request(
    request: Request,
    *,
    scope: CookieScope,
    session_id: int,
    x_interview_token: str | None,
    token: str | None,
) -> str | None:
    cookie_tok = (request.cookies.get(cookie_name(scope, session_id)) or "").strip()
    header_tok = (x_interview_token or "").strip()
    query_tok = (token or "").strip()
    if query_tok and get_settings().is_prod:
        logger.warning("The production environment rejects HTTP query token path=%s", request.url.path)
        query_tok = ""
    used_header = bool(header_tok)
    chosen = header_tok or cookie_tok or query_tok or None
    if chosen and cookie_tok and not header_tok:
        assert_csrf_if_cookie_only(request, used_header=False)
    elif chosen and not header_tok and not cookie_tok:
        # Query only: CSRF is also required (to prevent tokens from being exploited across sites after being logged)
        assert_csrf_if_cookie_only(request, used_header=False)
    elif chosen and used_header:
        pass
    return chosen or None


def extract_token(
    session_id: int,
    request: Request,
    x_interview_token: str | None = Header(default=None, alias=HEADER_NAME),
    token: str | None = Query(default=None, description="Session Capability Token (compatible; prod disabled)"),
) -> str | None:
    """HTTP dependencies for interviews / reports: Header > Cookie > query (no query in prod)."""
    return _extract_from_request(
        request,
        scope="iv",
        session_id=session_id,
        x_interview_token=x_interview_token,
        token=token,
    )


def extract_prep_token(
    session_id: int,
    request: Request,
    x_interview_token: str | None = Header(default=None, alias=HEADER_NAME),
    token: str | None = Query(default=None, description="Prep capability token (compatible; prod disabled)"),
) -> str | None:
    """Prep HTTP dependencies."""
    return _extract_from_request(
        request,
        scope="prep",
        session_id=session_id,
        x_interview_token=x_interview_token,
        token=token,
    )


def ws_token_subprotocol(token: str) -> str:
    """Constructs the WebSocket subprotocol name that carries the token."""
    return f"{WS_SUBPROTOCOL_PREFIX}{(token or '').strip()}"


def extract_ws_token(
    websocket: WebSocket,
    *,
    session_id: int | None = None,
    query_token: str | None = None,
) -> tuple[str, str | None]:
    """Extract the capability token from a WS handshake.

    Priority:
    1. Cookie ``iv_{session_id}`` (HttpOnly, same-origin/direct backend access)
    2. ``Sec-WebSocket-Protocol: mock.<token>`` (compatibility)
    3. query ``token=`` (non-production only; ignored in production to prevent log leakage)

    Returns:
        ``(access_token, chosen_subprotocol_or_None)``
        When the token came through a subprotocol, the second item is the complete subprotocol string for ``accept(subprotocol=...)``.
    """
    if session_id is not None:
        cookie_tok = (websocket.cookies.get(cookie_name("iv", session_id)) or "").strip()
        if cookie_tok:
            return cookie_tok, None

    header = websocket.headers.get("sec-websocket-protocol") or ""
    for part in header.split(","):
        p = part.strip()
        if not p:
            continue
        if p.lower().startswith(WS_SUBPROTOCOL_PREFIX):
            tok = p[len(WS_SUBPROTOCOL_PREFIX) :].strip()
            if tok:
                return tok, p
    q = (query_token or "").strip()
    if q and get_settings().is_prod:
        logger.warning("Production environment rejects WebSocket query token")
        return "", None
    return q, None
