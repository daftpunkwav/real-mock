"""Cookie-only CSRF mitigation: validate the Origin / Referer allowlist.

Extracted from ``session_auth``; on the cookie-only authentication path,
``_extract_from_request`` calls :func:`assert_csrf_if_cookie_only`.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import Request

from realmock.platform.config import get_settings
from realmock.platform.core.errors import raise_error

logger = logging.getLogger(__name__)


def _origin_allowed(request: Request) -> bool:
    """Check whether Origin/Referer is in the CORS allowlist (CSRF mitigation for cookie authentication)."""
    allowed = {o.rstrip("/") for o in get_settings().cors_origin_list}
    if not allowed:
        return False
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin and origin in allowed:
        return True
    referer = (request.headers.get("referer") or "").strip()
    if referer:
        try:
            parsed = urlparse(referer)
            ref_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            if ref_origin in allowed:
                return True
        except Exception:
            # If parsing fails, it will be processed as rejected (safe default), and the original value will be recorded to facilitate troubleshooting of false rejections.
            logger.debug("Referer parsing failed and is treated as not in the whitelist: %r", referer, exc_info=True)
    return False


def assert_csrf_if_cookie_only(
    request: Request,
    *,
    used_header: bool,
) -> None:
    """Require Origin/Referer only for cookie authentication; Header tokens are treated as explicit capabilities (test-friendly)."""
    if used_header:
        return
    if request.method.upper() in ("GET", "HEAD", "OPTIONS"):
        return
    if not _origin_allowed(request):
        raise_error("A0403")
