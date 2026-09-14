"""Streaming transport execution: SSE parsing, usage collection, and the stream_options downgrade signal.

The unified client (unified_client) and OpenAI-compatible client (llm_client) share this
streaming request execution layer; fallback when an endpoint explicitly rejects ``stream_options`` is centralized here.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any


from realmock.platform.core.prompts import strip_emojis
from realmock.platform.core.security import make_pinned_async_client

from .assemblers import _AnthropicRoundAssembler, _OpenAIRoundAssembler
from .base import _is_local_allowed, _require_https
from .protocol_utils import _headers
from .response_extract import parse_sse_event
from ..stream_filters import StreamSanitizer

logger = logging.getLogger(__name__)


class _StreamOptionsUnsupported(Exception):
    """Streaming endpoints explicitly reject ``stream_options`` (400/422 for the request body, with an error message naming the field)."""


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
    else:
        assembler = _OpenAIRoundAssembler()
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
    ) as c:
        async with c.stream(
            "POST", url, headers=_headers(api_key, protocol), json=payload
        ) as resp:
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
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
    ) as c:
        async with c.stream(
            "POST", url, headers=_headers(api_key, protocol), json=payload
        ) as resp:
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


__all__ = ["_StreamOptionsUnsupported", "stream_message_round", "stream_text_payload"]
