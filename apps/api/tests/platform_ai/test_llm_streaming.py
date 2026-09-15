"""Streaming tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/streaming.py.

Covers: stream_message/stream_text SSE rounds across protocols, reasoning deltas,
stream-options downgrade and tail-flush branches.

Conventions: no real network (httpx SSE transport mocked); asyncio_mode=auto.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from realmock.platform.capabilities.ai.llm.client import streaming as st_mod
from realmock.platform.capabilities.ai.llm.usage import UsageAccumulator


def _client() -> MagicMock:
    c = MagicMock()
    c.usage = UsageAccumulator()
    return c


def _pinned_with_stream(resp: MagicMock) -> MagicMock:
    stream_ctx = MagicMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=resp)
    stream_ctx.__aexit__ = AsyncMock(return_value=False)
    http = MagicMock()
    http.stream = MagicMock(return_value=stream_ctx)
    pinned = MagicMock()
    pinned.__aenter__ = AsyncMock(return_value=http)
    pinned.__aexit__ = AsyncMock(return_value=False)
    return pinned


def _sse_resp(lines: list[str], status: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.aread = AsyncMock(return_value=b"{}")
    resp.raise_for_status = MagicMock()

    async def _gen() -> Any:
        for line in lines:
            yield line

    resp.aiter_lines = lambda: _gen()
    return resp


async def _collect(agen: Any) -> list[Any]:
    return [x async for x in agen]


def _patch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(st_mod, "_is_local_allowed", lambda: False)
    monkeypatch.setattr(st_mod, "_require_https", lambda: False)


@pytest.mark.asyncio
async def test_stream_message_round_openai_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    lines = [
        ": keep-alive",
        "data: " + '{"choices":[{"delta":{"content":"hi"}}]}',
        "data: not-json{{{",
        "data: [DONE]",
    ]
    resp = _sse_resp(lines)
    with patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)):
        events = await _collect(
            st_mod.stream_message_round(client, "https://x", "openai_chat", "k", "https://u", {})
        )
    kinds = [e["type"] for e in events]
    assert "text" in kinds
    assert events[-1]["type"] == "message"
    assert events[-1]["message"]["content"] == "hi"


@pytest.mark.asyncio
async def test_stream_message_round_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    lines = ['data: {"choices":[{"delta":{"reasoning_content":"why"}}]}', "data: [DONE]"]
    resp = _sse_resp(lines)
    with patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)):
        events = await _collect(
            st_mod.stream_message_round(client, "https://x", "openai_chat", "k", "https://u", {})
        )
    assert any(e["type"] == "reasoning" for e in events)


@pytest.mark.asyncio
async def test_stream_message_round_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    lines = [
        'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"A"}}',
        "data: [DONE]",
    ]
    resp = _sse_resp(lines)
    with patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)):
        events = await _collect(
            st_mod.stream_message_round(
                client, "https://x", "anthropic_messages", "k", "https://u", {}
            )
        )
    assert events[-1]["message"]["content"] == "A"


@pytest.mark.asyncio
async def test_stream_message_round_options_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    resp = _sse_resp([], status=400)
    resp.aread = AsyncMock(return_value=b"stream_options rejected here")
    with (
        patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)),
        pytest.raises(st_mod._StreamOptionsUnsupported),
    ):
        await _collect(
            st_mod.stream_message_round(
                client, "https://x", "openai_chat", "k", "https://u", {"stream_options": {}}
            )
        )


@pytest.mark.asyncio
async def test_stream_message_round_400_without_keyword_calls_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_env(monkeypatch)
    client = _client()
    resp = _sse_resp([], status=400)
    resp.aread = AsyncMock(return_value=b"other error")
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("400", request=MagicMock(), response=resp)
    )
    with (
        patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await _collect(
            st_mod.stream_message_round(
                client, "https://x", "openai_chat", "k", "https://u", {"stream_options": {}}
            )
        )


@pytest.mark.asyncio
async def test_stream_message_round_422_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    resp = _sse_resp([], status=422)
    resp.aread = AsyncMock(return_value=b"bad stream_options field")
    with (
        patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)),
        pytest.raises(st_mod._StreamOptionsUnsupported),
    ):
        await _collect(
            st_mod.stream_message_round(
                client, "https://x", "openai_chat", "k", "https://u", {"stream_options": {}}
            )
        )


@pytest.mark.asyncio
async def test_stream_text_payload_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    lines = [
        "event: ping",
        'data: {"choices":[{"delta":{"content":"hello"}}]}',
        "data: [DONE]",
    ]
    resp = _sse_resp(lines)
    with patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)):
        tokens = await _collect(
            st_mod.stream_text_payload(client, "https://x", "openai_chat", "k", "https://u", {})
        )
    assert "".join(tokens) == "hello"


@pytest.mark.asyncio
async def test_stream_text_payload_reasoning_and_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"why"}}]}',
        "data: {bad",
        "data: [DONE]",
    ]
    resp = _sse_resp(lines)
    with patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)):
        tokens = await _collect(
            st_mod.stream_text_payload(client, "https://x", "openai_chat", "k", "https://u", {})
        )
    assert any("why" in t for t in tokens)


@pytest.mark.asyncio
async def test_stream_text_payload_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    resp = _sse_resp([], status=400)
    resp.aread = AsyncMock(return_value=b"stream_options not supported")
    with (
        patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)),
        pytest.raises(st_mod._StreamOptionsUnsupported),
    ):
        await _collect(
            st_mod.stream_text_payload(
                client, "https://x", "openai_chat", "k", "https://u", {"stream_options": {}}
            )
        )


@pytest.mark.asyncio
async def test_stream_text_payload_anthropic_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    lines = [
        'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"hmm"}}',
        "data: [DONE]",
    ]
    resp = _sse_resp(lines)
    with patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)):
        tokens = await _collect(
            st_mod.stream_text_payload(
                client, "https://x", "anthropic_messages", "k", "https://u", {}
            )
        )
    assert any("hmm" in t for t in tokens)


@pytest.mark.asyncio
async def test_stream_text_payload_flush_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    resp = _sse_resp(["data: [DONE]"])
    with patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)):
        with patch.object(
            st_mod, "StreamSanitizer"
        ) as mock_san:
            inst = mock_san.return_value
            inst.feed_reasoning.return_value = ""
            inst.feed_content.return_value = ""
            inst.flush.return_value = "TAIL"
            tokens = await _collect(
                st_mod.stream_text_payload(client, "https://x", "openai_chat", "k", "https://u", {})
            )
    assert tokens == ["TAIL"]


@pytest.mark.asyncio
async def test_stream_text_payload_no_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch)
    client = _client()
    resp = _sse_resp(["data: [DONE]"])
    with patch.object(st_mod, "make_pinned_async_client", return_value=_pinned_with_stream(resp)):
        with patch.object(st_mod, "StreamSanitizer") as mock_san:
            inst = mock_san.return_value
            inst.feed_reasoning.return_value = ""
            inst.feed_content.return_value = ""
            inst.flush.return_value = ""
            tokens = await _collect(
                st_mod.stream_text_payload(client, "https://x", "openai_chat", "k", "https://u", {})
            )
    assert tokens == []
