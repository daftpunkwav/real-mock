"""Message dispatcher tests for realtime/core/message_dispatcher.py.

Covers: user_text admission (A0003 length guard, busy-info, rate limit, spawn),
audio/stt/pong/vision admission, turn_end/silence/barge/finish wrappers,
hint/playback/overflow, coding update/run/submit, spawn gaps.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler
from realmock.platform.core.ratelimit import reset_rate_limit

def _make_handler(sid=1):
    """Build a mocked InterviewWSHandler bound to an in-memory websocket."""
    ws = MagicMock(accept=AsyncMock(), send_json=AsyncMock(), receive_json=AsyncMock(), close=AsyncMock())
    return InterviewWSHandler(ws, session_id=sid)


async def _agen(items):
    """Yield canned stream events for deterministic streaming tests."""
    for i in items:
        yield i

@pytest.mark.asyncio
async def test_llm_rate_limited_flips():
    h = _make_handler(11)
    reset_rate_limit()
    try:
        assert h._llm_rate_limited(limit=1) is False
        assert h._llm_rate_limited(limit=1) is True
    finally:
        reset_rate_limit()


@pytest.mark.asyncio
async def test_user_text_too_long_sends_a0003():
    h = _make_handler()
    h.ctx.turn_state = TurnState.USER_SPEAKING
    await h._on_user_text({"text": "x" * 16001})
    payload = h.ctx.ws.send_json.await_args[0][0]
    assert payload["type"] == "error" and payload["code"] == "A0003"


@pytest.mark.asyncio
async def test_user_text_busy_sends_info_empty_noop():
    h = _make_handler()
    h.ctx.turn_state = TurnState.USER_SPEAKING
    h.ctx.turn_busy = True
    await h._on_user_text({"text": "hello"})
    sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
    assert any(e.get("type") == "info" for e in sent)
    h2 = _make_handler()
    await h2._on_user_text({"text": "   "})
    h2.ctx.ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_user_text_ratelimited_and_spawn():
    h = _make_handler(12)
    h.ctx.turn_state = TurnState.USER_SPEAKING
    reset_rate_limit()
    try:
        h._llm_rate_limited = lambda limit: True  # type: ignore[method-assign]
        await h._on_user_text({"text": "hi"})
        assert h.ctx.ws.send_json.await_args[0][0]["code"] == "A0002"
    finally:
        reset_rate_limit()
    h3 = _make_handler()
    h3.ctx.turn_state = TurnState.USER_SPEAKING
    h3._llm_rate_limited = lambda limit: False  # type: ignore[method-assign]
    h3._spawn = MagicMock(side_effect=lambda coro: (coro.close(), MagicMock())[1])  # type: ignore[method-assign]
    await h3._on_user_text({"text": "hi"})
    h3._spawn.assert_called_once()


@pytest.mark.asyncio
async def test_audio_stt_pong_vision_ratelimited():
    h = _make_handler()
    await h._on_audio_chunk({"data": ""})
    assert h.ctx.audio_buffer == []
    await h._on_audio_chunk({"data": "!!!"})
    assert h.ctx.audio_buffer_bytes == 0
    await h._on_audio_chunk({"data": base64.b64encode(b"ab").decode()})
    assert len(h.ctx.audio_buffer) == 2
    await h._on_stt_text({"text": " partial "})
    assert h.ctx.ws.send_json.await_args[0][0] == {"type": "stt_partial", "text": "partial"}
    h.ctx.ws.send_json.reset_mock()
    await h._on_stt_text({"text": "   "})
    h.ctx.ws.send_json.assert_not_called()
    await h._on_pong({"t": 1})
    await h._on_vision_update({"face_analysis": {"face_detected": True}})
    assert h.ctx.orchestrator.snapshot.face_analysis == {"face_detected": True}
    await h._send_rate_limited()
    assert h.ctx.ws.send_json.await_args[0][0]["code"] == "A0002"


@pytest.mark.asyncio
async def test_start_turn_end_silence_barge_finish_wrappers():
    h = _make_handler()
    h.ctx.closing = True
    await h._start_user_turn_end({})
    await h._on_barge_in({})
    await h._start_request_finish({})
    h.ctx.ws.send_json.assert_not_called()
    h.ctx.closing = False
    h.ctx.turn_busy = True
    await h._start_user_turn_end({})
    assert h.ctx.ws.send_json.await_args[0][0]["type"] == "info"
    h.ctx.turn_busy = False
    h._spawn = MagicMock(side_effect=lambda c: (c.close(), MagicMock())[1])  # type: ignore[method-assign]
    h._llm_rate_limited = lambda limit: True  # type: ignore[method-assign]
    await h._start_user_turn_end({})
    assert h.ctx.ws.send_json.await_args[0][0]["code"] == "A0002"
    h._llm_rate_limited = lambda limit: False  # type: ignore[method-assign]
    await h._start_user_turn_end({"type": "user_turn_end"})
    h._spawn.assert_called_once()
    h2 = _make_handler()
    h2.ctx.turn_busy = True
    await h2._on_silence_timeout({})
    h2.ctx.ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_hint_playback_and_overflow():
    h = _make_handler()
    reset_rate_limit()
    try:
        h._llm_rate_limited = lambda limit: True  # type: ignore[method-assign]
        h._hint_rate_limited = AsyncMock()  # type: ignore[method-assign]
        await h._start_request_hint({"question": "q"})
        h._hint_rate_limited.assert_awaited_once()
    finally:
        reset_rate_limit()
    h.ctx.playback_done.clear()
    await h._on_tts_playback_done({"generation": None})
    assert h.ctx.playback_done.is_set()
    h2 = _make_handler()
    h2.ctx.audio_buffer_bytes = 5 * 1024 * 1024 - 1
    await h2._on_audio_chunk({"data": "YWI="})
    assert h2.ctx.audio_buffer == []
    assert h2.ctx.ws.send_json.await_args[0][0]["code"] == "A0004"


@pytest.mark.asyncio
async def test_coding_update_run():
    h = _make_handler()
    h.ctx.runner = MagicMock()
    await h._on_coding_code_update({"code": "print(1)"})
    assert h.ctx.runner.agent.cognitive_memory.working_memory.candidate_code == "print(1)"
    h.ctx.runner = MagicMock()
    del h.ctx.runner.coding_examiner
    await h._on_coding_run_request({"code": "x"})
    h.ctx.ws.send_json.assert_not_called()
    tc = MagicMock()
    tc.to_dict.return_value = {"input": "1", "expected": "1"}
    h.ctx.runner = MagicMock()
    h.ctx.runner.coding_examiner.active_challenge.test_cases = [tc]
    with patch("realmock.domains.interview.capabilities.sandbox.evaluator.evaluate_test_cases") as m:
        m.return_value.to_dict.return_value = {"passed": True}
        await h._on_coding_run_request({"code": "c", "test_output": "1"})
        assert h.ctx.ws.send_json.await_args[0][0]["type"] == "coding_test_result"


@pytest.mark.asyncio
async def test_coding_submit_timeout_error_success():
    h = _make_handler()
    h.ctx.runner = MagicMock()
    h.ctx.runner.agent.agent_state = {"asked_questions": ["q1"]}
    h.ctx.runner.coding_examiner.evaluate_submission = AsyncMock(side_effect=asyncio.TimeoutError())
    await h._on_coding_submit_request({"code": "c"})
    assert h.ctx.ws.send_json.await_args[0][0]["code"] == "C0001"
    h.ctx.runner.coding_examiner.evaluate_submission = AsyncMock(side_effect=RuntimeError("boom"))
    await h._on_coding_submit_request({"code": "c"})
    assert h.ctx.ws.send_json.await_args[0][0]["code"] == "C0001"
    rep = MagicMock()
    rep.to_dict.return_value = {"score": 1}
    h.ctx.runner.coding_examiner.evaluate_submission = AsyncMock(return_value=rep)
    await h._on_coding_submit_request({"code": "c", "test_output": "ok"})
    assert h.ctx.ws.send_json.await_args[0][0]["type"] == "coding_eval_report"


@pytest.mark.asyncio
async def test_dispatcher_spawn_gaps():
    h = _make_handler()
    try:
        reset_rate_limit()
        # silence_timeout spawn
        h.ctx.turn_busy = False
        h.ctx.closing = False
        h._spawn = MagicMock(side_effect=lambda c: (c.close(), MagicMock())[1])  # type: ignore[method-assign]
        h._on_silence_nudge = AsyncMock(return_value=None)  # type: ignore[method-assign]
        await h._on_silence_timeout({})
        h._spawn.assert_called_once()
        # barge_in spawn
        h._spawn.reset_mock()
        h.ctx.closing = False
        h._on_candidate_barge_in = AsyncMock(return_value=None)  # type: ignore[method-assign]
        await h._on_barge_in({})
        h._spawn.assert_called_once()
        # request_hint spawn (not rate limited)
        h._spawn.reset_mock()
        h._llm_rate_limited = lambda limit: False  # type: ignore[method-assign]
        h._on_request_hint = AsyncMock(return_value=None)  # type: ignore[method-assign]
        await h._start_request_hint({"question": "q"})
        h._spawn.assert_called_once()
        # request_finish spawn
        h._spawn.reset_mock()
        h.ctx.closing = False
        h._on_request_finish = AsyncMock(return_value=None)  # type: ignore[method-assign]
        await h._start_request_finish({})
        h._spawn.assert_called_once()
    finally:
        reset_rate_limit()
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_dispatcher_audio_coding_and_submit_gaps():
    h = _make_handler()
    try:
        # audio_chunk TypeError path (non-str data)
        await h._on_audio_chunk({"data": 12345})
        assert h.ctx.audio_buffer_bytes == 0
        # coding_code_update exception path
        await h._on_coding_code_update(None)  # type: ignore[arg-type]
        # coding_run exception path
        h.ctx.runner = MagicMock()
        tc = MagicMock()
        tc.to_dict.return_value = {"input": "1"}
        h.ctx.runner.coding_examiner.active_challenge.test_cases = [tc]
        with patch("realmock.domains.interview.capabilities.sandbox.evaluator.evaluate_test_cases", side_effect=RuntimeError("eval boom")):
            await h._on_coding_run_request({"code": "c"})
        # coding_submit no runner -> early return, no send
        h.ctx.ws.send_json.reset_mock()
        h.ctx.runner = None
        await h._on_coding_submit_request({"code": "c"})
        h.ctx.ws.send_json.assert_not_called()
    finally:
        await h._cancel_bg_tasks()

