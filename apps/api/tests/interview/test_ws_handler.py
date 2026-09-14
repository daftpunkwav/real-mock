"""``realmock.domains.interview.realtime.ws_handler`` unit and state-machine tests.

Coverage:
- import smoke: a clean checkout must be able to load InterviewWSHandler;
- audio_buffer limit protection (>5 MB forces a clear + error event);
- deadlock fallback: the error path returns to ``USER_SPEAKING``;
- SessionEvent.schema_version defaults to 1;
- ``_dispatch`` does not raise on an unrecognized message type;
- pong messages do not trigger business processing;
- barge-in epoch / playback-generation machinery;
- STT always runs on the user turn end path.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from realmock.domains.interview.realtime import ws_handler
from realmock.domains.interview.realtime.core.events import SessionEvent, TurnState
from realmock.domains.interview.agents.events import EventKind, StreamEvent
from realmock.platform.capabilities.voice.stt import SttCredentials, SttResult


def test_ws_handler_importable() -> None:
    """Import smoke test: a clean checkout must be able to load InterviewWSHandler."""
    assert ws_handler.InterviewWSHandler is not None


def _make_mock_ws() -> MagicMock:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


def _audio_b64(n_bytes: int) -> str:
    """Return the base64-encoded pcm payload of length n_bytes."""
    return base64.b64encode(b"\x00" * n_bytes).decode("ascii")


class TestSessionEvent:
    def test_default_schema_version(self) -> None:
        ev = SessionEvent(type="test")
        assert ev.schema_version == 1
        assert ev.type == "test"
        assert ev.payload == {}


class TestAudioBufferCap:
    def test_buffer_limit_constant_pin(self) -> None:
        assert ws_handler._AUDIO_BUFFER_MAX_BYTES == 5 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_audio_chunk_appends(self) -> None:
        from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        # Mock dispatch
        await handler._dispatch(
            {"type": "audio_chunk", "data": _audio_b64(64)},
            db=MagicMock(),
            session=MagicMock(),
        )
        assert len(handler.ctx.audio_buffer) == 1

    @pytest.mark.asyncio
    async def test_audio_buffer_overflow_clears(self) -> None:
        from realmock.domains.interview.realtime.ws_handler import (
            InterviewWSHandler,
            _AUDIO_BUFFER_MAX_BYTES,
        )

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        # Insert a chunk that exceeds the limit in one operation
        huge = _audio_b64(_AUDIO_BUFFER_MAX_BYTES + 1024)
        await handler._dispatch(
            {"type": "audio_chunk", "data": huge},
            db=MagicMock(),
            session=MagicMock(),
        )
        # Values above the threshold should be cleared and an error emitted
        assert handler.ctx.audio_buffer == []
        # At least one error event
        ws.send_json.assert_called()
        sent = [c.args[0] for c in ws.send_json.call_args_list]
        assert any(e.get("type") == "error" for e in sent)


class TestDispatchUnknownType:
    @pytest.mark.asyncio
    async def test_unknown_type_no_op(self) -> None:
        from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        # Unknown messages should not throw
        await handler._dispatch(
            {"type": "nonsense_unknown"},
            db=MagicMock(),
            session=MagicMock(),
        )
        ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_pong_no_op(self) -> None:
        from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        await handler._dispatch(
            {"type": "pong", "t": 123},
            db=MagicMock(),
            session=MagicMock(),
        )
        ws.send_json.assert_not_called()


class TestTurnState:
    def test_values(self) -> None:
        assert TurnState.USER_SPEAKING.value == "USER_SPEAKING"
        assert TurnState.AI_SPEAKING.value == "AI_SPEAKING"
        assert TurnState.PROCESSING.value == "PROCESSING"
        assert TurnState.IDLE.value == "IDLE"


class TestSetTurn:
    @pytest.mark.asyncio
    async def test_set_turn_emits_turn_state_event(self) -> None:
        from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        await handler.set_turn(TurnState.USER_SPEAKING)
        assert handler.ctx.turn_state == TurnState.USER_SPEAKING
        ws.send_json.assert_called_once_with(
            {"type": "turn_state", "state": "USER_SPEAKING"}
        )


class TestSessionConnectionMutex:
    @pytest.mark.asyncio
    async def test_claim_kicks_previous_handler(self) -> None:
        """When a new connection claims the same session, the old connection should be marked and closed."""
        from realmock.domains.interview.realtime import ws_handler as ws_mod

        ws_mod.reset_session_registry_for_tests()
        old_ws = _make_mock_ws()
        new_ws = _make_mock_ws()
        old_ws.close = AsyncMock()
        new_ws.close = AsyncMock()

        old_h = ws_mod.InterviewWSHandler(old_ws, session_id=42)
        new_h = ws_mod.InterviewWSHandler(new_ws, session_id=42)

        await ws_mod.claim_session_connection(old_h)
        assert old_h._superseded is False
        assert ws_mod.active_handlers_for_tests()[42] is old_h

        await ws_mod.claim_session_connection(new_h)
        assert old_h._superseded is True
        assert new_h._superseded is False
        assert ws_mod.active_handlers_for_tests()[42] is new_h
        old_ws.close.assert_awaited()
        # The old connection should receive an error notification
        sent = [c.args[0] for c in old_ws.send_json.call_args_list]
        assert any(e.get("type") == "error" for e in sent)

        # Releasing the displaced old handler must not accidentally remove the new connection
        await ws_mod.release_session_connection(old_h)
        assert ws_mod.active_handlers_for_tests()[42] is new_h

        await ws_mod.release_session_connection(new_h)
        assert 42 not in ws_mod.active_handlers_for_tests()

    @pytest.mark.asyncio
    async def test_different_sessions_independent(self) -> None:
        from realmock.domains.interview.realtime import ws_handler as ws_mod

        ws_mod.reset_session_registry_for_tests()
        h1 = ws_mod.InterviewWSHandler(_make_mock_ws(), session_id=1)
        h2 = ws_mod.InterviewWSHandler(_make_mock_ws(), session_id=2)
        await ws_mod.claim_session_connection(h1)
        await ws_mod.claim_session_connection(h2)
        assert h1._superseded is False
        assert h2._superseded is False
        assert ws_mod.active_handlers_for_tests()[1] is h1
        assert ws_mod.active_handlers_for_tests()[2] is h2
        await ws_mod.release_session_connection(h1)
        await ws_mod.release_session_connection(h2)


class TestTraceId:
    @pytest.mark.asyncio
    async def test_handle_sets_trace_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The handle() entry point should inject trace_id in the form ws-{session}-{uuid}."""
        from realmock.platform.core.logging import get_trace_id
        from realmock.domains.interview.realtime import ws_handler as ws_mod
        from realmock.platform.capabilities.ai.llm.client import LLMClient

        captured_tid: list[str] = []

        class _StubRunner:
            async def stream_opening(self, db):
                if False:
                    yield  # Empty async generator

        monkeypatch.setattr(LLMClient, "from_db", classmethod(lambda cls, db: MagicMock(api_key="")))
        monkeypatch.setattr(
            "realmock.domains.interview.realtime.core.context.InterviewOrchestrator", MagicMock()
        )
        monkeypatch.setattr(
            "realmock.domains.interview.realtime.connection.auth.InterviewRunner",
            lambda *a, **kw: _StubRunner(),
        )
        # Mock db.query to obtain the session
        class _StubSession:
            id = 1
            status = "completed"  # Make handle return early without sending opening
            access_token = "test-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = _StubSession()
        # handle() is defined in the connection_lifecycle module, so patch SessionLocal in that module.
        monkeypatch.setattr(
            "realmock.domains.interview.realtime.connection.lifecycle.SessionLocal", lambda: mock_db
        )

        ws = _make_mock_ws()
        handler = ws_mod.InterviewWSHandler(
            ws, session_id=1, access_token=_StubSession.access_token
        )
        # Because status=completed, handle sends error and then returns.
        await handler.handle()

        # trace_id should now be injected (set_trace_id is a module-level ContextVar).
        tid = get_trace_id()
        assert tid.startswith("ws-1-")
        captured_tid.append(tid)


