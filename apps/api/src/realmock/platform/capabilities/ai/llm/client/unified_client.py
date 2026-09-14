"""Unified multi-protocol client: supports chat completions / anthropic messages / responses.

Protocol request-body construction lives in :mod:`protocol_translate`, response parsing in :mod:`response_extract`,
streaming execution in :mod:`streaming`, incremental assemblers in :mod:`assemblers`, and non-streaming endpoints
(chat / test_connection / chat_message) in :mod:`chat_endpoints`; this module retains only
client state, SSRF checks, URL+payload construction, and streaming orchestration.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL, LLMProtocol
from realmock.platform.capabilities.ai.llm.defaults import DEFAULT_MAX_OUTPUT_TOKENS
from realmock.platform.core.security import (
    UnsafeURLError,
    is_safe_http_url,
)
from realmock.platform.core.secrets import LegacySecretFormatError, decrypt_secret
from realmock.platform.capabilities.ai.llm.usage import UsageAccumulator

from .base import _is_local_allowed, _require_https
from .chat_endpoints import chat as _chat
from .chat_endpoints import chat_message as _chat_message
from .chat_endpoints import test_connection as _test_connection
from .protocol_translate import build_request
from .streaming import _StreamOptionsUnsupported, stream_message_round, stream_text_payload

logger = logging.getLogger(__name__)


class UnifiedLLMClient:
    """Select the correct API path and payload format based on the protocol field."""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        protocol: str = DEFAULT_LLM_PROTOCOL,
        max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        reasoning_effort: str | None = None,
        usage_sink: UsageAccumulator | None = None,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.protocol = protocol
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort or None
        # Usage accumulation: self-built by default (used independently), sharing the same sink when delegated by LLMClient
        self.usage = usage_sink if usage_sink is not None else UsageAccumulator()
        self._stream_usage_disabled = False

    @classmethod
    def from_stage_config(cls, config: dict[str, Any]) -> "UnifiedLLMClient":
        api_key = config.get("api_key") or ""
        if api_key.startswith("enc:"):
            try:
                api_key = decrypt_secret(api_key) or ""
            except LegacySecretFormatError as e:
                logger.error("API Key uses the old encryption format, please save again: %s", e)
                api_key = ""
            except ValueError as e:
                logger.error("API Key decryption failed: %s", e)
                api_key = ""
        return cls(
            api_base=config.get("api_base") or "",
            api_key=api_key,
            model=config.get("model") or "",
            protocol=config.get("protocol") or DEFAULT_LLM_PROTOCOL,
            max_tokens=config.get("max_tokens") or DEFAULT_MAX_OUTPUT_TOKENS,
        )

    def _safe_check(self) -> None:
        if not is_safe_http_url(self.api_base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"LLM api_base is not secure: {self.api_base}")

    def _build_url_and_payload(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        stream: bool = False,
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        return build_request(
            self.protocol,
            self.api_base,
            self.model,
            self.max_tokens,
            self.reasoning_effort,
            messages,
            system=system,
            stream=stream,
            temperature=temperature,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        purpose: str | None = None,
    ) -> str:
        """Non-streaming text replies (see :mod:`chat_endpoints` for implementation).

        ``purpose`` is observability-only (debug log, never sent to the provider).
        """
        if purpose:
            logger.debug("LLM chat purpose=%s model=%s", purpose, self.model)
        return await _chat(
            self,
            messages,
            system=system,
            temperature=temperature,
            response_format=response_format,
            tools=tools,
        )

    async def test_connection(self) -> tuple[bool, str]:
        """Test API connectivity (see :mod:`chat_endpoints` for implementation)."""
        return await _test_connection(self)

    async def chat_message(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return text and normalized function tool calls (implemented in :mod:`chat_endpoints`)."""
        return await _chat_message(
            self,
            messages,
            system=system,
            temperature=temperature,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
        )

    async def chat_message_stream(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream one tool-loop round: emit reasoning deltas in real time, buffering body/tool calls for assembly.

        Emits ``{"type": "reasoning", "text": ...}`` delta events, raw
        ``{"type": "text", "text": ...}`` body-delta events, then finally
        ``{"type": "message", "message": {...}}`` (with the same shape as non-streaming ``chat_message``;
        reasoning has already been sent in real time and is not included again). Raises :class:`NotImplementedError`
        when the openai_responses protocol is unsupported, allowing the caller to fall back to non-streaming.
        """
        if self.protocol == LLMProtocol.OPENAI_RESPONSES:
            raise NotImplementedError("responses protocol does not support streaming toolwheel")
        self._safe_check()
        url, payload = self._build_url_and_payload(
            messages, system=system, stream=True, temperature=temperature, tools=tools
        )
        if self.protocol == LLMProtocol.OPENAI_CHAT and not self._stream_usage_disabled:
            payload["stream_options"] = {"include_usage": True}
        try:
            async for event in stream_message_round(
                self, self.api_base, self.protocol, self.api_key, url, payload
            ):
                yield event
            return
        except _StreamOptionsUnsupported:
            self._stream_usage_disabled = True
            logger.info(
                "LLM streaming endpoint rejects stream_options and will no longer carry them: model=%s", self.model
            )
            payload.pop("stream_options", None)
            async for event in stream_message_round(
                self, self.api_base, self.protocol, self.api_key, url, payload
            ):
                yield event

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Parse text deltas from SSE for all three protocols.

        Wrap reasoning deltas (Anthropic ``thinking_delta`` / OpenAI ``reasoning_content``)
        uniformly in ``<think>...</think>``; pass response text through ``StreamSanitizer`` to
        strip template tokens.
        """
        self._safe_check()
        url, payload = self._build_url_and_payload(
            messages,
            system=system,
            stream=True,
            temperature=temperature,
            tools=tools,
        )
        if self.protocol == LLMProtocol.OPENAI_CHAT and not self._stream_usage_disabled:
            # Request the supplier to return usage (last chunk); if rejected, downgrade according to the response
            payload["stream_options"] = {"include_usage": True}
        try:
            async for piece in stream_text_payload(
                self, self.api_base, self.protocol, self.api_key, url, payload
            ):
                yield piece
        except _StreamOptionsUnsupported:
            self._stream_usage_disabled = True
            logger.info(
                "LLM streaming endpoint rejects stream_options and will no longer carry them: model=%s", self.model
            )
            payload.pop("stream_options", None)
            async for piece in stream_text_payload(
                self, self.api_base, self.protocol, self.api_key, url, payload
            ):
                yield piece
