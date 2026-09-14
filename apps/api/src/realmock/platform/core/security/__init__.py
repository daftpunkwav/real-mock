"""Application-layer security helpers.

Preserve the backward-compatible import path: ``from realmock.platform.core.security import ...``

Split submodules:

- :mod:`file` — filename sanitization, path-traversal defense, extension/magic-number validation
- :mod:`url` — URL/SSRF filtering, DNS pinning, secure HTTP client
- :mod:`redact` — API Key redaction
"""

from .file import assert_within_dir, sanitize_filename, sniff_extension
from .redact import redact_api_key
from .url import (
    FAKEIP_ALLOWED_HOSTS,
    PinnedHostTransport,
    PinnedHttpTarget,
    UnsafeURLError,
    assert_safe_http_url,
    is_localhost_family,
    is_safe_http_url,
    make_pinned_async_client,
    pin_safe_http_url,
)

__all__ = [
    "FAKEIP_ALLOWED_HOSTS",
    "PinnedHostTransport",
    "PinnedHttpTarget",
    "UnsafeURLError",
    "assert_safe_http_url",
    "assert_within_dir",
    "is_localhost_family",
    "is_safe_http_url",
    "make_pinned_async_client",
    "pin_safe_http_url",
    "redact_api_key",
    "sanitize_filename",
    "sniff_extension",
]
