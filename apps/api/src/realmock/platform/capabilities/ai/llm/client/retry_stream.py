"""LLMClient's OpenAI-compatible streaming execution: retries + stream_options fallback.

Shared by ``chat_message_stream`` (tool rounds) and ``chat_stream`` (text deltas):
- Do not retry 4xx (if stream_options is explicitly rejected, remove that field and replay);
- Retry 429/5xx / connection errors with exponential backoff before any delta is emitted (3 attempts by default);
- If failure occurs after a delta is emitted, raise immediately (retrying cannot repair a partial stream).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from realmock.platform.core.security import make_pinned_async_client

from .assemblers import _OpenAIRoundAssembler
from .base import _is_local_allowed, _require_https
from .openai_transport import chat_completions_headers
from ..stream_filters import StreamSanitizer

logger = logging.getLogger(__name__)

_RETRYABLE_CONNECTION_ERRORS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)


async def stream_message_round_retry(
    client: Any,
    api_base: str,
    api_key: str,
    model: str,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Streaming tool loop (OpenAI Chat compatible): emit reasoning and raw content deltas immediately, assemble the message at the end.

    Retry 429/5xx/connection errors with exponential backoff if no delta has been emitted; when the
    endpoint rejects ``stream_options``, set ``_stream_usage_disabled``, remove that field, and replay.
    """
    headers = chat_completions_headers(api_key)
    max_retries = 3
    backoff = 0.5
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
    ) as c:
        for attempt in range(max_retries + 1):
            assembler = _OpenAIRoundAssembler()
            emitted = False
            try:
                async with c.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code in (400, 422) and "stream_options" in payload:
                        body = (await resp.aread()).decode("utf-8", "ignore")
                        if "stream_options" in body:
                            client._stream_usage_disabled = True
                            logger.info(
                                "LLM streaming endpoint rejects stream_options and will no longer carry them: model=%s",
                                model,
                            )
                            payload.pop("stream_options", None)
                            if attempt < max_retries:
                                continue
                    # First judge 429/5xx and try again, then unify raise_for_status——4xx without retry,
                    # 429/5xx is thrown when retries are exhausted (same semantics as base._retry_request)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        if attempt < max_retries:
                            await asyncio.sleep(backoff * (2**attempt))
                            continue
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        client.usage.record_stream_event(chunk, client.protocol)
                        reasoning = assembler.feed(chunk)
                        if reasoning:
                            emitted = True
                            yield {"type": "reasoning", "text": reasoning}
                        # Speculative streaming: raw body-text deltas (consumers
                        # sanitize their own channel; assembly is unaffected).
                        text = assembler.drain_content()
                        if text:
                            emitted = True
                            yield {"type": "text", "text": text}
                    yield {"type": "message", "message": assembler.message()}
                    return
            except _RETRYABLE_CONNECTION_ERRORS:
                if emitted or attempt >= max_retries:
                    raise
                await asyncio.sleep(backoff * (2**attempt))


async def stream_text_retry(
    client: Any,
    api_base: str,
    api_key: str,
    model: str,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[str]:
    """Stream sanitized text tokens (OpenAI Chat compatible).

    Retry 429/5xx/connection errors with exponential backoff if no token has been emitted; rebuild the sanitizer for each attempt,
    discarding any partial special-token buffer and <think> open/close state left by the previous failed attempt.
    """
    headers = chat_completions_headers(api_key)
    max_retries = 3
    backoff = 0.5
    last_exc: Exception | None = None
    tokens_yielded = False
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=120.0
    ) as c:
        for attempt in range(max_retries + 1):
            # sanitizer rebuilds according to attempt: discards the last remaining data when retrying fails.
            # Half special token buffering and <think> opening and closing status to avoid polluting new streams
            sanitizer = StreamSanitizer()
            try:
                async with c.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code in (400, 422) and "stream_options" in payload:
                        # The supplier does not support stream_options: visible downgrade (logging) and then remove and retry.
                        body = (await resp.aread()).decode("utf-8", "ignore")
                        if "stream_options" in body:
                            client._stream_usage_disabled = True
                            logger.info(
                                "LLM streaming endpoint rejects stream_options and will no longer carry them: model=%s",
                                model,
                            )
                            payload.pop("stream_options", None)
                            if attempt < max_retries:
                                continue
                    # Check 429/5xx for retries first, then call raise_for_status consistently (as in stream_message_round_retry)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        last_exc = httpx.HTTPStatusError(
                            f"transient {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(backoff * (2**attempt))
                            continue
                        raise last_exc
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            client.usage.record_stream_event(chunk, client.protocol)
                            delta = chunk["choices"][0].get("delta", {})
                            if not isinstance(delta, dict):
                                continue
                            reasoning = (
                                delta.get("reasoning_content")
                                or delta.get("reasoning")
                                or ""
                            )
                            token = delta.get("content") or ""
                            if isinstance(reasoning, str) and reasoning:
                                cleaned_r = sanitizer.feed_reasoning(reasoning)
                                if cleaned_r:
                                    tokens_yielded = True
                                    yield cleaned_r
                            if isinstance(token, str) and token:
                                cleaned = sanitizer.feed_content(token)
                                if cleaned:
                                    tokens_yielded = True
                                    yield cleaned
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                    tail = sanitizer.flush()
                    if tail:
                        tokens_yielded = True
                        yield tail
                    return
            except _RETRYABLE_CONNECTION_ERRORS as e:
                if tokens_yielded:
                    raise
                last_exc = e
                if attempt < max_retries:
                    await asyncio.sleep(backoff * (2**attempt))
                    continue
                raise
        if last_exc is not None:
            raise last_exc


__all__ = ["stream_message_round_retry", "stream_text_retry"]
