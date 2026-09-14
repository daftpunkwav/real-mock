"""Session capability token.

This local-first product does not introduce multi-user login; mutating operations (WS / start / message / finish /
messages / reports / prep) require the ``access_token`` issued at creation, preventing session hijacking using only an integer
session_id.

Issued through an HttpOnly Cookie by default (``iv_{id}`` / ``prep_{id}``);
the ``X-Interview-Token`` Header remains supported for tests and migration.
Production rejects query ``?token=`` to prevent proxy/access-log leakage.

The implementation is split into sibling submodules by responsibility; this module re-exports public symbols:

- ``session_auth.tokens``: generation / constant-time comparison / assertion
- ``session_auth.cookies``: cookie naming / writing / clearing / Secure determination
- ``session_auth.extract``: HTTP / WebSocket token extraction
- ``session_auth.csrf``: cookie-only CSRF / Origin validation
"""

from __future__ import annotations

from realmock.platform.core.session_auth.cookies import (
    COOKIE_MAX_AGE,
    CookieScope,
    clear_session_cookie,
    cookie_name,
    cookie_should_be_secure,
    set_session_cookie,
)
from realmock.platform.core.session_auth.extract import (
    HEADER_NAME,
    WS_SUBPROTOCOL_PREFIX,
    _extract_from_request,
    extract_prep_token,
    extract_token,
    extract_ws_token,
    ws_token_subprotocol,
)
from realmock.platform.core.session_auth.tokens import (
    HasAccessToken,
    assert_session_token,
    new_access_token,
    tokens_match,
)

__all__ = [
    "HEADER_NAME",
    "WS_SUBPROTOCOL_PREFIX",
    "COOKIE_MAX_AGE",
    "CookieScope",
    "HasAccessToken",
    "cookie_name",
    "new_access_token",
    "tokens_match",
    "assert_session_token",
    "cookie_should_be_secure",
    "set_session_cookie",
    "clear_session_cookie",
    "extract_token",
    "extract_prep_token",
    "extract_ws_token",
    "ws_token_subprotocol",
    "_extract_from_request",
]
