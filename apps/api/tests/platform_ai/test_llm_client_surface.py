"""LLM client surface tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/llm_client.py.

Covers: init normalization, from_db/from_stage_config delegation, safe-check and
usage-shared chat/payload delegation.

Conventions: no real network (httpx/pinned client mocked); asyncio_mode=auto.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from realmock.platform.capabilities.ai.llm.client import llm_client as lc_mod
from realmock.platform.capabilities.ai.llm.client.llm_client import LLMClient
from realmock.platform.capabilities.ai.llm.usage import UsageAccumulator
from realmock.platform.core.constants import LLMProtocol
from realmock.platform.core.security import UnsafeURLError


def _client(**kw: Any) -> LLMClient:
    args: dict[str, Any] = {"api_base": "https://api.test/v1/", "api_key": "sk-test-key", "model": "m"}
    args.update(kw)
    return LLMClient(**args)


def test_init_normalizes() -> None:
    c = LLMClient(api_base="https://x/v1/", api_key="k", model="m", context_window=-5, supports_vision=1)
    assert c.api_base == "https://x/v1"
    assert c.context_window == 0
    assert c.supports_vision is True
    assert isinstance(c.usage, UsageAccumulator)
    assert c._stream_usage_disabled is False
    sink = UsageAccumulator()
    c2 = LLMClient(api_base="https://x", api_key="k", model="m", usage_sink=sink, reasoning_effort="high")
    assert c2.usage is sink
    assert c2.reasoning_effort == "high"


def test_from_db_delegates() -> None:
    with patch.object(lc_mod, "build_from_db", return_value="BUILT") as m:
        out = LLMClient.from_db(MagicMock(), profile_id=1, reasoning_effort="high")
    assert out == "BUILT"
    assert m.called


def test_build_payload_delegates() -> None:
    c = _client()
    with patch.object(lc_mod, "build_payload", return_value={"ok": 1}) as m:
        assert c._build_payload([{"role": "user", "content": "hi"}], 0.5) == {"ok": 1}
        assert m.called


def test_safe_check() -> None:
    c = _client()
    with patch.object(lc_mod, "is_safe_http_url", return_value=True):
        c._safe_check()
    with (
        patch.object(lc_mod, "is_safe_http_url", return_value=False),
        pytest.raises(UnsafeURLError),
    ):
        c._safe_check()


def test_delegate_shares_usage() -> None:
    c = _client()
    d = c._delegate()
    assert d.usage is c.usage
    assert d.api_base == c.api_base
    assert d.protocol == c.protocol


@pytest.mark.asyncio
async def test_chat_openai_success() -> None:
    c = _client()
    with (
        patch.object(lc_mod, "is_safe_http_url", return_value=True),
        patch.object(lc_mod, "build_payload", return_value={"model": "m"}),
        patch.object(
            lc_mod,
            "chat_completions",
            new=AsyncMock(
                return_value={
                    "choices": [{"message": {"content": "hi"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            ),
        ),
    ):
        text = await c.chat([{"role": "user", "content": "hi"}], purpose="t", system="sys")
    assert text == "hi"


@pytest.mark.asyncio
async def test_chat_system_prepend_and_max_tokens() -> None:
    c = _client()
    seen: dict[str, Any] = {}
    orig_build = lc_mod.build_payload

    def _capture(model: Any, messages: Any, *a: Any, **k: Any) -> Any:
        seen["messages"] = messages
        return orig_build(model, messages, *a, **k)

    with (
        patch.object(lc_mod, "is_safe_http_url", return_value=True),
        patch.object(lc_mod, "build_payload", side_effect=_capture),
        patch.object(
            lc_mod,
            "chat_completions",
            new=AsyncMock(return_value={"choices": [{"message": {"content": "ok"}}]}),
        ),
    ):
        await c.chat([{"role": "user", "content": "hi"}], system="SYS", max_tokens=5)
    assert seen["messages"][0] == {"role": "system", "content": "SYS"}


@pytest.mark.asyncio
async def test_chat_delegates_for_non_default_protocol() -> None:
    c = _client(protocol=LLMProtocol.ANTHROPIC_MESSAGES)
    delegate = MagicMock()
    delegate.chat = AsyncMock(return_value="delegated")
    with patch.object(LLMClient, "_delegate", return_value=delegate):
        assert await c.chat([{"role": "user", "content": "hi"}]) == "delegated"


@pytest.mark.asyncio
async def test_chat_blocks_unsafe() -> None:
    c = _client()
    with patch.object(lc_mod, "is_safe_http_url", return_value=False):
        with pytest.raises(UnsafeURLError):
            await c.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_chat_api_key_redacted_in_error_log(caplog: pytest.LogCaptureFixture) -> None:
    """End-to-end via real openai_transport: 500 error log must redact the full key."""
    import realmock.platform.capabilities.ai.llm.client.openai_transport as ot_mod

    c = LLMClient(api_base="https://api.test/v1", api_key="sk-test-1234567890abcdef", model="m")
    http = AsyncMock()
    err_resp = MagicMock(spec=httpx.Response)
    err_resp.status_code = 500
    err_resp.request = MagicMock()
    err_resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=err_resp)
    )
    http.post = AsyncMock(return_value=err_resp)
    pinned = MagicMock()
    pinned.__aenter__ = AsyncMock(return_value=http)
    pinned.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(lc_mod, "is_safe_http_url", return_value=True),
        patch.object(ot_mod, "make_pinned_async_client", return_value=pinned),
        patch.object(ot_mod, "_is_local_allowed", return_value=False),
        patch.object(ot_mod, "_require_https", return_value=False),
        patch.object(lc_mod, "is_safe_http_url", return_value=True),
        caplog.at_level("WARNING"),
        pytest.raises(httpx.HTTPStatusError),
    ):
        # Patch base retry to avoid sleep: make _retry_request return immediately.
        with patch.object(ot_mod, "_retry_request", new=AsyncMock(return_value=err_resp)):
            await c.chat([{"role": "user", "content": "hi"}])
    assert not any("sk-test-1234567890abcdef" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_chat_message_openai_with_tools_and_reasoning() -> None:
    c = _client()
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "hi",
                    "tool_calls": [{"id": "c1"}],
                    "reasoning_content": "think",
                }
            }
        ]
    }
    with (
        patch.object(lc_mod, "is_safe_http_url", return_value=True),
        patch.object(lc_mod, "build_payload", return_value={}),
        patch.object(lc_mod, "chat_completions", new=AsyncMock(return_value=data)),
    ):
        msg = await c.chat_message(
            [{"role": "user", "content": "hi"}], tool_choice="auto"
        )
    assert msg["tool_calls"] == [{"id": "c1"}]
    assert msg["reasoning"] == "think"


@pytest.mark.asyncio
async def test_chat_message_no_tools_no_reasoning() -> None:
    c = _client()
    data = {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}
    with (
        patch.object(lc_mod, "is_safe_http_url", return_value=True),
        patch.object(lc_mod, "build_payload", return_value={}),
        patch.object(lc_mod, "chat_completions", new=AsyncMock(return_value=data)),
    ):
        msg = await c.chat_message([{"role": "user", "content": "hi"}])
    assert msg["content"] == "hi"
    assert "tool_calls" not in msg
    assert "reasoning" not in msg


@pytest.mark.asyncio
async def test_chat_message_reasoning_key_and_role_fallback() -> None:
    c = _client()
    data = {"choices": [{"message": {"content": "x", "reasoning": "r"}}]}
    with (
        patch.object(lc_mod, "is_safe_http_url", return_value=True),
        patch.object(lc_mod, "build_payload", return_value={}),
        patch.object(lc_mod, "chat_completions", new=AsyncMock(return_value=data)),
    ):
        msg = await c.chat_message([{"role": "user", "content": "hi"}])
    assert msg["role"] == "assistant"
    assert msg["reasoning"] == "r"


@pytest.mark.asyncio
async def test_chat_message_delegates_and_strips_empty_tools() -> None:
    c = _client(protocol=LLMProtocol.OPENAI_RESPONSES)
    delegate = MagicMock()
    delegate.chat_message = AsyncMock(return_value={"role": "assistant", "content": "x", "tool_calls": []})
    with patch.object(LLMClient, "_delegate", return_value=delegate):
        msg = await c.chat_message([{"role": "user", "content": "hi"}])
    assert "tool_calls" not in msg


@pytest.mark.asyncio
async def test_chat_message_delegates_keeps_tools() -> None:
    c = _client(protocol=LLMProtocol.ANTHROPIC_MESSAGES)
    delegate = MagicMock()
    delegate.chat_message = AsyncMock(
        return_value={"role": "assistant", "content": "x", "tool_calls": [{"id": "1"}]}
    )
    with patch.object(LLMClient, "_delegate", return_value=delegate):
        msg = await c.chat_message([{"role": "user", "content": "hi"}])
    assert msg["tool_calls"] == [{"id": "1"}]


@pytest.mark.asyncio
async def test_chat_message_stream_openai() -> None:
    c = _client()

    async def _fake(*a: Any, **k: Any) -> Any:
        yield {"type": "message", "message": {}}
        return
        yield

    with (
        patch.object(lc_mod, "is_safe_http_url", return_value=True),
        patch.object(lc_mod, "build_payload", return_value={}),
        patch.object(lc_mod, "stream_message_round_retry", side_effect=_fake),
    ):
        events = [e async for e in c.chat_message_stream([{"role": "user", "content": "hi"}])]
    assert events[0]["type"] == "message"


@pytest.mark.asyncio
async def test_chat_message_stream_delegates() -> None:
    c = _client(protocol=LLMProtocol.ANTHROPIC_MESSAGES)
    delegate = MagicMock()

    async def _fake(*a: Any, **k: Any) -> Any:
        yield {"type": "message", "message": {}}
        return
        yield

    delegate.chat_message_stream = _fake
    with patch.object(LLMClient, "_delegate", return_value=delegate):
        events = [e async for e in c.chat_message_stream([{"role": "user", "content": "hi"}])]
    assert events[0]["type"] == "message"


@pytest.mark.asyncio
async def test_chat_stream_openai() -> None:
    c = _client()

    async def _fake(*a: Any, **k: Any) -> Any:
        yield "tok"
        return
        yield

    with (
        patch.object(lc_mod, "is_safe_http_url", return_value=True),
        patch.object(lc_mod, "build_payload", return_value={}),
        patch.object(lc_mod, "stream_text_retry", side_effect=_fake),
    ):
        tokens = [t async for t in c.chat_stream([{"role": "user", "content": "hi"}])]
    assert tokens == ["tok"]


@pytest.mark.asyncio
async def test_chat_stream_delegates() -> None:
    c = _client(protocol=LLMProtocol.OPENAI_RESPONSES)
    delegate = MagicMock()

    async def _fake(*a: Any, **k: Any) -> Any:
        yield "d"
        return
        yield

    delegate.chat_stream = _fake
    with patch.object(LLMClient, "_delegate", return_value=delegate):
        tokens = [t async for t in c.chat_stream([{"role": "user", "content": "hi"}])]
    assert tokens == ["d"]


@pytest.mark.asyncio
async def test_chat_json_test_connection_embed() -> None:
    c = _client()
    with patch(
        "realmock.platform.capabilities.ai.llm.client.json_response.parse_chat_json",
        new=AsyncMock(return_value={"a": 1}),
    ):
        assert await c.chat_json([{"role": "user", "content": "hi"}]) == {"a": 1}
    with patch.object(lc_mod._llm_ext, "test_connection", new=AsyncMock(return_value=(True, "ok"))):
        assert await c.test_connection() == (True, "ok")
    with patch.object(lc_mod._llm_ext, "embed", new=AsyncMock(return_value=[[0.1]])):
        assert await c.embed(["hi"]) == [[0.1]]


def test_from_stage_config_delegates() -> None:
    with patch.object(lc_mod, "build_from_stage_config", return_value="STAGE") as m:
        assert LLMClient.from_stage_config({}) == "STAGE"
        assert m.called
