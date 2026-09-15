"""Unified client tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/unified_client.py.

Covers: init/stage-config construction, safe-check, URL/payload delegation and
chat/chat_message/stream dispatch including stream-options fallback.

Conventions: no real network (httpx/pinned client mocked); asyncio_mode=auto.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from realmock.platform.capabilities.ai.llm.client import unified_client as uc_mod
from realmock.platform.capabilities.ai.llm.client.streaming import _StreamOptionsUnsupported
from realmock.platform.capabilities.ai.llm.usage import UsageAccumulator
from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL, LLMProtocol
from realmock.platform.core.secrets import LegacySecretFormatError
from realmock.platform.core.security import UnsafeURLError


def _client(**kw: Any) -> uc_mod.UnifiedLLMClient:
    args: dict[str, Any] = {
        "api_base": "https://api.test/v1/",
        "api_key": "k",
        "model": "m",
        "protocol": LLMProtocol.OPENAI_CHAT,
    }
    args.update(kw)
    return uc_mod.UnifiedLLMClient(**args)


def test_init_strips_and_defaults() -> None:
    c = uc_mod.UnifiedLLMClient(api_base="https://x/v1/", api_key="k", model="m")
    assert c.api_base == "https://x/v1"
    assert c.protocol == DEFAULT_LLM_PROTOCOL
    assert c.reasoning_effort is None
    assert isinstance(c.usage, UsageAccumulator)
    assert c._stream_usage_disabled is False
    sink = UsageAccumulator()
    c2 = uc_mod.UnifiedLLMClient(
        api_base="https://x", api_key="k", model="m", reasoning_effort="", usage_sink=sink
    )
    assert c2.usage is sink
    assert c2.reasoning_effort is None


def test_from_stage_config_plain() -> None:
    c = uc_mod.UnifiedLLMClient.from_stage_config(
        {"api_base": "https://x", "api_key": "plain", "model": "m"}
    )
    assert c.api_key == "plain"
    assert c.api_base == "https://x"


def test_from_stage_config_enc_success() -> None:
    with patch.object(uc_mod, "decrypt_secret", return_value="dec"):
        c = uc_mod.UnifiedLLMClient.from_stage_config(
            {"api_base": "https://x", "api_key": "enc:abc", "model": "m"}
        )
    assert c.api_key == "dec"


def test_from_stage_config_legacy_error() -> None:
    with patch.object(uc_mod, "decrypt_secret", side_effect=LegacySecretFormatError("old")):
        c = uc_mod.UnifiedLLMClient.from_stage_config(
            {"api_base": "https://x", "api_key": "enc:old", "model": "m"}
        )
    assert c.api_key == ""


def test_from_stage_config_value_error() -> None:
    with patch.object(uc_mod, "decrypt_secret", side_effect=ValueError("bad")):
        c = uc_mod.UnifiedLLMClient.from_stage_config(
            {"api_base": "https://x", "api_key": "enc:bad", "model": "m"}
        )
    assert c.api_key == ""


def test_from_stage_config_defaults() -> None:
    c = uc_mod.UnifiedLLMClient.from_stage_config({})
    assert c.api_base == ""
    assert c.protocol == DEFAULT_LLM_PROTOCOL


def test_safe_check_ok_and_fail() -> None:
    c = _client()
    with patch.object(uc_mod, "is_safe_http_url", return_value=True):
        c._safe_check()
    with (
        patch.object(uc_mod, "is_safe_http_url", return_value=False),
        pytest.raises(UnsafeURLError),
    ):
        c._safe_check()


def test_build_url_and_payload_delegates() -> None:
    c = _client()
    with patch.object(uc_mod, "build_request", return_value=("u", {"p": 1})) as br:
        url, payload = c._build_url_and_payload([{"role": "user", "content": "hi"}])
    assert (url, payload) == ("u", {"p": 1})
    assert br.called


@pytest.mark.asyncio
async def test_chat_delegates_with_purpose() -> None:
    c = _client()
    with patch.object(uc_mod, "_chat", new=AsyncMock(return_value="hi")) as m:
        out = await c.chat([{"role": "user", "content": "hi"}], purpose="test")
    assert out == "hi"
    assert m.await_count == 1


@pytest.mark.asyncio
async def test_test_connection_and_chat_message_delegate() -> None:
    c = _client()
    with patch.object(uc_mod, "_test_connection", new=AsyncMock(return_value=(True, "ok"))) as m:
        assert await c.test_connection() == (True, "ok")
        assert m.await_count == 1
    with patch.object(uc_mod, "_chat_message", new=AsyncMock(return_value={"role": "a"})) as m2:
        assert await c.chat_message([{"role": "user", "content": "hi"}]) == {"role": "a"}
        assert m2.await_count == 1


@pytest.mark.asyncio
async def test_chat_message_stream_responses_not_implemented() -> None:
    c = _client(protocol=LLMProtocol.OPENAI_RESPONSES)
    with pytest.raises(NotImplementedError):
        async for _ in c.chat_message_stream([{"role": "user", "content": "hi"}]):
            pass


async def _collect(agen: Any) -> list[Any]:
    return [x async for x in agen]


@pytest.mark.asyncio
async def test_chat_message_stream_success_adds_stream_options() -> None:
    c = _client()
    c._safe_check = MagicMock()  # type: ignore[method-assign]
    seen: dict[str, Any] = {}

    async def _fake(client: Any, api_base: str, protocol: str, api_key: str, url: str, payload: Any) -> Any:
        seen.update(payload)
        yield {"type": "message", "message": {"role": "assistant", "content": "hi"}}
        return
        yield  # make it an async generator

    with (
        patch.object(uc_mod, "build_request", return_value=("https://u", {"model": "m"})),
        patch.object(uc_mod, "stream_message_round", side_effect=_fake),
    ):
        events = await _collect(c.chat_message_stream([{"role": "user", "content": "hi"}]))
    assert events[0]["message"]["content"] == "hi"
    assert seen.get("stream_options") == {"include_usage": True}


@pytest.mark.asyncio
async def test_chat_message_stream_fallback_on_unsupported() -> None:
    c = _client()
    c._safe_check = MagicMock()  # type: ignore[method-assign]
    calls = {"n": 0}

    async def _fake(client: Any, api_base: str, protocol: str, api_key: str, url: str, payload: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _StreamOptionsUnsupported("stream_options rejected")
        yield {"type": "message", "message": {"role": "assistant", "content": "ok"}}
        return
        yield

    with (
        patch.object(uc_mod, "build_request", return_value=("https://u", {"model": "m"})),
        patch.object(uc_mod, "stream_message_round", side_effect=_fake),
    ):
        events = await _collect(c.chat_message_stream([{"role": "user", "content": "hi"}]))
    assert events[0]["message"]["content"] == "ok"
    assert c._stream_usage_disabled is True
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_chat_message_stream_anthropic_no_stream_options() -> None:
    c = _client(protocol=LLMProtocol.ANTHROPIC_MESSAGES)
    c._safe_check = MagicMock()  # type: ignore[method-assign]
    seen: dict[str, Any] = {}

    async def _fake(client: Any, api_base: str, protocol: str, api_key: str, url: str, payload: Any) -> Any:
        seen.update(payload)
        yield {"type": "message", "message": {"role": "assistant", "content": "a"}}
        return
        yield

    with (
        patch.object(uc_mod, "build_request", return_value=("https://u", {"model": "m"})),
        patch.object(uc_mod, "stream_message_round", side_effect=_fake),
    ):
        await _collect(c.chat_message_stream([{"role": "user", "content": "hi"}]))
    assert "stream_options" not in seen


@pytest.mark.asyncio
async def test_chat_stream_success_and_fallback() -> None:
    c = _client()
    c._safe_check = MagicMock()  # type: ignore[method-assign]

    async def _ok(client: Any, api_base: str, protocol: str, api_key: str, url: str, payload: Any) -> Any:
        yield "hi"
        return
        yield

    with (
        patch.object(uc_mod, "build_request", return_value=("https://u", {"model": "m"})),
        patch.object(uc_mod, "stream_text_payload", side_effect=_ok),
    ):
        assert await _collect(c.chat_stream([{"role": "user", "content": "hi"}])) == ["hi"]

    # Fallback path: first raises, second yields.
    c2 = _client()
    c2._safe_check = MagicMock()  # type: ignore[method-assign]
    calls = {"n": 0}

    async def _flaky(client: Any, api_base: str, protocol: str, api_key: str, url: str, payload: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _StreamOptionsUnsupported("no stream_options")
        yield "ok"
        return
        yield

    with (
        patch.object(uc_mod, "build_request", return_value=("https://u", {"model": "m"})),
        patch.object(uc_mod, "stream_text_payload", side_effect=_flaky),
    ):
        assert await _collect(c2.chat_stream([{"role": "user", "content": "hi"}])) == ["ok"]
    assert c2._stream_usage_disabled is True
