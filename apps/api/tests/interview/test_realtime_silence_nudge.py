"""Silence nudge tests for realtime/control/silence_nudge.py.

Covers: nudge guards/helpers, full probe and capped/closing paths,
session-missing/fallback/ledger-fail, closing nudge variants.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

def _make_handler(sid=301):
    """Build a mocked InterviewWSHandler bound to an in-memory websocket."""
    ws = MagicMock(accept=AsyncMock(), send_json=AsyncMock(), receive_json=AsyncMock(), close=AsyncMock())
    return InterviewWSHandler(ws, session_id=sid)


def _agent_with_assistant(text="\u8bf7\u4ecb\u7ecd\u4e00\u4e0b\u4f60\u81ea\u5df1?"):
    """Build a fake agent carrying one assistant message for nudge tests."""
    ag = MagicMock()
    ag.plan = SimpleNamespace(source="agent", language="zh")
    ag.messages = [{"role": "assistant", "content": text}]
    ag.agent_state = {}
    return ag

@pytest.mark.asyncio
async def test_nudge_guards_and_helpers():
    h = _make_handler()
    try:
        # not USER_SPEAKING -> return
        h.ctx.turn_state = TurnState.IDLE
        await h._on_silence_nudge()
        h.ctx.ws.send_json.assert_not_called()
        # tts in flight, not stale -> return
        h.ctx.turn_state = TurnState.USER_SPEAKING
        h.ctx.tts_sent_this_turn = True
        h.ctx.playback_done.clear()
        h.ctx.last_tts_sent_at = asyncio.get_event_loop().time()
        h.ctx.speech_end_at = 0.0
        h.ctx.mic_opened_at = 0.0
        h.ctx.nudge_grace_sec = 1000.0
        await h._on_silence_nudge()
        h.ctx.ws.send_json.assert_not_called()
        # grace -> return
        h.ctx.tts_sent_this_turn = False
        h.ctx.playback_done.set()
        now = asyncio.get_event_loop().time()
        h.ctx.speech_end_at = now
        h.ctx.nudge_grace_sec = 1000.0
        await h._on_silence_nudge()
        h.ctx.ws.send_json.assert_not_called()
        # cooldown -> return
        h.ctx.speech_end_at = 0.0
        h.ctx.mic_opened_at = 0.0
        h.ctx.nudge_grace_sec = 0.0
        h.ctx.nudge_cooldown_sec = 10.0
        h.ctx.last_wait_seconds = 0.0
        h.ctx.last_nudge_at = now
        await h._on_silence_nudge()
        h.ctx.ws.send_json.assert_not_called()
        # helpers
        h.ctx.agent = None
        assert h._last_assistant_text() == ""
        assert h._assistant_message_count() == 0
        h._append_to_last_assistant("x")  # no-op
        h.ctx.agent = MagicMock()
        h.ctx.agent.messages = [{"role": "user", "content": "hi"}]
        assert h._last_assistant_text() == ""
        assert h._assistant_message_count() == 0
        h.ctx.agent.messages = [{"role": "assistant", "content": "Q1?"}]
        assert h._last_assistant_text() == "Q1?"
        h._append_to_last_assistant("follow?")
        assert "follow?" in h.ctx.agent.messages[0]["content"]
        h._append_to_last_assistant("")  # empty no-op
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_nudge_full_probe_and_capped_and_closing():
    h = _make_handler()
    try:
        h.ctx.turn_state = TurnState.USER_SPEAKING
        h.ctx.tts_sent_this_turn = False
        h.ctx.playback_done.set()
        h.ctx.speech_end_at = 0.0
        h.ctx.mic_opened_at = 0.0
        h.ctx.nudge_grace_sec = 0.0
        h.ctx.nudge_cooldown_sec = 0.0
        h.ctx.last_wait_seconds = 0.0
        h.ctx.last_nudge_at = 0.0
        h.ctx.agent = _agent_with_assistant("请讲讲缓存项目?")
        h.ctx.agent.messages = [{"role": "assistant", "content": "请讲讲缓存项目?"}]
        h.ctx.silence_probe_msg_count = 0
        h.ctx.silence_probe_seq = 0
        h.ctx.silence_capped = False
        h.ctx.last_silence_probe = ""
        sess = MagicMock(personality="professional", strictness=3, current_phase="tech")
        db = MagicMock()
        db.close = MagicMock()
        h._load_session = MagicMock(return_value=sess)  # type: ignore[method-assign]
        h._generate_silence_probe = AsyncMock(return_value="换个角度讲讲缓存?")  # type: ignore[method-assign]
        h._speak_one = AsyncMock()  # type: ignore[method-assign]
        h._open_mic_after_playback = AsyncMock()  # type: ignore[method-assign]
        h._begin_playback_wait = MagicMock()  # type: ignore[method-assign]
        with (
            patch("realmock.domains.interview.realtime.control.silence_nudge.SessionLocal", return_value=db),
            patch("realmock.domains.interview.realtime.control.silence_nudge.append_last_turn_flag", return_value=None),
        ):
            await h._on_silence_nudge()
        assert h.ctx.silence_probe_seq == 1
        assert h.ctx.silence_probe_question == "请讲讲缓存项目?"
        sent = [c.args[0]["type"] for c in h.ctx.ws.send_json.call_args_list]
        assert "silence_nudge" in sent
        # capped -> updates last_nudge_at and returns
        h.ctx.silence_capped = True
        h.ctx.ws.send_json.reset_mock()
        with patch("realmock.domains.interview.realtime.control.silence_nudge.SessionLocal", return_value=db):
            await h._on_silence_nudge()
        # seq >= cap -> closing nudge
        h2 = _make_handler()
        try:
            h2.ctx.turn_state = TurnState.USER_SPEAKING
            h2.ctx.tts_sent_this_turn = False
            h2.ctx.playback_done.set()
            h2.ctx.speech_end_at = 0.0
            h2.ctx.mic_opened_at = 0.0
            h2.ctx.nudge_grace_sec = 0.0
            h2.ctx.nudge_cooldown_sec = 0.0
            h2.ctx.last_wait_seconds = 0.0
            h2.ctx.last_nudge_at = 0.0
            h2.ctx.agent = _agent_with_assistant("Q?")
            h2.ctx.silence_probe_msg_count = 1
            h2.ctx.silence_probe_seq = 2
            h2.ctx.silence_capped = False
            h2._speak_one = AsyncMock()  # type: ignore[method-assign]
            h2._open_mic_after_playback = AsyncMock()  # type: ignore[method-assign]
            h2._begin_playback_wait = MagicMock()  # type: ignore[method-assign]
            h2._load_session = MagicMock(return_value=sess)  # type: ignore[method-assign]
            db2 = MagicMock()
            db2.close = MagicMock()
            with (
                patch("realmock.domains.interview.realtime.control.silence_nudge.SessionLocal", return_value=db2),
                patch("realmock.domains.interview.realtime.control.silence_nudge.append_last_turn_flag", return_value=None),
            ):
                await h2._on_silence_nudge()
            assert h2.ctx.silence_capped is True
        finally:
            await h2._cancel_bg_tasks()
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_nudge_session_missing_and_fallback_and_ledger_fail():
    h = _make_handler()
    try:
        h.ctx.turn_state = TurnState.USER_SPEAKING
        h.ctx.tts_sent_this_turn = False
        h.ctx.playback_done.set()
        h.ctx.speech_end_at = 0.0
        h.ctx.mic_opened_at = 0.0
        h.ctx.nudge_grace_sec = 0.0
        h.ctx.nudge_cooldown_sec = 0.0
        h.ctx.last_wait_seconds = 0.0
        h.ctx.last_nudge_at = 0.0
        h.ctx.agent = _agent_with_assistant("讲讲项目?")
        h.ctx.silence_probe_msg_count = 1
        h.ctx.silence_probe_seq = 0
        h.ctx.silence_capped = False
        h.ctx.last_silence_probe = "same?"
        h._load_session = MagicMock(return_value=None)  # type: ignore[method-assign]
        h._generate_silence_probe = AsyncMock(return_value="x")  # type: ignore[method-assign]
        db = MagicMock()
        db.close = MagicMock(side_effect=RuntimeError("close boom"))
        with patch("realmock.domains.interview.realtime.control.silence_nudge.SessionLocal", return_value=db):
            await h._on_silence_nudge()  # session None -> early return, close fails swallowed
        # fallback to orchestrator when probe empty/duplicate + ledger failure
        h.ctx.last_nudge_at = 0.0
        h.ctx.silence_probe_seq = 0
        sess = MagicMock(personality="professional", strictness=3, current_phase="tech")
        h._load_session = MagicMock(return_value=sess)  # type: ignore[method-assign]
        h._generate_silence_probe = AsyncMock(return_value="same?")  # type: ignore[method-assign]
        h.ctx.orchestrator.build_silence_nudge = MagicMock(return_value="模板追问")  # type: ignore[method-assign]
        h._speak_one = AsyncMock()  # type: ignore[method-assign]
        h._open_mic_after_playback = AsyncMock()  # type: ignore[method-assign]
        h._begin_playback_wait = MagicMock()  # type: ignore[method-assign]
        db2 = MagicMock()
        db2.close = MagicMock()
        with (
            patch("realmock.domains.interview.realtime.control.silence_nudge.SessionLocal", return_value=db2),
            patch("realmock.domains.interview.realtime.control.silence_nudge.append_last_turn_flag", side_effect=RuntimeError("ledger boom")),
        ):
            await h._on_silence_nudge()
        assert h.ctx.last_silence_probe == "模板追问"
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_speak_closing_nudge_variants():
    h = _make_handler()
    try:
        h.ctx.agent = MagicMock()
        h.ctx.agent.plan = SimpleNamespace(source="agent", language="en")
        h._speak_one = AsyncMock()  # type: ignore[method-assign]
        h._open_mic_after_playback = AsyncMock()  # type: ignore[method-assign]
        h._begin_playback_wait = MagicMock()  # type: ignore[method-assign]
        sess = MagicMock()
        h._load_session = MagicMock(return_value=sess)  # type: ignore[method-assign]
        db = MagicMock()
        db.close = MagicMock()
        with (
            patch("realmock.domains.interview.realtime.control.silence_nudge.SessionLocal", return_value=db),
            patch("realmock.domains.interview.realtime.control.silence_nudge.append_last_turn_flag", side_effect=RuntimeError("boom")),
        ):
            await h._speak_closing_nudge()
        assert "can't hear" in h.ctx.last_silence_probe
        # session None + close fail
        h._load_session = MagicMock(return_value=None)  # type: ignore[method-assign]
        db2 = MagicMock()
        db2.close = MagicMock(side_effect=RuntimeError("close boom"))
        with patch("realmock.domains.interview.realtime.control.silence_nudge.SessionLocal", return_value=db2):
            await h._speak_closing_nudge()
    finally:
        await h._cancel_bg_tasks()

