"""Turn routes tests for routes/turns.py.

Covers: collect turn result tokens/error, start/send/finish paths,
status keys, finish errors.
Conventions: no real network/LLM (all external calls mocked); uses _agen helper for event streams.
"""

import pytest
from unittest.mock import MagicMock, patch
from realmock.domains.interview.agents.events import StreamEvent
from realmock.domains.interview.routes.turns import _collect_turn_result, finish_interview, send_message, start_interview
from realmock.platform.core.errors import ApiBusinessError

async def _agen(items):
    """Yield canned stream events for deterministic route tests."""
    for i in items:
        yield i

@pytest.mark.asyncio
async def test_collect_tokens_and_error():
    evs = [StreamEvent.make_token("Hi "), StreamEvent.make_turn_done(content="Hi", phase_id="p", is_complete=False, phase_changed=False)]
    c, done = await _collect_turn_result(_agen(evs))
    assert c == "Hi" and done is False
    errs = [StreamEvent.make_error("bad", code="A2002")]
    try:
        await _collect_turn_result(_agen(errs))
        assert False
    except ApiBusinessError as e:
        assert e.error_code == "A2002"


@pytest.mark.asyncio
async def test_start_send_finish_paths():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    try:
        await start_interview(1, db=db, access="t")
        assert False
    except ApiBusinessError as e:
        assert e.error_code == "A2001"
    sess = MagicMock(status="active", access_token="tok", current_phase="p", agent_state="{}")
    db.query.return_value.filter.return_value.first.return_value = sess
    try:
        await send_message(1, MagicMock(content="hi"), db=db, access="bad")
        assert False
    except ApiBusinessError as e:
        assert e.error_code == "A0401"
    sess2 = MagicMock(status="completed", access_token="tok", overall_score=80)
    db.query.return_value.filter.return_value.first.return_value = sess2
    out = await finish_interview(1, db=db, access="tok")
    assert out.status == "already_completed"
    sess3 = MagicMock(status="active", access_token="tok", current_phase="p", overall_score=None)
    db.query.return_value.filter.return_value.first.return_value = sess3
    with patch("realmock.domains.interview.routes.turns.run_finish_lifecycle", return_value=None):
        out2 = await finish_interview(1, db=db, access="tok")
        assert out2.status == "completed"


@pytest.mark.asyncio
async def test_status_key_and_finish_errors():
    db = MagicMock()
    s = MagicMock(status="completed", access_token="tok")
    db.query.return_value.filter.return_value.first.return_value = s
    try:
        await start_interview(1, db=db, access="tok")
        assert False
    except ApiBusinessError as e:
        assert e.error_code == "A2002"
    s2 = MagicMock(status="pending", access_token="tok")
    db.query.return_value.filter.return_value.first.return_value = s2
    with patch("realmock.domains.interview.routes.turns.session_llm", return_value=MagicMock(api_key="")):
        try:
            await start_interview(1, db=db, access="tok")
            assert False
        except ApiBusinessError as e:
            assert e.error_code == "A0006"
    sess = MagicMock(status="pending", access_token="tok", current_phase="p")
    sess.agent_state = "{}"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = sess
    llm = MagicMock(api_key="sk")
    runner = MagicMock()
    async def _op(db2):
        yield StreamEvent.make_turn_done(content="open", phase_id="p", is_complete=False, phase_changed=False)
    runner.stream_opening = _op
    with patch("realmock.domains.interview.routes.turns.session_llm", return_value=llm):
        with patch("realmock.domains.interview.routes.turns.InterviewRunner", return_value=runner):
            with patch("realmock.domains.interview.routes.turns.InterviewSessionState", return_value=MagicMock(phases_remaining=lambda: [])):
                out = await start_interview(1, db=db, access="tok")
                assert out["message"].content == "open"
    sess2 = MagicMock(status="active", access_token="tok", current_phase="p")
    db.query.return_value.filter.return_value.first.return_value = sess2
    async def _tu(*a, **k):
        yield StreamEvent.make_token("a")
        yield StreamEvent.make_turn_done(content="a", phase_id="p", is_complete=False, phase_changed=False)
    runner.stream_turn = _tu
    body = MagicMock(content="hi", face_analysis=None, image_base64=None)
    with patch("realmock.domains.interview.routes.turns.session_llm", return_value=llm):
        with patch("realmock.domains.interview.routes.turns.InterviewRunner", return_value=runner):
            with patch("realmock.domains.interview.routes.turns.InterviewSessionState", return_value=MagicMock(phases_remaining=lambda: ["x"])):
                out2 = await send_message(1, body, db=db, access="tok")
                assert out2.message.content == "a"

