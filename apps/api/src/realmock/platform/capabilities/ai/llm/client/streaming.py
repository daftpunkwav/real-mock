"""Streaming transport execution: SSE parsing, usage collection, and the stream_options downgrade signal.

The unified client (unified_client) and OpenAI-compatible client (llm_client) share this
streaming request execution layer; fallback when an endpoint explicitly rejects ``stream_options``
is centralized here. Streams retry on the shared ladder (429/5xx/connection errors) until the
first delta is emitted — after that a partial stream is unrecoverable and errors surface.
Terminal provider error events raise :class:`LLMUpstreamError` with the verbatim message.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from realmock.platform.core.prompts import strip_emojis
from realmock.platform.core.security import make_pinned_async_client
from realmock.platform.capabilities.ai.llm.retry_policy import (
    RETRY_DELAYS,
    is_retryable_exception,
    is_retryable_status,
    sleep_retry,
)

from .assemblers import _AnthropicRoundAssembler, _OpenAIRoundAssembler, _ResponsesRoundAssembler
from .base import LLMUpstreamError, _is_local_allowed, _require_https
from .protocol_utils import _headers
from .response_extract import parse_sse_event
from ..stream_filters import StreamSanitizer

logger = logging.getLogger(__name__)


class _StreamOptionsUnsupported(Exception):
    """Streaming endpoints explicitly reject ``stream_options`` (400/422 for the request body, with an error message naming the field)."""


async def _open_stream_with_retry(
    client: Any,
    c: Any,
    url: str,
    payload: dict[str, Any],
    protocol: str,
    api_key: str,
    usage: Any,
) -> tuple[Any, Any]:
    """Open one SSE stream, retrying 429/5xx/connection failures on the shared ladder.

    Returns ``(ctx, resp)``: the async context manager and the entered response.
    The caller must leave the stream via ``ctx.__aexit__`` (an httpx Response is
    not itself a context manager). Only non-retryable statuses come back; 4xx
    bodies — the stream_options downgrade signal — are the caller's business.
    """
    last_exc: Exception | None = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        if usage is not None:
            usage.note_request_start()
        ctx = c.stream(
            "POST",
            url,
            headers=_headers(api_key, protocol, getattr(client, "extra_headers", None)),
            json=payload,
        )
        try:
            # The connection opens on __aenter__, which returns the live response.
            resp = await ctx.__aenter__()
        except Exception as e:
            if usage is not None:
                usage.note_request_error(e)
            if is_retryable_exception(e) and attempt < len(RETRY_DELAYS):
                last_exc = e
                await sleep_retry(attempt)
                continue
            raise
        if usage is not None:
            usage.note_response_meta(getattr(resp, "headers", None))
        if is_retryable_status(resp.status_code) and attempt < len(RETRY_DELAYS):
            last_exc = httpx.HTTPStatusError(
                f"transient {resp.status_code}",
                request=resp.request,
                response=resp,
            )
            await ctx.__aexit__(None, None, None)
            await sleep_retry(attempt, headers=getattr(resp, "headers", None))
            continue
        return ctx, resp
    assert last_exc is not None
    raise last_exc


async def stream_message_round(
    client: Any,
    api_base: str,
    protocol: str,
    api_key: str,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Execute one streaming tool round: emit reasoning and raw content deltas immediately, yield the assembled message at the end.

    Used by ``chat_message_stream``; if the endpoint rejects ``stream_options``, raise
    :class:`_StreamOptionsUnsupported` so the caller can remove that field and replay.
    """
    if protocol == "anthropic_messages":
        assembler: Any = _AnthropicRoundAssembler()
    elif protocol == "openai_responses":
        assembler = _ResponsesRoundAssembler()
    else:
        assembler = _OpenAIRoundAssembler()
    usage = getattr(client, "usage", None)
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
    ) as c:
        ctx, resp = await _open_stream_with_retry(client, c, url, payload, protocol, api_key, usage)
        try:
            if "stream_options" in payload and resp.status_code in (400, 422):
                body = (await resp.aread()).decode("utf-8", "ignore")
                if "stream_options" in body:
                    raise _StreamOptionsUnsupported(body[:120])
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                client.usage.record_stream_event(event, protocol)
                reasoning = strip_emojis(assembler.feed(event))
                if reasoning:
                    yield {"type": "reasoning", "text": reasoning}
                # Speculative streaming: surface buffered content deltas so callers can
                # forward body text live (raw; consumers sanitize their own channel).
                text = assembler.drain_content()
                if text:
                    yield {"type": "text", "text": text}
        except (asyncio.CancelledError, GeneratorExit):
            await ctx.__aexit__(None, None, None)
            raise
        except BaseException as e:
            if usage is not None:
                usage.note_request_error(e)
            await ctx.__aexit__(type(e), e, e.__traceback__)
            raise
        else:
            await ctx.__aexit__(None, None, None)
    if assembler.terminal_error:
        if usage is not None:
            usage.note_request_error(LLMUpstreamError(assembler.terminal_error))
        raise LLMUpstreamError(assembler.terminal_error)
    yield {"type": "message", "message": assembler.message()}


async def stream_text_payload(
    client: Any,
    api_base: str,
    protocol: str,
    api_key: str,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[str]:
    """Execute one streaming request and yield sanitized text deltas (including usage collection).

    Used by ``chat_stream``; when the endpoint rejects ``stream_options``, raise
    :class:`_StreamOptionsUnsupported` so the caller can remove the field and replay the request.
    """
    sanitizer = StreamSanitizer()
    usage = getattr(client, "usage", None)
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
    ) as c:
        ctx, resp = await _open_stream_with_retry(client, c, url, payload, protocol, api_key, usage)
        try:
            if "stream_options" in payload and resp.status_code in (400, 422):
                body = (await resp.aread()).decode("utf-8", "ignore")
                if "stream_options" in body:
                    raise _StreamOptionsUnsupported(body[:120])
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                client.usage.record_stream_event(event, protocol)
                token, reasoning = parse_sse_event(event, protocol)
                if reasoning:
                    cleaned = sanitizer.feed_reasoning(reasoning)
                    if cleaned:
                        yield cleaned
                if token:
                    cleaned = sanitizer.feed_content(token)
                    if cleaned:
                        yield cleaned
            tail = sanitizer.flush()
            if tail:
                yield tail
        except (asyncio.CancelledError, GeneratorExit):
            await ctx.__aexit__(None, None, None)
            raise
        except BaseException as e:
            if usage is not None:
                usage.note_request_error(e)
            await ctx.__aexit__(type(e), e, e.__traceback__)
            raise
        else:
            await ctx.__aexit__(None, None, None)


__all__ = ["_StreamOptionsUnsupported", "stream_message_round", "stream_text_payload"]
