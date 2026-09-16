"""OpenAI-compatible LLM client (BYOK).

Changes:

- ``from_db`` automatically decrypts the encrypted ``api_key`` stored in the database;
- Validate ``api_base`` for safety on every request (SSRF defense, with dev/prod behavior controlled by settings);
- chat 180s / chat_message 90s timeouts;
- Redact API Keys in error logs;
- Do not retry 4xx; automatically retry 429/5xx with exponential backoff (3 attempts by default).

Assembly lives in :mod:`from_db`, openai_chat transport in :mod:`openai_transport`,
streaming retries in :mod:`retry_stream`, and protocol translation in :mod:`protocol_translate`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL
from realmock.platform.core.security import (
    UnsafeURLError,
    is_safe_http_url,
)
from realmock.platform.capabilities.ai.llm.defaults import DEFAULT_MAX_OUTPUT_TOKENS
from realmock.platform.capabilities.ai.llm.usage import UsageAccumulator

from .base import _extract_message_text, _is_local_allowed, _require_https
from .from_db import build_from_db, build_from_stage_config
from .openai_transport import build_payload, chat_completions
from .retry_stream import stream_message_round_retry, stream_text_retry

if TYPE_CHECKING:
    from .unified_client import UnifiedLLMClient

logger = logging.getLogger(__name__)


class LLMClient:
    """Supports BYOK client in OpenAI Chat Completions format."""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        protocol: str = DEFAULT_LLM_PROTOCOL,
        reasoning_effort: str | None = None,
        context_window: int = 0,
        supports_vision: bool = False,
        usage_sink: UsageAccumulator | None = None,
        full_url: bool = False,
        extra_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.protocol = protocol
        self.reasoning_effort = reasoning_effort
        # Full-URL providers: api_base is the verbatim endpoint, protocol path appending is skipped.
        self.full_url = bool(full_url)
        # Vendor-specific request customization from model-entry extras (any standard key wins replacement).
        self.extra_body = dict(extra_body) if extra_body else {}
        self.extra_headers = dict(extra_headers) if extra_headers else {}
        # Context window for model entry declaration; 0 = unknown (caller falls back on its own)
        self.context_window = max(0, int(context_window or 0))
        self.supports_vision = bool(supports_vision)
        # Usage accumulation: client instance life cycle = one business request, read usage as the total usage in this round
        self.usage = usage_sink if usage_sink is not None else UsageAccumulator()
        # When the supplier rejects stream_options, it is set to False and will no longer be carried in subsequent streaming requests.
        self._stream_usage_disabled = False

    @classmethod
    def from_db(
        cls,
        db: Session,
        *,
        profile_id: int | None = None,
        reasoning_effort: str | None = None,
    ) -> "LLMClient":
        """Build from the model entry system (default task binding or scene-level ``profile_id`` override)."""
        return build_from_db(
            cls, db, profile_id=profile_id, reasoning_effort=reasoning_effort
        )

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        stream: bool = False,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        return build_payload(
            self.model,
            messages,
            temperature,
            self.max_tokens,
            self.reasoning_effort,
            stream=stream,
            response_format=response_format,
            tools=tools,
            max_tokens_override=max_tokens,
            extra_body=self.extra_body or None,
        )

    def _safe_check(self) -> None:
        if not is_safe_http_url(self.api_base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"LLM api_base is not secure: {self.api_base}")

    def _endpoint(self, path: str) -> str:
        """Full-URL providers use api_base verbatim; otherwise the protocol path is appended."""
        return self.api_base if self.full_url else f"{self.api_base}{path}"

    def _delegate(self) -> "UnifiedLLMClient":
        from .unified_client import UnifiedLLMClient

        return UnifiedLLMClient(
            api_base=self.api_base,
            api_key=self.api_key,
            model=self.model,
            protocol=self.protocol,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort,
            usage_sink=self.usage,
            full_url=self.full_url,
            extra_body=self.extra_body or None,
            extra_headers=self.extra_headers or None,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        system: str | None = None,
        purpose: str | None = None,
    ) -> str:
        """Sends a Chat Completions request and returns text content.

        ``system`` (when given) is prepended as a system message — the native
        OpenAI shape, so stable prefixes keep prefix-caching. ``purpose`` is
        observability-only (debug log, never sent to the provider).
        """
        if purpose:
            logger.debug("LLM chat purpose=%s model=%s", purpose, self.model)
        payload_messages = list(messages or [])
        if system:
            payload_messages = [{"role": "system", "content": system}, *payload_messages]
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            return await self._delegate().chat(payload_messages, temperature=temperature, response_format=response_format, tools=tools)
        self._safe_check()
        url = self._endpoint("/chat/completions")
        payload = self._build_payload(
            payload_messages,
            temperature,
            response_format=response_format,
            tools=tools,
            max_tokens=max_tokens,
        )
        data = await chat_completions(
            api_base=self.api_base,
            api_key=self.api_key,
            url=url,
            payload=payload,
            timeout=180.0,
            log_label="LLM chat",
            model=self.model,
            extra_headers=self.extra_headers or None,
        )
        msg = data["choices"][0]["message"]
        self.usage.record_response(data, self.protocol)
        return _extract_message_text(msg)

    async def chat_message(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send Chat Completions and return the complete message object (including tool_calls)."""
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            message = await self._delegate().chat_message(
                messages, temperature=temperature, response_format=response_format, tools=tools, tool_choice=tool_choice
            )
            if not message.get("tool_calls"):
                message.pop("tool_calls", None)
            return message
        self._safe_check()
        url = self._endpoint("/chat/completions")
        payload = self._build_payload(
            messages, temperature, response_format=response_format, tools=tools
        )
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        data = await chat_completions(
            api_base=self.api_base,
            api_key=self.api_key,
            url=url,
            payload=payload,
            timeout=90.0,
            log_label="LLM chat_message",
            model=self.model,
            extra_headers=self.extra_headers or None,
        )
        msg = data["choices"][0]["message"]
        self.usage.record_response(data, self.protocol)
        result: dict[str, Any] = {
            "role": msg.get("role") or "assistant",
            "content": msg.get("content"),
        }
        if msg.get("tool_calls"):
            result["tool_calls"] = msg["tool_calls"]
        # The thinking process (reasoning_content) is only returned with the message for display, and is not written into the message sequence.
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        if isinstance(reasoning, str) and reasoning.strip():
            from realmock.platform.core.prompts import strip_emojis

            result["reasoning"] = strip_emojis(reasoning)
        return result

    async def chat_message_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming call for one tool-loop round: emit reasoning deltas immediately, buffering body/tool calls for assembly.

        Emits ``{"type": "reasoning", "text": ...}`` delta events, raw
        ``{"type": "text", "text": ...}`` body-delta events, then finally
        ``{"type": "message", "message": {...}}`` (with the same shape as non-streaming ``chat_message``).
        Used by the Agent loop: the reasoning process remains visible in real time, avoiding a silent connection during long non-streaming reasoning.
        Retries 429/5xx/connection errors with exponential backoff if no delta has yet been emitted.
        """
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            async for event in self._delegate().chat_message_stream(
                messages, temperature=temperature, tools=tools
            ):
                yield event
            return
        self._safe_check()
        url = self._endpoint("/chat/completions")
        payload = self._build_payload(messages, temperature, stream=True, tools=tools)
        if not self._stream_usage_disabled:
            payload["stream_options"] = {"include_usage": True}
        async for event in stream_message_round_retry(
            self, self.api_base, self.api_key, self.model, url, payload
        ):
            yield event

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.75,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Streaming returns token."""
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            async for token in self._delegate().chat_stream(
                messages, tools=tools
            ):
                yield token
            return
        self._safe_check()
        url = self._endpoint("/chat/completions")
        payload = self._build_payload(messages, temperature, stream=True, tools=tools)
        if not self._stream_usage_disabled:
            # Request the supplier to return usage (last chunk); if rejected, downgrade according to the response
            payload["stream_options"] = {"include_usage": True}
        async for token in stream_text_retry(
            self, self.api_base, self.api_key, self.model, url, payload
        ):
            yield token

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Request a response in JSON format and parse it (see :mod:`json_response` for implementation)."""
        from .json_response import parse_chat_json

        return await parse_chat_json(self.chat, messages, temperature, max_tokens)

    async def test_connection(self) -> tuple[bool, str]:
        """Test API connectivity (see :mod:`llm_client_ext` for implementation)."""
        return await _llm_ext.test_connection(self)

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Call the OpenAI-compatible /embeddings endpoint and return the vector for each text segment (implementation in :mod:`llm_client_ext`)."""
        return await _llm_ext.embed(self, texts, model=model)

    @classmethod
    def from_stage_config(cls, config: dict[str, Any]) -> "LLMClient":
        """Build the client from stage config (stage_tests for connectivity testing)."""
        return build_from_stage_config(cls, config)


from . import llm_client_ext as _llm_ext  # noqa: E402 — Import after class definition, one-way dependency on ext during runtime
