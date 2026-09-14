"""HTTP layer for GitHub REST calls: constants and error-shape mapping.

Extracted from :mod:`...github.client`; ``GitHubClient._get`` delegates thinly to :func:`async_get`.
``httpx`` is imported once at module level, so tests patching ``client.httpx.AsyncClient`` still
reach it in this module.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 20.0
# The upper limit of the body of a single response to prevent the README/file from being too large and overwhelming the context
MAX_TEXT_CHARS = 12_000
#: Total attempts per GET (one initial try plus one bounded retry).
_MAX_ATTEMPTS = 2
#: Upper bound for a single rate-limit wait: longer waits would stall agent
#: turns past tool timeouts, so anything beyond this degrades to an explicit
#: ``rate_limited`` observation instead of sleeping.
_MAX_WAIT_SEC = 5.0
#: Remaining-quota floor below which batch callers should shed heavy calls.
LOW_QUOTA_REMAINING = 50

#: Best-effort last-seen quota (single process only; multi-worker setups must
#: treat it as advisory — the settings Test button always reads live).
_LAST_QUOTA: dict[str, Any] = {}


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _quota_from_headers(headers: Any) -> dict[str, Any]:
    """Extract rate-limit quota from response headers (empty when absent)."""
    if headers is None:
        return {}
    get = headers.get if hasattr(headers, "get") else (lambda k, d=None: d)
    quota: dict[str, Any] = {}
    remaining = _as_int(get("x-ratelimit-remaining"))
    reset = _as_int(get("x-ratelimit-reset"))
    retry_after = _as_int(get("retry-after"))
    if remaining is not None:
        quota["remaining"] = remaining
    if reset is not None:
        quota["reset_in"] = max(0, reset - int(time.time()))
    if retry_after is not None:
        quota["retry_after"] = max(0, retry_after)
    limit = _as_int(get("x-ratelimit-limit"))
    if limit is not None:
        quota["limit"] = limit
    return quota


def record_quota(headers: Any) -> dict[str, Any]:
    """Remember the last-seen quota headers (advisory, process-local)."""
    quota = _quota_from_headers(headers)
    if quota:
        _LAST_QUOTA.clear()
        _LAST_QUOTA.update(quota)
    return quota


def get_last_quota() -> dict[str, Any]:
    """Last-seen quota headers (empty when no GitHub call ran yet)."""
    return dict(_LAST_QUOTA)


def _rate_limit_markers(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        marker in lowered
        for marker in ("rate limit", "rate_limit", "ratelimit", "quota", "abuse")
    )


async def async_get(
    path: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """GET ``path`` and map error cases (404/403/429/>=400/empty body/JSON failure).

    Rate-limit responses (429, or 403 carrying a rate-limit signature) wait
    once when the hinted delay fits the turn budget, otherwise degrade to an
    explicit ``rate_limited`` observation — never an unbounded sleep, never a
    silent cut. Genuine 403s (permissions) return immediately as before.
    """
    url = f"{GITHUB_API}{path}"
    last: Any = {"error": "http_error", "status": 0, "message": "no response"}
    for attempt in range(_MAX_ATTEMPTS):
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=headers or {}, params=params or {})
        quota = record_quota(getattr(resp, "headers", None))
        if resp.status_code == 404:
            return {"error": "not_found", "path": path, "status": 404}
        if resp.status_code == 429 or (
            resp.status_code == 403
            and (_rate_limit_markers(resp.text) or quota.get("remaining") == 0)
        ):
            wait_hint = quota.get("retry_after")
            if wait_hint is None and quota.get("reset_in") is not None:
                wait_hint = quota["reset_in"]
            if wait_hint is None:
                wait_hint = _MAX_WAIT_SEC
            last = {
                "error": "rate_limited",
                "status": resp.status_code,
                "message": resp.text[:300],
                "retry_after": quota.get("retry_after"),
                "reset_in": quota.get("reset_in"),
                "remaining": quota.get("remaining"),
            }
            if attempt + 1 < _MAX_ATTEMPTS and 0 < wait_hint <= _MAX_WAIT_SEC:
                logger.warning(
                    "GitHub rate-limited %s; waiting %.0fs before one retry", path, wait_hint
                )
                await asyncio.sleep(wait_hint)
                continue
            return last
        if resp.status_code == 403:
            return {
                "error": "forbidden_or_rate_limited",
                "status": 403,
                "message": resp.text[:300],
            }
        if resp.status_code >= 400:
            return {
                "error": "http_error",
                "status": resp.status_code,
                "message": resp.text[:300],
            }
        # empty body
        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception:
            text = resp.text
            return {"raw": text[:MAX_TEXT_CHARS]}
    return last
