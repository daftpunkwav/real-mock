"""Regression coverage for session capability tokens and audio_buffer cumulative bytes."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from realmock.platform.core.session_auth import new_access_token, tokens_match


def test_tokens_match_rejects_empty() -> None:
    assert tokens_match("", "abc") is False
    assert tokens_match("abc", "") is False
    assert tokens_match(None, "abc") is False


def test_tokens_match_accepts_equal() -> None:
    t = new_access_token()
    assert tokens_match(t, t) is True
    assert tokens_match(t, t + "x") is False


@pytest.mark.asyncio
async def test_audio_chunk_uses_running_byte_total() -> None:
    from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler, _AUDIO_BUFFER_MAX_BYTES

    ws = MagicMock()
    ws.send_json = AsyncMock()
    handler = InterviewWSHandler(ws, session_id=1, access_token="tok")
    # Small chunk
    raw = b"\x00\x01" * 100
    chunk = base64.b64encode(raw).decode("ascii")
    await handler._dispatch({"type": "audio_chunk", "data": chunk}, MagicMock(), MagicMock())
    assert handler.ctx.audio_buffer_bytes == len(raw)
    assert len(handler.ctx.audio_buffer) == 1

    # Appending again should not trigger a full recomputation (bytes should accumulate)
    await handler._dispatch({"type": "audio_chunk", "data": chunk}, MagicMock(), MagicMock())
    assert handler.ctx.audio_buffer_bytes == len(raw) * 2

    # Clear when over the limit
    handler.ctx.audio_buffer_bytes = _AUDIO_BUFFER_MAX_BYTES
    await handler._dispatch({"type": "audio_chunk", "data": chunk}, MagicMock(), MagicMock())
    assert handler.ctx.audio_buffer == []
    assert handler.ctx.audio_buffer_bytes == 0
