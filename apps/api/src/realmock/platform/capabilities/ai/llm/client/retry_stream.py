"""LLMClient's OpenAI-compatible streaming execution: retries + stream_options fallback.

Shared by ``chat_message_stream`` (tool rounds) and ``chat_stream`` (text deltas):
- Do not retry 4xx (if stream_options is explicitly rejected, remove that field and replay);
- Retry 429/5xx / connection errors on the shared retry ladder (see ``retry_policy``) until the
  first delta is emitted; a provider ``Retry-After`` header overrides the ladder delay;
- If failure occurs after a delta is emitted, raise immediately (retrying cannot repair a partial stream).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from realmock.platform.capabilities.ai.llm.retry_policy import (
    RETRY_DELAYS,
    is_retryable_status,
    sleep_retry,
)
from realmock.platform.core.security import make_pinned_async_client

from ..stream_filters import StreamSanitizer
from .assemblers import _OpenAIRoundAssembler
from .base import LLMUpstreamError, _is_local_allowed, _require_https
from .openai_transport import chat_completions_headers

logger = logging.getLogger(__name__)


async def stream_message_round_retry(
    client: Any,
    api_base: str,
    api_key: str,
    model: str,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Streaming tool loop (OpenAI Chat compatible): emit reasoning and raw content deltas immediately, assemble the message at the end.

    Retry 429/5xx/connection errors on the shared ladder if no delta has been emitted; when the
    endpoint rejects ``stream_options``, set ``_stream_usage_disabled``, remove that field, and replay.
    """
    headers = chat_completions_headers(api_key, getattr(client, "extra_headers", None))
    usage = getattr(client, "usage", None)
    # Keep DNS resolution off the event loop (same convention as web_fetch).
    pinned = await asyncio.to_thread(
        make_pinned_async_client,
        api_base,
        allow_local=_is_local_allowed(),
        require_https=_require_https(),
        timeout=180.0,
    )
    async with pinned as c:
        attempt = 0
        while True:
            assembler = _OpenAIRoundAssembler()
            emitted = False
            if usage is not None:
                # Anchor per attempt (same semantics as streaming's
                # _open_stream_with_retry): a retried stream then reports the
                # successful attempt's latency, not the retry ladder's wait.
                usage.note_request_start()
            try:
                async with c.stream("POST", url, headers=headers, json=payload) as resp:
                    if usage is not None:
                        usage.note_response_diagnostics(getattr(resp, "headers", None))
                    if resp.status_code in (400, 422) and "stream_options" in payload:
                        body = (await resp.aread()).decode("utf-8", "ignore")
                        if "stream_options" in body:
                            client._stream_usage_disabled = True
                            logger.info(
                                "LLM streaming endpoint rejects stream_options and will no longer carry them: model=%s",
                                model,
                            )
                            payload.pop("stream_options", None)
                            if attempt < len(RETRY_DELAYS):
                                attempt += 1
                                continue
                    # First judge 429/5xx and try again, then unify raise_for_status——4xx without retry,
                    # 429/5xx is thrown when retries are exhausted (same semantics as base._retry_request)
                    if is_retryable_status(resp.status_code):
                        if attempt < len(RETRY_DELAYS):
                            await sleep_retry(attempt, headers=getattr(resp, "headers", None))
                            attempt += 1
                            continue
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
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
                    if assembler.terminal_error:
                        if usage is not None:
                            usage.note_request_error(LLMUpstreamError(assembler.terminal_error))
                        raise LLMUpstreamError(assembler.terminal_error)
                    yield {"type": "message", "message": assembler.message()}
                    return
            except (asyncio.CancelledError, GeneratorExit):
                raise
            except _RETRYABLE_CONNECTION_ERRORS as e:
                if usage is not None:
                    usage.note_request_error(e)
                if emitted or attempt >= len(RETRY_DELAYS):
                    raise
                await sleep_retry(attempt)
                attempt += 1


async def stream_text_retry(
    client: Any,
    api_base: str,
    api_key: str,
    model: str,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[str]:
    """Stream sanitized text tokens (OpenAI Chat compatible).

    Retry 429/5xx/connection errors on the shared ladder if no token has been emitted; rebuild the sanitizer for each attempt,
    discarding any partial special-token buffer and <think> open/close state left by the previous failed attempt.
    """
    headers = chat_completions_headers(api_key, getattr(client, "extra_headers", None))
    usage = getattr(client, "usage", None)
    tokens_yielded = False
    # Keep DNS resolution off the event loop (same convention as web_fetch).
    pinned = await asyncio.to_thread(
        make_pinned_async_client,
        api_base,
        allow_local=_is_local_allowed(),
        require_https=_require_https(),
        timeout=120.0,
    )
    async with pinned as c:
        attempt = 0
        while True:
            # Fresh sanitizer per attempt: leftover partial-token buffers and
            # <think> open/close state from a failed attempt must not bleed
            # into the retry stream.
            sanitizer = StreamSanitizer()
            if usage is not None:
                # Anchor per attempt (same semantics as streaming's
                # _open_stream_with_retry): a retried stream then reports the
                # successful attempt's latency, not the retry ladder's wait.
                usage.note_request_start()
            try:
                async with c.stream("POST", url, headers=headers, json=payload) as resp:
                    if usage is not None:
                        usage.note_response_diagnostics(getattr(resp, "headers", None))
                    if resp.status_code in (400, 422) and "stream_options" in payload:
                        # Supplier rejects stream_options: log the downgrade,
                        # drop the option, and retry without it.
                        body = (await resp.aread()).decode("utf-8", "ignore")
                        if "stream_options" in body:
                            client._stream_usage_disabled = True
                            logger.info(
                                "LLM streaming endpoint rejects stream_options and will no longer carry them: model=%s",
                                model,
                            )
                            payload.pop("stream_options", None)
                            if attempt < len(RETRY_DELAYS):
                                attempt += 1
                                continue
                    # Check 429/5xx for retries first, then call raise_for_status consistently (as in stream_message_round_retry)
                    if is_retryable_status(resp.status_code):
                        if attempt < len(RETRY_DELAYS):
                            await sleep_retry(attempt, headers=getattr(resp, "headers", None))
                            attempt += 1
                            continue
                        raise httpx.HTTPStatusError(
                            f"transient {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            client.usage.record_stream_event(chunk, client.protocol)
                            delta = chunk["choices"][0].get("delta", {})
                            if not isinstance(delta, dict):
                                continue
                            reasoning = (
                                delta.get("reasoning_content") or delta.get("reasoning") or ""
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
            except (asyncio.CancelledError, GeneratorExit):
                raise
            except _RETRYABLE_CONNECTION_ERRORS as e:
                if usage is not None:
                    usage.note_request_error(e)
                if tokens_yielded:
                    raise
                if attempt < len(RETRY_DELAYS):
                    await sleep_retry(attempt)
                    attempt += 1
                    continue
                raise


# ReadTimeout is deliberately absent (same policy as base._retry_request): a
# read timeout on a minutes-scale request means the provider is still
# generating, and retrying would multiply the wait — the caller decides.
_RETRYABLE_CONNECTION_ERRORS = (
    httpx.ConnectError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)


__all__ = ["stream_message_round_retry", "stream_text_retry"]
