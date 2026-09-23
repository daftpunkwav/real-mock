"""Shared LLM retry policy: attempt schedule and Retry-After handling.

One policy for every outbound LLM call (non-streaming requests, streaming
requests before the first delta, and embedding calls), so a provider blip is
absorbed identically everywhere. Delays follow a doubled pair ladder
(10/10/20/20/40/40/80/80/100/100 seconds, capped at 100s) for up to 10
retries. When the upstream response carries a ``Retry-After`` header, that
value wins for the immediate retry — the provider knows its own recovery
time better than our ladder does.
"""

from __future__ import annotations

import asyncio
import logging
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: Per-retry wait seconds; index = retry attempt (0-based). Ten retries max.
RETRY_DELAYS: tuple[float, ...] = (10, 10, 20, 20, 40, 40, 80, 80, 100, 100)

#: Hard ceiling for a provider-requested wait, so a hostile header cannot
#: stall a turn for minutes.
MAX_RETRY_AFTER_SECONDS = 300.0


def retry_delay(attempt: int, retry_after: float | None = None) -> float:
    """Wait seconds for the given 0-based retry attempt."""
    if retry_after is not None and retry_after > 0:
        return min(retry_after, MAX_RETRY_AFTER_SECONDS)
    if 0 <= attempt < len(RETRY_DELAYS):
        return RETRY_DELAYS[attempt]
    return RETRY_DELAYS[-1]


def parse_retry_after(headers: Any) -> float | None:
    """Best-effort ``Retry-After`` parse (delta-seconds or HTTP-date); None when absent."""
    if headers is None:
        return None
    try:
        raw = headers.get("retry-after")
    except Exception:
        return None
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(text)
        import datetime as _dt

        now = _dt.datetime.now(_dt.timezone.utc)
        return max(0.0, (target - now).total_seconds())
    except Exception:
        return None


async def sleep_retry(
    attempt: int,
    *,
    headers: Any = None,
    retry_after: float | None = None,
) -> float:
    """Sleep before the given retry attempt; returns the waited seconds."""
    delay = retry_delay(attempt, retry_after if retry_after is not None else parse_retry_after(headers))
    logger.info("LLM request retrying in %.0fs (attempt %d)", delay, attempt + 1)
    await asyncio.sleep(delay)
    return delay


def is_retryable_status(status_code: int) -> bool:
    """429 and 5xx are transient; everything else fails fast."""
    return status_code == 429 or status_code >= 500


def is_retryable_exception(exc: BaseException) -> bool:
    """Connection-level failures are transient; ReadTimeout never is (the
    provider is still generating — retrying would multiply the wait)."""
    if isinstance(exc, httpx.ReadTimeout):
        return False
    return isinstance(exc, (httpx.ConnectError, httpx.WriteError, httpx.RemoteProtocolError))


__all__ = [
    "MAX_RETRY_AFTER_SECONDS",
    "RETRY_DELAYS",
    "is_retryable_exception",
    "is_retryable_status",
    "parse_retry_after",
    "retry_delay",
    "sleep_retry",
]
