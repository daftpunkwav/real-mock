"""Retry-stream tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/retry_stream.py.

Covers: chat_message_stream/chat_text_stream success, 429/5xx/4xx handling,
stream-options downgrade and connect-error retry/emit guards.

Conventions: no real network (httpx/pinned client mocked); asyncio_mode=auto.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from realmock.platform.capabilities.ai.llm.client import retry_stream as rs_mod
from realmock.platform.capabilities.ai.llm.usage import UsageAccumulator


def _client() -> MagicMock:
    c = MagicMock()
    c.usage = UsageAccumulator()
    c.protocol = "openai_chat"
    c._stream_usage_disabled = False
    return c


def _ok_resp(lines: list[str]) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.request = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.aread = AsyncMock(return_value=b"{}")

    async def _gen() -> Any:
        for line in lines:
            yield line

    resp.aiter_lines = lambda: _gen()
    return resp


def _err_resp(status: int, body: bytes = b"{}", exc: bool = True) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.request = MagicMock()
    resp.aread = AsyncMock(return_value=body)
    if exc:
        resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(str(status), request=MagicMock(), response=resp)
        )
    else:
        resp.raise_for_status = MagicMock()
    async def _gen() -> Any:
        if False:
            yield ""
    resp.aiter_lines = lambda: _gen()
    return resp


def _pinned_for(sequence: list[Any], exc_map: dict[int, Exception] | None = None) -> MagicMock:
    """Build pinned client where c.stream returns contexts in order; entries may be resp or Exception."""
    calls = {"n": 0}

    def _stream(*a: Any, **k: Any) -> MagicMock:
        idx = calls["n"]
        calls["n"] += 1
        item = sequence[min(idx, len(sequence) - 1)]
        ctx = MagicMock()
        if isinstance(item, Exception):
            ctx.__aenter__ = AsyncMock(side_effect=item)
        else:
            ctx.__aenter__ = AsyncMock(return_value=item)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    http = MagicMock()
    http.stream = _stream
    http.calls = calls  # type: ignore[attr-defined]
    pinned = MagicMock()
    pinned.__aenter__ = AsyncMock(return_value=http)
    pinned.__aexit__ = AsyncMock(return_value=False)
    pinned.http = http  # type: ignore[attr-defined]
    return pinned


async def _collect(agen: Any) -> list[Any]:
    return [x async for x in agen]


def _patch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rs_mod.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(rs_mod, "_is_local_allowed", lambda: False)
    monkeypatch.setattr(rs_mod, "_require_https", lambda: False)


# ── stream_message_round_retry ──


@pytest.mark.asyncio
async def test_msg_success_text_and_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    lines = [
        "x: ignore",
        'data: {"choices":[{"delta":{"reasoning_content":"why"}}]}',
        'data: {"choices":[{"delta":{"content":"hi"}}]}',
        "data: {bad",
        "data: [DONE]",
    ]
    pinned = _pinned_for([_ok_resp(lines)])
    with patch.object(rs_mod, "make_pinned_async_client", return_value=pinned):
        events = await _collect(
            rs_mod.stream_message_round_retry(client, "https://x", "k", "m", "https://u", {})
        )
    assert any(e["type"] == "reasoning" for e in events)
    assert any(e["type"] == "text" for e in events)
    assert events[-1]["type"] == "message"


@pytest.mark.asyncio
async def test_msg_429_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    pinned = _pinned_for(
        [_err_resp(429), _ok_resp(['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"])]
    )
    with patch.object(rs_mod, "make_pinned_async_client", return_value=pinned):
        events = await _collect(
            rs_mod.stream_message_round_retry(client, "https://x", "k", "m", "https://u", {})
        )
    assert events[-1]["message"]["content"] == "hi"
    assert pinned.http.calls["n"] == 2  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_msg_500_retries_then_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    pinned = _pinned_for([_err_resp(500)] * 5)
    with (
        patch.object(rs_mod, "make_pinned_async_client", return_value=pinned),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await _collect(
            rs_mod.stream_message_round_retry(client, "https://x", "k", "m", "https://u", {})
        )
    # Shared ladder: 10 retries (11 attempts total) before exhaustion.
    assert pinned.http.calls["n"] == 11  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_msg_4xx_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    pinned = _pinned_for([_err_resp(400)])
    with (
        patch.object(rs_mod, "make_pinned_async_client", return_value=pinned),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await _collect(
            rs_mod.stream_message_round_retry(client, "https://x", "k", "m", "https://u", {})
        )
    assert pinned.http.calls["n"] == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_msg_stream_options_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    payload = {"stream_options": {"include_usage": True}, "model": "m"}
    first = _err_resp(400, body=b"stream_options unsupported")
    second = _ok_resp(['data: {"choices":[{"delta":{"content":"ok"}}]}', "data: [DONE]"])
    pinned = _pinned_for([first, second])
    with patch.object(rs_mod, "make_pinned_async_client", return_value=pinned):
        events = await _collect(
            rs_mod.stream_message_round_retry(client, "https://x", "k", "m", "https://u", payload)
        )
    assert client._stream_usage_disabled is True
    assert "stream_options" not in payload
    assert events[-1]["message"]["content"] == "ok"


@pytest.mark.asyncio
async def test_msg_stream_options_body_without_keyword_no_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    payload = {"stream_options": {"include_usage": True}}
    pinned = _pinned_for([_err_resp(400, body=b"other error")])
    with (
        patch.object(rs_mod, "make_pinned_async_client", return_value=pinned),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await _collect(
            rs_mod.stream_message_round_retry(client, "https://x", "k", "m", "https://u", payload)
        )
    assert client._stream_usage_disabled is False


@pytest.mark.asyncio
async def test_msg_connection_error_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    pinned = _pinned_for(
        [httpx.ConnectError("down"), _ok_resp(['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"])]
    )
    with patch.object(rs_mod, "make_pinned_async_client", return_value=pinned):
        events = await _collect(
            rs_mod.stream_message_round_retry(client, "https://x", "k", "m", "https://u", {})
        )
    assert events[-1]["type"] == "message"


@pytest.mark.asyncio
async def test_msg_connection_error_after_emit_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()

    async def _gen_emit_then_fail() -> Any:
        yield 'data: {"choices":[{"delta":{"content":"hi"}}]}'
        raise httpx.ConnectError("mid-stream")

    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.request = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.aread = AsyncMock(return_value=b"{}")
    resp.aiter_lines = lambda: _gen_emit_then_fail()
    pinned = _pinned_for([resp])
    with (
        patch.object(rs_mod, "make_pinned_async_client", return_value=pinned),
        pytest.raises(httpx.ConnectError),
    ):
        await _collect(
            rs_mod.stream_message_round_retry(client, "https://x", "k", "m", "https://u", {})
        )


@pytest.mark.asyncio
async def test_msg_connection_error_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    pinned = _pinned_for([httpx.ConnectError("down")] * 5)
    with (
        patch.object(rs_mod, "make_pinned_async_client", return_value=pinned),
        pytest.raises(httpx.ConnectError),
    ):
        await _collect(
            rs_mod.stream_message_round_retry(client, "https://x", "k", "m", "https://u", {})
        )


# ── stream_text_retry ──


@pytest.mark.asyncio
async def test_text_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    lines = [": keep-alive", 'data: {"choices":[{"delta":{"content":"hello"}}]}', "data: [DONE]"]
    pinned = _pinned_for([_ok_resp(lines)])
    with patch.object(rs_mod, "make_pinned_async_client", return_value=pinned):
        tokens = await _collect(
            rs_mod.stream_text_retry(client, "https://x", "k", "m", "https://u", {})
        )
    assert "".join(tokens) == "hello"


@pytest.mark.asyncio
async def test_text_reasoning_and_malformed_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"why"}}]}',
        "data: {bad",
        'data: {"nope": 1}',
        'data: {"choices":[]}',
        'data: {"choices":[{"delta":"bad"}]}',
        "data: [DONE]",
    ]
    pinned = _pinned_for([_ok_resp(lines)])
    with patch.object(rs_mod, "make_pinned_async_client", return_value=pinned):
        tokens = await _collect(
            rs_mod.stream_text_retry(client, "https://x", "k", "m", "https://u", {})
        )
    assert any("why" in t for t in tokens)


@pytest.mark.asyncio
async def test_text_429_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    pinned = _pinned_for(
        [_err_resp(429), _ok_resp(['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"])]
    )
    with patch.object(rs_mod, "make_pinned_async_client", return_value=pinned):
        tokens = await _collect(
            rs_mod.stream_text_retry(client, "https://x", "k", "m", "https://u", {})
        )
    assert "".join(tokens) == "hi"


@pytest.mark.asyncio
async def test_text_500_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    pinned = _pinned_for([_err_resp(500)] * 5)
    with (
        patch.object(rs_mod, "make_pinned_async_client", return_value=pinned),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await _collect(rs_mod.stream_text_retry(client, "https://x", "k", "m", "https://u", {}))


@pytest.mark.asyncio
async def test_text_stream_options_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    payload = {"stream_options": {"include_usage": True}}
    pinned = _pinned_for(
        [
            _err_resp(400, body=b"stream_options bad"),
            _ok_resp(['data: {"choices":[{"delta":{"content":"ok"}}]}', "data: [DONE]"]),
        ]
    )
    with patch.object(rs_mod, "make_pinned_async_client", return_value=pinned):
        tokens = await _collect(
            rs_mod.stream_text_retry(client, "https://x", "k", "m", "https://u", payload)
        )
    assert "".join(tokens) == "ok"
    assert client._stream_usage_disabled is True


@pytest.mark.asyncio
async def test_text_4xx_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    pinned = _pinned_for([_err_resp(400, body=b"other")])
    with (
        patch.object(rs_mod, "make_pinned_async_client", return_value=pinned),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await _collect(
            rs_mod.stream_text_retry(
                client, "https://x", "k", "m", "https://u", {"stream_options": {}}
            )
        )


@pytest.mark.asyncio
async def test_text_connection_retry_and_emit_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    pinned = _pinned_for(
        [httpx.ConnectError("down"), _ok_resp(['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"])]
    )
    with patch.object(rs_mod, "make_pinned_async_client", return_value=pinned):
        tokens = await _collect(
            rs_mod.stream_text_retry(client, "https://x", "k", "m", "https://u", {})
        )
    assert "".join(tokens) == "hi"


@pytest.mark.asyncio
async def test_text_connection_after_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()

    async def _gen() -> Any:
        yield 'data: {"choices":[{"delta":{"content":"hi"}}]}'
        raise httpx.ReadTimeout("mid")

    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.request = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.aread = AsyncMock(return_value=b"{}")
    resp.aiter_lines = lambda: _gen()
    pinned = _pinned_for([resp])
    with (
        patch.object(rs_mod, "make_pinned_async_client", return_value=pinned),
        pytest.raises(httpx.ReadTimeout),
    ):
        await _collect(rs_mod.stream_text_retry(client, "https://x", "k", "m", "https://u", {}))


@pytest.mark.asyncio
async def test_text_connection_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    client = _client()
    pinned = _pinned_for([httpx.ConnectError("down")] * 5)
    with (
        patch.object(rs_mod, "make_pinned_async_client", return_value=pinned),
        pytest.raises(httpx.ConnectError),
    ):
        await _collect(rs_mod.stream_text_retry(client, "https://x", "k", "m", "https://u", {}))
