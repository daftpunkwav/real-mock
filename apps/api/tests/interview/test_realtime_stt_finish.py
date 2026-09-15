"""STT finish tests for realtime/turn/stt_finish.py.

Covers: run busy-info, missing session A2001, exception recovery C0001,
success dispatch, early returns, PCM limit A0004, fallback process,
empty-text C2001 backoff, buffer path, echo reject, sample-range guard.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler
from realmock.platform.capabilities.voice.stt import SttResult

def _make_handler(sid=1):
    """Build a mocked InterviewWSHandler bound to an in-memory websocket."""
    ws = MagicMock(accept=AsyncMock(), send_json=AsyncMock(), receive_json=AsyncMock(), close=AsyncMock())
    return InterviewWSHandler(ws, session_id=sid)


async def _agen(items):
    """Yield canned stream events for deterministic streaming tests."""
    for i in items:
        yield i

@pytest.mark.asyncio
async def test_run_busy_sends_info():
    h = _make_handler()
    h.ctx.turn_busy = True
    h.ctx.busy_epoch = h.ctx.stream_epoch
    await h._run_user_turn_end({"pcm": "AA"})
    assert h.ctx.ws.send_json.await_args[0][0]["type"] == "info"


@pytest.mark.asyncio
async def test_run_missing_session_sends_a2001():
    h = _make_handler()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch("realmock.domains.interview.realtime.turn.stt_finish.SessionLocal", return_value=db):
        await h._run_user_turn_end({"pcm": "AA"})
    assert h.ctx.ws.send_json.await_args[0][0]["code"] == "A2001"
    assert h.ctx.turn_busy is False


@pytest.mark.asyncio
async def test_run_exception_recovers_user_speaking():
    h = _make_handler()
    db = MagicMock()
    sess = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = sess
    h.rebind_runtime_session = MagicMock()  # type: ignore[method-assign]
    h._on_user_turn_end = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.turn.stt_finish.SessionLocal", return_value=db):
        await h._run_user_turn_end({"pcm": "AA"})
    sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
    assert any(e.get("code") == "C0001" for e in sent)
    assert h.ctx.turn_state == TurnState.USER_SPEAKING
    assert h.ctx.turn_busy is False


@pytest.mark.asyncio
async def test_run_success_calls_on_turn_end():
    h = _make_handler()
    db = MagicMock()
    sess = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = sess
    h.rebind_runtime_session = MagicMock()  # type: ignore[method-assign]
    h._on_user_turn_end = AsyncMock()  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.turn.stt_finish.SessionLocal", return_value=db):
        await h._run_user_turn_end({"pcm": "AA"})
    h._on_user_turn_end.assert_awaited_once()
    db.close.assert_called_once()


@pytest.mark.asyncio
async def test_early_returns_and_pcm_limit():
    h = _make_handler()
    h.ctx.turn_state = TurnState.PROCESSING
    h._process_user_text = AsyncMock()  # type: ignore[method-assign]
    await h._on_user_turn_end({}, MagicMock(), MagicMock())
    h._process_user_text.assert_not_awaited()
    h.ctx.turn_state = TurnState.AI_SPEAKING
    await h._on_user_turn_end({}, MagicMock(), MagicMock())
    h._process_user_text.assert_not_awaited()
    h2 = _make_handler()
    h2.ctx.turn_state = TurnState.USER_SPEAKING
    big = "A" * (5 * 1024 * 1024 + 5)
    await h2._on_user_turn_end({"pcm": big}, MagicMock(), MagicMock())
    sent = [c.args[0] for c in h2.ctx.ws.send_json.call_args_list]
    assert any(e.get("code") == "A0004" for e in sent)


@pytest.mark.asyncio
async def test_pcm_success_with_fallback_and_process():
    h = _make_handler()
    h.ctx.turn_state = TurnState.USER_SPEAKING
    h._process_user_text = AsyncMock()  # type: ignore[method-assign]
    h._reject_probable_echo = AsyncMock(return_value=False)  # type: ignore[method-assign]
    res = SttResult(text="hello world answer", provider="local", fallback=True, requested_provider="x")
    with patch("realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result", AsyncMock(return_value=res)):
        await h._on_user_turn_end({"pcm": "AAAA", "sample_rate": "bad"}, MagicMock(), MagicMock())
    types = [c.args[0]["type"] for c in h.ctx.ws.send_json.call_args_list]
    assert "info" in types and "stt_final" in types
    h._process_user_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_text_sends_c2001_once_with_backoff():
    h = _make_handler()
    h.ctx.turn_state = TurnState.USER_SPEAKING
    h.ctx.last_stt_error_at = 0.0
    h._process_user_text = AsyncMock()  # type: ignore[method-assign]
    res = SttResult(text="", provider="local")
    with patch("realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result", AsyncMock(return_value=res)):
        await h._on_user_turn_end({"pcm": "AAAA"}, MagicMock(), MagicMock())
    sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
    assert any(e.get("code") == "C2001" for e in sent)
    h.ctx.ws.send_json.reset_mock()
    await h._on_user_turn_end({"text": "   "}, MagicMock(), MagicMock())
    sent2 = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
    assert not any(e.get("code") == "C2001" for e in sent2)


@pytest.mark.asyncio
async def test_buffer_path_and_echo_reject():
    h = _make_handler()
    h.ctx.turn_state = TurnState.USER_SPEAKING
    h.ctx.audio_buffer = ["AAAA"]
    h.ctx.audio_buffer_bytes = 4
    h._process_user_text = AsyncMock()  # type: ignore[method-assign]
    h._reject_probable_echo = AsyncMock(return_value=False)  # type: ignore[method-assign]
    res = SttResult(text="buffer answer text", provider="local")
    with patch("realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result", AsyncMock(return_value=res)):
        await h._on_user_turn_end({}, MagicMock(), MagicMock())
    assert h.ctx.audio_buffer == []
    h._process_user_text.assert_awaited_once()
    h2 = _make_handler()
    h2.ctx.agent = MagicMock()
    h2.ctx.agent.messages = [{"role": "assistant", "content": "Tell me about Redis cache design in detail please"}]
    assert h2._last_assistant_content().startswith("Tell me")
    h2.ctx.agent.messages = [{"role": "assistant", "content": "Tell me about Redis cache design in detail please"}]
    h2.set_turn = AsyncMock()  # type: ignore[method-assign]
    ok = await h2._reject_probable_echo("Tell me about Redis cache design in detail please")
    assert ok is True
    sent2 = [c.args[0] for c in h2.ctx.ws.send_json.call_args_list]
    assert any(e.get("code") == "C2001" for e in sent2)


@pytest.mark.asyncio
async def test_run_inner_restore_and_close_fail():
    h = _make_handler()
    db = MagicMock()
    sess = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = sess
    db.close = MagicMock(side_effect=RuntimeError("close fail"))
    h.rebind_runtime_session = MagicMock()  # type: ignore[method-assign]
    h._on_user_turn_end = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    h.set_turn = AsyncMock(side_effect=RuntimeError("set fail"))  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.turn.stt_finish.SessionLocal", return_value=db):
        await h._run_user_turn_end({"pcm": "AA"})
    assert h.ctx.turn_busy is False


@pytest.mark.asyncio
async def test_sample_range_and_buffer_limit_and_clear():
    h = _make_handler()
    h.ctx.turn_state = TurnState.USER_SPEAKING
    h._process_user_text = AsyncMock()  # type: ignore[method-assign]
    h._reject_probable_echo = AsyncMock(return_value=False)  # type: ignore[method-assign]
    res = SttResult(text="valid answer text here", provider="local")
    with patch("realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result", AsyncMock(return_value=res)):
        await h._on_user_turn_end({"pcm": "AAAA", "sample_rate": 100}, MagicMock(), MagicMock())
    h._process_user_text.assert_awaited()
    h2 = _make_handler()
    h2.ctx.turn_state = TurnState.USER_SPEAKING
    h2.ctx.audio_buffer = ["A" * (5 * 1024 * 1024 + 5)]
    h2.ctx.audio_buffer_bytes = 0
    await h2._on_user_turn_end({}, MagicMock(), MagicMock())
    sent = [c.args[0] for c in h2.ctx.ws.send_json.call_args_list]
    assert any(e.get("code") == "A0004" for e in sent)
    h3 = _make_handler()
    h3.ctx.turn_state = TurnState.USER_SPEAKING
    h3.ctx.audio_buffer = ["AAAA"]
    h3._process_user_text = AsyncMock()  # type: ignore[method-assign]
    h3._reject_probable_echo = AsyncMock(return_value=False)  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result", AsyncMock(return_value=res)):
        await h3._on_user_turn_end({"text": "typed"}, MagicMock(), MagicMock())
    assert h3.ctx.audio_buffer == []


@pytest.mark.asyncio
async def test_buffer_fallback_echo_and_no_agent():
    h = _make_handler()
    h.ctx.turn_state = TurnState.USER_SPEAKING
    h.ctx.audio_buffer = ["AAAA"]
    h.ctx.audio_buffer_bytes = 4
    h._process_user_text = AsyncMock()  # type: ignore[method-assign]
    h._reject_probable_echo = AsyncMock(return_value=True)  # type: ignore[method-assign]
    res = SttResult(text="echo text", provider="cloud", fallback=True)
    with patch("realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result", AsyncMock(return_value=res)):
        await h._on_user_turn_end({}, MagicMock(), MagicMock())
    h._process_user_text.assert_not_awaited()
    h2 = _make_handler()
    h2.ctx.agent = None
    assert h2._last_assistant_content() == ""
    assert await h2._reject_probable_echo("anything long enough text here") is False

