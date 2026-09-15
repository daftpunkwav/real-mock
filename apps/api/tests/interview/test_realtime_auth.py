"""Authentication tests for realtime/connection/auth.py.

Covers: authenticate branches, bind_pipeline no-key/ok, announce fallbacks,
prosody binding, STT warmup, runtime rebind, session flow, remainder gaps.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler
from realmock.domains.interview.realtime.core.session_registry import reset_session_registry_for_tests

def _make_handler(sid=1, token="tok-abc"):
    """Build a mocked InterviewWSHandler bound to an in-memory websocket."""
    ws = MagicMock(accept=AsyncMock(), send_json=AsyncMock(), receive_json=AsyncMock(), close=AsyncMock())
    return InterviewWSHandler(ws, session_id=sid, access_token=token)


async def _agen(items):
    """Yield canned stream events for deterministic streaming tests."""
    for i in items:
        yield i


async def _aiter(items):
    """Yield items as an async iterator (opening-stream stub)."""
    for i in items:
        yield i

@pytest.mark.asyncio
async def test_authenticate_branches():
    reset_session_registry_for_tests()
    h = _make_handler(token="good")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    assert await h.authenticate(db) is None
    assert h.ctx.ws.send_json.await_count == 1
    h.ctx.ws.send_json.reset_mock()
    s = MagicMock(status="active", access_token="good")
    db.query.return_value.filter.return_value.first.return_value = s
    h2 = _make_handler(token="bad")
    assert await h2.authenticate(db) is None
    s2 = MagicMock(status="completed", access_token="good")
    db.query.return_value.filter.return_value.first.return_value = s2
    h3 = _make_handler(token="good")
    assert await h3.authenticate(db) is None
    s3 = MagicMock(status="active", access_token="good")
    db.query.return_value.filter.return_value.first.return_value = s3
    h4 = _make_handler(token="good")
    assert await h4.authenticate(db) is s3
    reset_session_registry_for_tests()


@pytest.mark.asyncio
async def test_bind_pipeline_no_key_and_ok(monkeypatch):
    h = _make_handler()
    llm_nokey = MagicMock(api_key="")
    monkeypatch.setattr("realmock.domains.interview.realtime.connection.auth.session_llm", lambda a, b: llm_nokey)
    cm = MagicMock()
    cm.__enter__.return_value = MagicMock()
    cm.__exit__.return_value = False
    monkeypatch.setattr("realmock.domains.interview.realtime.connection.auth.api_db_session", lambda: cm)
    assert await h.bind_pipeline(MagicMock(), MagicMock()) is False
    llm_ok = MagicMock(api_key="sk")
    monkeypatch.setattr("realmock.domains.interview.realtime.connection.auth.session_llm", lambda a, b: llm_ok)
    monkeypatch.setattr("realmock.domains.interview.realtime.connection.auth.session_stt_credentials", lambda a, b: MagicMock(provider="local", model="base", voice="v"))
    monkeypatch.setattr("realmock.domains.interview.realtime.connection.auth.session_tts_credentials", lambda a, b: MagicMock(handler="edge", voice="", mode="tts_from_text"))
    with patch("realmock.domains.interview.capabilities.rag.company_rag.CompanyKnowledgeRAG", side_effect=RuntimeError("no rag")):
        h._announce_fallbacks = AsyncMock()  # type: ignore[method-assign]
        h._bind_prosody = AsyncMock()  # type: ignore[method-assign]
        h._warmup_stt = AsyncMock()  # type: ignore[method-assign]
        sess = MagicMock(agent_state="{}", messages="[]", reference_detail="outline")
        sess.avatar_id = None
        sess.personality = "professional"
        sess.strictness = 3
        assert await h.bind_pipeline(MagicMock(), sess) is True
    assert h.ctx.llm is llm_ok and h.ctx.runner is not None


@pytest.mark.asyncio
async def test_announce_prosody_warmup_rebind_flow():
    h = _make_handler()
    h.ctx.stt_creds = MagicMock(provider="p1")
    h.ctx.tts_creds = MagicMock(handler="h1", mode="tts_from_text", voice="")
    with patch("realmock.domains.interview.realtime.connection.auth.find_provider", return_value={"status": "coming_soon", "label": "L"}):
        await h._announce_fallbacks()
    sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
    assert sum(1 for e in sent if e.get("type") == "info") >= 2
    h.ctx.agent = MagicMock()
    h.ctx.agent.session = MagicMock(avatar_id="a", personality="professional", strictness=3)
    h.ctx.tts_creds = MagicMock(handler="edge", voice="", mode="tts_from_text")
    h.ctx.tts_queue.set_prosody = MagicMock()
    h.ctx.tts_queue.set_tts_creds = MagicMock()
    h.ctx.tts_queue.set_on_sent = MagicMock()
    await h._bind_prosody()
    assert h.ctx.tts_voice != ""
    h._spawn = MagicMock(side_effect=lambda c: (c.close(), MagicMock())[1])  # type: ignore[method-assign]
    await h._warmup_stt()
    h._spawn.assert_called_once()
    s = MagicMock()
    h.ctx.agent = MagicMock()
    h.ctx.runner = MagicMock()
    h.rebind_runtime_session(s)
    assert h.ctx.agent.session is s
    h.ctx.runner = MagicMock()
    h.ctx.runner.stream_opening = MagicMock(return_value=_aiter([]))
    h._stream_events_with_tts = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
    h._open_mic_after_playback = AsyncMock()  # type: ignore[method-assign]
    h.ctx.tts_queue.start = AsyncMock()
    await h.start_session_flow(MagicMock(status="pending"), MagicMock())
    h._stream_events_with_tts.assert_awaited_once()


@pytest.mark.asyncio
async def test_auth_remainder_gaps():
    reset_session_registry_for_tests()
    h = _make_handler()
    try:
        # text_only announces captions-only
        h.ctx.stt_creds = MagicMock(provider="local")
        h.ctx.tts_creds = MagicMock(handler="edge", mode="text_only", voice="")
        h.ctx.ws.send_json.reset_mock()
        with patch("realmock.domains.interview.realtime.connection.auth.find_provider", return_value=None):
            await h._announce_fallbacks()
        sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
        assert any("Captions-only" in e.get("message", "") for e in sent)
        # non-edge handler rewrites prosody
        h.ctx.agent = MagicMock()
        h.ctx.agent.session = MagicMock(avatar_id="a", personality="professional", strictness=3)
        h.ctx.tts_creds = MagicMock(handler="custom", voice="", mode="tts_from_text")
        h.ctx.tts_voice = "orig"
        h.ctx.tts_queue.set_prosody = MagicMock()
        h.ctx.tts_queue.set_tts_creds = MagicMock()
        h.ctx.tts_queue.set_on_sent = MagicMock()
        with patch("realmock.domains.interview.realtime.connection.auth.resolve_prosody", return_value=MagicMock(rate=1.0, pitch=1.0, voice="pv")):
            await h._bind_prosody()
        assert h.ctx.tts_voice != ""
        # warmup local + non-local
        h.ctx.stt_creds = MagicMock(provider="local")
        h.ctx.whisper_model = "base"
        h._spawn = MagicMock(side_effect=lambda c: (c.close(), MagicMock())[1])  # type: ignore[method-assign]
        with patch("realmock.domains.interview.realtime.connection.auth.warmup_whisper", return_value=MagicMock()) as w:
            await h._warmup_stt()
            h._spawn.assert_called()
            assert w.called
        h._spawn.reset_mock()
        h.ctx.stt_creds = MagicMock(provider="cloud")
        h.ctx.whisper_model = "cloud-model"
        with (
            patch("realmock.domains.interview.realtime.connection.auth.is_local_stt_model", return_value=False),
            patch("realmock.domains.interview.realtime.connection.auth.warmup_whisper", return_value=MagicMock()),
        ):
            await h._warmup_stt()
            h._spawn.assert_called_once()
        # start_session_flow ACTIVE branch
        h2 = _make_handler()
        try:
            h2.ctx.tts_queue.start = AsyncMock()  # type: ignore[method-assign]
            await h2.start_session_flow(MagicMock(status="active"), MagicMock())
            assert h2.ctx.turn_state.value == "USER_SPEAKING"
            h2.ctx.tts_queue.start.assert_awaited_once()
        finally:
            await h2._cancel_bg_tasks()
    finally:
        await h._cancel_bg_tasks()
        reset_session_registry_for_tests()