class TestFailAndClose:
    """Authentication and state-failure paths should consistently send error + ws.close(4401)."""

    @staticmethod
    def _patch_session_db(
        monkeypatch: pytest.MonkeyPatch, session: object | None
    ) -> MagicMock:
        """Patch SessionLocal in the connection_lifecycle module (where handle is defined)."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = session
        monkeypatch.setattr(
            "realmock.domains.interview.realtime.connection.lifecycle.SessionLocal", lambda: mock_db
        )
        return mock_db

    @pytest.mark.asyncio
    async def test_wrong_token_closes_4401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

        class _StubSession:
            id = 1
            status = "pending"
            access_token = "correct-token-aaaaaaaaaaaaaaaaaaaa"

        self._patch_session_db(monkeypatch, _StubSession())

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1, access_token="wrong-token")
        await handler.handle()

        # Send an error first, then close with 4401
        assert ws.send_json.await_count == 1
        assert ws.send_json.await_args[0][0]["type"] == "error"
        ws.close.assert_awaited_once_with(code=4401)

    @pytest.mark.asyncio
    async def test_missing_session_closes_4401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

        self._patch_session_db(monkeypatch, None)

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=999)
        await handler.handle()

        assert ws.send_json.await_count == 1
        assert ws.send_json.await_args[0][0]["type"] == "error"
        ws.close.assert_awaited_once_with(code=4401)

    @pytest.mark.asyncio
    async def test_finished_session_closes_4401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

        class _StubSession:
            id = 1
            status = "completed"
            access_token = "test-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        self._patch_session_db(monkeypatch, _StubSession())

        ws = _make_mock_ws()
        handler = InterviewWSHandler(
            ws, session_id=1, access_token="test-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        await handler.handle()

        # The state check now occurs before claim/initialization: a completed session immediately sends "The interview has ended".
        assert ws.send_json.await_count == 1
        err = ws.send_json.await_args[0][0]
        assert err["type"] == "error"
        assert err["message"] == "The interview has ended"
        ws.close.assert_awaited_once_with(code=4401)


def _make_handler() -> ws_handler.InterviewWSHandler:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()
    return ws_handler.InterviewWSHandler(ws, session_id=1)


class TestBargeEpoch:
    def test_can_start_after_barge_invalidates_busy(self) -> None:
        h = _make_handler()
        epoch = h._begin_user_turn()
        assert epoch is not None
        assert h.ctx.turn_busy is True
        assert not h._can_start_user_turn()
        # Simulate barge-in: advance the stream epoch without blindly clearing busy.
        h.ctx.stream_epoch += 1
        assert h._can_start_user_turn()
        new_epoch = h._begin_user_turn()
        assert new_epoch == h.ctx.stream_epoch
        # Finishing the old turn must not clear the new turn's lock
        h._end_user_turn(epoch)
        assert h.ctx.turn_busy is True
        h._end_user_turn(new_epoch)
        assert h.ctx.turn_busy is False

    @pytest.mark.asyncio
    async def test_barge_bumps_playback_generation(self) -> None:
        h = _make_handler()
        h.ctx.turn_state = TurnState.AI_SPEAKING
        h.ctx.awaiting_playback_gen = 3
        h.ctx.playback_generation = 3
        h.ctx.stream_epoch = 1
        h.ctx.tts_queue.clear = AsyncMock()
        await h._on_candidate_barge_in()
        assert h.ctx.stream_epoch == 2
        assert h.ctx.playback_generation == 4
        assert h.ctx.awaiting_playback_gen == 4
        assert h.ctx.turn_state == TurnState.USER_SPEAKING
        h.ctx.tts_queue.clear.assert_awaited()
        sent = [c.args[0] for c in h.ws.send_json.call_args_list]
        assert any(e.get("type") == "tts_interrupted" for e in sent)
        interrupted = next(e for e in sent if e.get("type") == "tts_interrupted")
        assert interrupted.get("playback_generation") == 4

    @pytest.mark.asyncio
    async def test_stream_returns_none_after_barge_epoch(self) -> None:
        h = _make_handler()
        h.ctx.stream_epoch = 5
        h.ctx.tts_queue.enqueue = AsyncMock()
        h.ctx.tts_queue.flush_remainder = AsyncMock()

        async def events():
            # Simulate a mid-stream barge-in: advance the epoch
            h.ctx.stream_epoch += 1
            yield StreamEvent(
                kind=EventKind.TOKEN,
                token="Hello",
            )
            yield StreamEvent(
                kind=EventKind.TURN_COMPLETE,
                content="Hello",
                phase_id="intro",
                is_complete=False,
            )

        last = await h._stream_events_with_tts(events(), auto_hint=False)
        assert last is None
        h.ctx.tts_queue.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_user_text_skips_open_mic_after_barge(self) -> None:
        h = _make_handler()
        h.ctx.runner = MagicMock()
        h._open_mic_after_playback = AsyncMock()
        start_epoch = h.ctx.stream_epoch

        async def fake_stream(*_a, **_k):
            h.ctx.stream_epoch = start_epoch + 1
            h.ctx.turn_state = TurnState.USER_SPEAKING
            return None

        h._stream_events_with_tts = fake_stream  # type: ignore[method-assign]
        h._consume_runner_turn = MagicMock(return_value=None)
        await h._process_user_text("Answer", {}, MagicMock(), MagicMock())
        h._open_mic_after_playback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_open_mic_aborts_when_epoch_changed(self) -> None:
        h = _make_handler()
        h.ctx.tts_sent_this_turn = False
        h.ctx.turn_state = TurnState.AI_SPEAKING
        epoch = h.ctx.stream_epoch

        async def wait_then_barge():
            h.ctx.stream_epoch = epoch + 1
            h.ctx.turn_state = TurnState.USER_SPEAKING

        h._wait_client_playback = wait_then_barge  # type: ignore[method-assign]
        h.set_turn = AsyncMock()
        await h._open_mic_after_playback(wait_playback=True)
        h.set_turn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_open_mic_by_default_skips_playback_wait(self) -> None:
        """Mic opens at text-complete: no playback wait on the default path."""
        h = _make_handler()
        h.ctx.tts_sent_this_turn = True
        h.ctx.turn_state = TurnState.AI_SPEAKING
        h._wait_client_playback = AsyncMock()  # type: ignore[method-assign]
        h.set_turn = AsyncMock()
        await h._open_mic_after_playback()
        h._wait_client_playback.assert_not_awaited()
        h.set_turn.assert_awaited_once_with(TurnState.USER_SPEAKING)

    @pytest.mark.asyncio
    async def test_cancel_pending_playback_interrupts_stale_audio(self) -> None:
        """A text reply while TTS is in flight stops the stale audio."""
        h = _make_handler()
        h.ctx.tts_sent_this_turn = True
        h.ctx.playback_done.clear()
        h.ctx.tts_queue.clear = AsyncMock()
        gen = h.ctx.playback_generation
        await h._cancel_pending_playback()
        h.ctx.tts_queue.clear.assert_awaited()
        assert h.ctx.playback_generation == gen + 1
        assert h.ctx.tts_sent_this_turn is False
        sent = [c.args[0] for c in h.ws.send_json.call_args_list]
        interrupted = [e for e in sent if e.get("type") == "tts_interrupted"]
        assert len(interrupted) == 1
        assert interrupted[0].get("reason") == "candidate_text_reply"

    @pytest.mark.asyncio
    async def test_cancel_pending_playback_noop_when_idle(self) -> None:
        """No TTS in flight: no clear, no event, nothing sent."""
        h = _make_handler()
        h.ctx.tts_sent_this_turn = False
        h.ctx.tts_queue.clear = AsyncMock()
        await h._cancel_pending_playback()
        h.ctx.tts_queue.clear.assert_not_awaited()
        h.ws.send_json.assert_not_called()


class TestSttAlwaysRuns:
    @pytest.mark.asyncio
    async def test_asr_always_called_for_pcm(self) -> None:
        h = _make_handler()
        h.ctx.turn_state = TurnState.USER_SPEAKING
        h.ctx.agent = None
        h.ctx.llm = MagicMock(api_base="https://api.openai.com/v1", api_key="sk-t")
        h.ctx.stt_creds = SttCredentials(
            provider="openai_compat",
            api_base=h.ctx.llm.api_base,
            api_key="sk-stt",
            model="whisper-1",
        )
        h._process_user_text = AsyncMock()
        with patch(
            "realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result",
            new_callable=AsyncMock,
            return_value=SttResult(text="This is a sufficiently long technical answer in English", provider="local"),
        ) as mock_tr:
            await h._on_user_turn_end(
                {
                    "text": "This is a sufficiently long technical answer in English",
                    "pcm": "AAAA",
                    "sample_rate": 16000,
                },
                db=MagicMock(),
                session=MagicMock(),
            )
            mock_tr.assert_awaited()
            h._process_user_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_asr_preferred_for_english_mix(self) -> None:
        h = _make_handler()
        h.ctx.turn_state = TurnState.USER_SPEAKING
        h.ctx.agent = None
        h.ctx.llm = MagicMock(api_base="https://api.openai.com/v1", api_key="sk-t")
        h.ctx.stt_creds = SttCredentials(
            provider="openai_compat",
            api_base=h.ctx.llm.api_base,
            api_key="sk-stt",
            model="whisper-1",
        )
        h._process_user_text = AsyncMock()
        with patch(
            "realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result",
            new_callable=AsyncMock,
            return_value=SttResult(text="I used React hooks", provider="local"),
        ) as mock_tr:
            await h._on_user_turn_end(
                {
                    "text": "I have used React hooks",
                    "pcm": "AAAA",
                    "sample_rate": 16000,
                },
                db=MagicMock(),
                session=MagicMock(),
            )
            mock_tr.assert_awaited()
            assert h._process_user_text.await_args.args[0] == "I used React hooks"


class TestDispatchTable:
    def test_table_entries_resolve_on_handler(self) -> None:
        from realmock.domains.interview.realtime.core.message_dispatcher import (
            MessageDispatcherMixin,
        )
        from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

        missing = [
            name
            for name in MessageDispatcherMixin._MESSAGE_HANDLER_NAMES.values()
            if not callable(getattr(InterviewWSHandler, name, None))
        ]
        assert missing == []

    def test_table_covers_production_message_types(self) -> None:
        from realmock.domains.interview.realtime.core.message_dispatcher import (
            MessageDispatcherMixin,
        )

        assert set(MessageDispatcherMixin._MESSAGE_HANDLER_NAMES) == {
            "audio_chunk",
            "stt_text",
            "pong",
            "vision_update",
            "user_turn_end",
            "silence_timeout",
            "barge_in",
            "user_text",
            "request_hint",
            "request_finish",
            "tts_playback_done",
        }

    @pytest.mark.asyncio
    async def test_broken_table_entry_warns_without_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

        ws = _make_mock_ws()
        handler = InterviewWSHandler(ws, session_id=1)
        monkeypatch.setattr(
            handler,
            "_MESSAGE_HANDLER_NAMES",
            {"bogus": "_missing_method"},
        )
        await handler._dispatch({"type": "bogus"}, db=MagicMock(), session=MagicMock())
        ws.send_json.assert_not_called()

    def test_audio_limit_single_sourced(self) -> None:
        from realmock.domains.interview.realtime import ws_handler as ws_module
        from realmock.domains.interview.realtime.turn import stt_finish
        from realmock.platform.core.constants import AUDIO_BUFFER_MAX_BYTES

        assert ws_module._AUDIO_BUFFER_MAX_BYTES == AUDIO_BUFFER_MAX_BYTES
        assert stt_finish._AUDIO_BUFFER_MAX_BYTES == AUDIO_BUFFER_MAX_BYTES
