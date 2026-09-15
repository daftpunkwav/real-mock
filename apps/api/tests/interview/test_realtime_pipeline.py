"""Pipeline tests for realtime/voice/pipeline.py.

Covers: latin ratio, STT text pick, echo detection, speak_one empty/success/failure paths.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from realmock.domains.interview.realtime.voice.pipeline import _is_echo_of_assistant, _latin_letter_ratio, _pick_stt_text
from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

def _make_handler(sid=10):
    """Build a mocked InterviewWSHandler bound to an in-memory websocket."""
    ws = MagicMock(accept=AsyncMock(), send_json=AsyncMock(), receive_json=AsyncMock(), close=AsyncMock())
    return InterviewWSHandler(ws, session_id=sid)

def test_latin_pick_echo_pure():
    assert _latin_letter_ratio("") == 0.0
    assert _latin_letter_ratio("Hello world") > 0.9
    assert _pick_stt_text("", "asr text") == "asr text"
    assert _pick_stt_text("browser", "") == "browser"
    assert _pick_stt_text("", "") == ""
    assert _pick_stt_text("你好", "I used React hooks daily") == "I used React hooks daily"
    assert _pick_stt_text("hello", "你好世界今天") == "你好世界今天"
    assert _is_echo_of_assistant("short", "short") is False
    long_a = "Tell me about Redis cache design in detail please explain"
    assert _is_echo_of_assistant(long_a, long_a) is True
    assert _is_echo_of_assistant("Completely different answer about Python asyncio tasks", long_a) is False


@pytest.mark.asyncio
async def test_speak_one_empty_success_fail():
    h = _make_handler()
    h.ctx.session_prosody = MagicMock(voice="v", rate="+0%", pitch="+0Hz")
    h.ctx.tts_creds = MagicMock(handler="edge", mode="tts_from_text", protocol="openai_chat", api_base="", api_key="", model="", voice="v", fallback_handler="none", fallback_mode="text_only")
    h._tts_send = AsyncMock()  # type: ignore[method-assign]
    h._mark_tts_sent = MagicMock()  # type: ignore[method-assign]
    await h._speak_one("   ***   ")
    h._tts_send.assert_not_called()
    with patch("realmock.domains.interview.realtime.voice.pipeline.synthesize_speech", AsyncMock(return_value="aud")):
        await h._speak_one("Hello world.")
        h._tts_send.assert_awaited_once()
        assert h._mark_tts_sent.called
    with patch("realmock.domains.interview.realtime.voice.pipeline.synthesize_speech", AsyncMock(side_effect=RuntimeError("down"))):
        await h._speak_one("Hello again world.")
        sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
        assert any(e.get("code") == "C2002" for e in sent)


@pytest.mark.asyncio
async def test_speak_one_empty_audio_sends_failed():
    h = _make_handler()
    h.ctx.session_prosody = MagicMock(voice="v", rate="+0%", pitch="+0Hz")
    h.ctx.tts_creds = MagicMock(handler="edge", mode="tts_from_text", protocol="openai_chat", api_base="", api_key="", model="", voice="v", fallback_handler="none", fallback_mode="text_only")
    h._tts_send = AsyncMock()  # type: ignore[method-assign]
    h._mark_tts_sent = MagicMock()  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.voice.pipeline.synthesize_speech", AsyncMock(return_value="")):
        await h._speak_one("Hello world test.")
        sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
        assert any(e.get("type") == "tts_failed" for e in sent)

