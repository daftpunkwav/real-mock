"""OpenAI Chat Completions transport: request execution, JSON-output parse repair, and embeddings calls.

LLMClient uses this module when ``protocol == openai_chat``; SSRF checks are completed before the
call (and are not repeated here), while retries consistently use ``base._retry_request``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.security import (
    make_pinned_async_client,
    redact_api_key,
)
from realmock.platform.core.secrets import LegacySecretFormatError, decrypt_secret

from .base import _is_local_allowed, _require_https, _retry_request

logger = logging.getLogger(__name__)


def build_payload(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    reasoning_effort: str | None,
    stream: bool = False,
    response_format: dict[str, str] | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tokens_override: int | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens_override if max_tokens_override is not None else max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    if response_format:
        payload["response_format"] = response_format
    if tools:
        payload["tools"] = tools
    if reasoning_effort:
        payload["reasoning_effort"] = (
            "high" if reasoning_effort == "max" else reasoning_effort
        )
    # Vendor-specific request-body customization: model-entry extras (extra_body) win over
    # every standard key, so any provider field can be set from the settings page.
    if extra_body:
        payload.update(extra_body)
        # Newer providers deprecate ``max_tokens`` for ``max_completion_tokens``; when a
        # vendor overrides the field, the legacy key must leave the payload entirely.
        if "max_completion_tokens" in payload:
            payload.pop("max_tokens", None)
    return payload


def chat_completions_headers(api_key: str, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


async def chat_completions(
    *,
    api_base: str,
    api_key: str,
    url: str,
    payload: dict[str, Any],
    timeout: float,
    log_label: str,
    model: str,
    extra_headers: dict[str, str] | None = None,
    usage: Any = None,
) -> dict[str, Any]:
    """POST Chat Completions and return JSON; retry semantics for 4xx/429/5xx are defined in base.

    ``usage`` (optional :class:`UsageAccumulator`) receives request diagnostics:
    latency, upstream request-id headers, and the last error summary.
    """
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=timeout
    ) as client:
        try:
            if usage is not None:
                usage.note_request_start()
            resp = await _retry_request(
                lambda: client.post(
                    url, headers=chat_completions_headers(api_key, extra_headers), json=payload
                )
            )
            resp.raise_for_status()
            if usage is not None:
                usage.note_response_meta(getattr(resp, "headers", None))
            return resp.json()
        except httpx.HTTPStatusError as e:
            if usage is not None:
                usage.note_response_meta(getattr(e.response, "headers", None))
                usage.note_request_error(e)
            logger.warning(
                "%s failed: model=%s status=%s key=%s",
                log_label,
                model,
                e.response.status_code,
                redact_api_key(api_key),
            )
            raise
        except BaseException as e:
            if usage is not None:
                usage.note_request_error(e)
            raise


def strip_code_fences(text: str) -> str:
    """Strip away the Markdown code fences that LLM might have wrapped around JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def repair_common_json_errors(text: str) -> str:
    """Repair common syntax errors in LLM-generated JSON.

    - Remove trailing commas at the end of objects/arrays;
    - Escape raw control characters inside strings (newlines/tabs, etc. <0x20) as \\n / \\t.
    Track string boundaries character by character; preserve content outside strings unchanged.
    """
    out: list[str] = []
    in_str = False
    escape = False
    n = len(text)
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_str = False
                out.append(ch)
                continue
            if ord(ch) < 0x20:
                out.append("\\n" if ch == "\n" else "\\t" if ch == "\t" else "\\r" if ch == "\r" else f"\\u{ord(ch):04x}")
                continue
            out.append(ch)
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            continue
        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                continue  # Trailing commas, discarded
        out.append(ch)
    return "".join(out)


async def embed_texts(
    *,
    texts: list[str],
    model: str | None,
    api_base: str,
    api_key: str,
) -> list[list[float]]:
    """Call the OpenAI compatible /embeddings endpoint to return a vector for each piece of text."""
    settings = get_settings()
    base = settings.effective_embeddings_base
    url = f"{base}/embeddings"
    payload: dict[str, Any] = {
        "model": model or settings.effective_embeddings_model,
        "input": texts,
    }
    raw_embed = settings.effective_embeddings_key
    try:
        embed_key = (decrypt_secret(raw_embed) if raw_embed else None)
        if not embed_key:
            embed_key = decrypt_secret(api_key) if api_key else ""
    except LegacySecretFormatError as e:
        logger.error("Embeddings API Key uses the old encryption format, please save again: %s", e)
        raise
    except ValueError as e:
        logger.error("Embeddings API Key decryption failed, request aborted (plaintext will not be rolled back): %s", e)
        raise
    headers = {
        "Authorization": f"Bearer {embed_key}",
        "Content-Type": "application/json",
    }
    async with make_pinned_async_client(
        base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=60.0
    ) as client:
        try:
            resp = await _retry_request(
                lambda: client.post(url, headers=headers, json=payload)
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "LLM embed failed: model=%s status=%s key=%s",
                payload["model"],
                e.response.status_code,
                redact_api_key(embed_key),
            )
            raise

    return [item["embedding"] for item in data["data"]]


__all__ = [
    "build_payload",
    "chat_completions_headers",
    "chat_completions",
    "strip_code_fences",
    "repair_common_json_errors",
    "embed_texts",
]
