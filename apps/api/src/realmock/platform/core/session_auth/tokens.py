"""Session capability-token primitives: generation / constant-time comparison / assertion.

Extracted from ``session_auth``; public symbols are still exported through ``session_auth``.
"""

from __future__ import annotations

import secrets
from typing import Any, Protocol

from realmock.platform.core.errors import ApiBusinessError, get_spec


class HasAccessToken(Protocol):
    access_token: Any


def new_access_token() -> str:
    """Generate session capability token (url-safe, ~32 bytes of entropy)."""
    return secrets.token_urlsafe(32)


def tokens_match(expected: str | None, provided: str | None) -> bool:
    """Constant time comparison; reject if either side is empty."""
    exp = (expected or "").strip()
    got = (provided or "").strip()
    if not exp or not got:
        return False
    if len(exp) != len(got):
        # compare_digest requires equal length; if the length is not equal, reject it directly (still avoid short circuit leakage of specific content)
        secrets.compare_digest(exp, exp)
        return False
    return secrets.compare_digest(exp, got)


def assert_session_token(
    session: HasAccessToken,
    provided: str | None,
    *,
    detail: str = "Don't have access to this interview session",
) -> None:
    """If verification fails, 403 will be thrown."""
    if not tokens_match(getattr(session, "access_token", None), provided):
        raise ApiBusinessError(get_spec("A0401"), message=detail)
