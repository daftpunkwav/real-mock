"""Shared LLM client foundation: retries, text extraction, and environment checks.

Shared helpers extracted from the original ``client.py`` and ``unified_client.py``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.prompts import strip_emojis
from realmock.platform.capabilities.ai.llm.retry_policy import (
    RETRY_DELAYS,
    is_retryable_exception,
    is_retryable_status,
    sleep_retry,
)

logger = logging.getLogger(__name__)


class LLMUpstreamError(RuntimeError):
    """Upstream provider reported a business-level failure inside an HTTP-success body.

    MiniMax-style ``base_resp`` codes, Responses ``status=failed/incomplete``,
    and terminal SSE error events all surface here with their verbatim
    message so callers (and the user) can see the real cause instead of a
    generic failure — and the model can adapt (quota, rate limit, filter).
    """


def _extract_message_text(msg: dict[str, Any] | None) -> str:
    """Extract readable text from a Chat Completions message.

    Supports:
    - Standard string ``content``
    - Response text placed by some providers in ``reasoning_content`` / ``reasoning``
    - list-valued content (multiple text segments)

    Strip emoji before outbound use to prevent the model from ignoring system constraints.
    """
    if not msg or not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return strip_emojis(content)
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text") or ""))
            elif isinstance(p, str):
                parts.append(p)
        joined = "".join(parts).strip()
        if joined:
            return strip_emojis(joined)
    for key in ("reasoning_content", "reasoning", "output_text"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return strip_emojis(val)
    if isinstance(content, str):
        return strip_emojis(content)
    return ""


async def _retry_request(
    coro_factory,
    *,
    max_retries: int = len(RETRY_DELAYS),
    is_stream: bool = False,
) -> httpx.Response:
    """Retry 429/5xx and connection errors on the shared ladder; raise immediately for other 4xx.

    ``coro_factory`` is a no-argument callable that returns a new coroutine each time (avoiding multiple awaits on the same
    response). When ``is_stream=True``, the caller handles closing the stream. A provider
    ``Retry-After`` header overrides the ladder delay for the immediate retry.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        coro = coro_factory()
        try:
            resp = await coro
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response else 0
            if is_retryable_status(status_code):
                last_exc = e
                if attempt < max_retries:
                    if is_stream:
                        try:
                            await e.response.aclose()
                        except Exception:
                            logger.debug("Failed to close streaming response before retrying", exc_info=True)
                    await sleep_retry(attempt, headers=getattr(e.response, "headers", None))
                    continue
            raise
        except httpx.ReadTimeout:
            # Never retried: the request timeouts are minutes-scale, so a read
            # timeout means the provider is still generating, not down —
            # retrying would multiply an already-long wait (up to 4x) and is
            # the caller's decision to make with its own budget.
            raise
        except Exception as e:
            if is_retryable_exception(e):
                last_exc = e
                if attempt < max_retries:
                    await sleep_retry(attempt)
                    continue
            raise
        if is_retryable_status(resp.status_code):
            last_exc = httpx.HTTPStatusError(
                f"transient {resp.status_code}",
                request=resp.request,
                response=resp,
            )
            if attempt < max_retries:
                if is_stream:
                    try:
                        await resp.aclose()
                    except Exception:
                        logger.debug("Failed to close streaming response before retrying", exc_info=True)
                await sleep_retry(attempt, headers=getattr(resp, "headers", None))
                continue
            resp.raise_for_status()
        return resp
    assert last_exc is not None
    raise last_exc


def _is_local_allowed() -> bool:
    """Each request is recalculated to prevent module-level cached environment variables from failing to respond to test monkeypatch."""
    return bool(get_settings().allow_local_llm)


def _require_https() -> bool:
    """Enforce HTTPS outbound to production."""
    return bool(get_settings().is_prod)
