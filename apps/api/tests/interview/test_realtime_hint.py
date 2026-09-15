"""Hint tests for realtime/control/hint.py.

Covers: background/candidate slice, question extraction, empty LLM/question,
outline success/timeout/error/empty, full-mode degrade/success,
rate-limited EN, outline both languages, full reference branches.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.interview.realtime.core.session_registry import reset_session_registry_for_tests
from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

def _make_handler(sid=101):
    """Build a mocked InterviewWSHandler bound to an in-memory websocket."""
    ws = MagicMock(accept=AsyncMock(), send_json=AsyncMock(), receive_json=AsyncMock(), close=AsyncMock())
    return InterviewWSHandler(ws, session_id=sid)


def _seed_outline(h, lang="zh"):
    """Seed handler with a mocked LLM and outline plan for hint generation."""
    h.ctx.llm = MagicMock()
    h.ctx.llm.chat = AsyncMock(return_value="hint body")
    if lang == "en":
        plan = SimpleNamespace(source="agent", language="en-US")
    else:
        plan = SimpleNamespace(source="agent", language="zh")
    h.ctx.agent = MagicMock()
    h.ctx.agent.plan = plan
    h.ctx.agent.messages = [
        {"role": "system", "content": "## Interview setup\nRole: BE\n## Candidate profile\nAda\n## Current phase\nx"},
    ]
    return h

@pytest.mark.asyncio
async def test_hint_background_and_candidate_slice_branches():
    reset_session_registry_for_tests()
    h = _make_handler()
    try:
        h.ctx.agent = MagicMock()
        h.ctx.agent.messages = [{"role": "user", "content": "hi"}]
        assert h._hint_background() == ""
        h.ctx.agent.messages = [{"role": "system", "content": "plain head no markers here"}]
        assert h._hint_background() == "plain head no markers here"
        h.ctx.agent = None
        assert h._hint_background() == ""
        # end <= start branch: marker present but no Current phase
        only_setup = "## Interview setup\nRole: BE\nprofile stuff here"
        sl = h._candidate_slice(only_setup, limit=50)
        assert "Interview setup" in sl
        # end after start branch
        full = "## Interview setup\nA\n## Candidate profile\nB\n## Current phase\nC\n## Behavior\nD"
        sl2 = h._candidate_slice(full, limit=1200)
        assert "Candidate profile" in sl2
        assert "Behavior" not in sl2
    finally:
        reset_session_registry_for_tests()
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_extract_hint_question_variants():
    h = _make_handler()
    try:
        assert h._extract_hint_question("") == ""
        assert h._extract_hint_question("   \n  ") == ""
        assert h._extract_hint_question("hello, please tell me about yourself") == "hello, please tell me about yourself"
        assert "?" in h._extract_hint_question("intro line\nWhat did you do?")
        assert h._extract_hint_question("line1\nintroduce yourself") == "introduce yourself"
        assert h._extract_hint_question("chat about cache") == "chat about cache"
        assert h._extract_hint_question("no marker\nstill none") == "still none"
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_on_request_hint_empty_llm_and_empty_question():
    h = _make_handler()
    try:
        h.ctx.llm = None
        h.ctx.agent = MagicMock()
        h.ctx.agent.plan = SimpleNamespace(source="agent", language="zh")
        await h._on_request_hint({"question": "hello"})
        assert h.ctx.ws.send_json.await_args[0][0]["type"] == "reference_hint"
        h.ctx.ws.send_json.reset_mock()
        await h._on_request_hint({"question": "   "})
        assert h.ctx.ws.send_json.await_args[0][0]["type"] == "reference_hint"
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_on_request_hint_outline_success_timeout_error():
    h = _make_handler()
    try:
        _seed_outline(h)
        h._generate_reference_hint = AsyncMock(return_value="outline <think>x</think>")  # type: ignore[method-assign]
        await h._on_request_hint({"question": "讲讲你的项目？详细介绍下"})
        events = [c.args[0]["type"] for c in h.ctx.ws.send_json.call_args_list]
        assert "reference_hint_loading" in events
        assert "reference_hint" in events
        assert h.ctx.hint_inflight is None

        # timeout path
        h.ctx.ws.send_json.reset_mock()
        _seed_outline(h)
        h._generate_reference_hint = AsyncMock(side_effect=asyncio.TimeoutError())  # type: ignore[method-assign]
        await h._on_request_hint({"question": "超时问题?"})
        assert h.ctx.ws.send_json.await_args[0][0]["type"] == "reference_hint"
        assert "STAR" in h.ctx.ws.send_json.await_args[0][0]["content"] or "超时" in h.ctx.ws.send_json.await_args[0][0]["content"]

        # generic error path
        h.ctx.ws.send_json.reset_mock()
        _seed_outline(h)
        h._generate_reference_hint = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
        await h._on_request_hint({"question": "报错问题?"})
        assert h.ctx.ws.send_json.await_args[0][0]["type"] == "reference_hint"

        # empty hint degrades to error_fb (still terminal)
        h.ctx.ws.send_json.reset_mock()
        _seed_outline(h)
        h._generate_reference_hint = AsyncMock(return_value="   ")  # type: ignore[method-assign]
        await h._on_request_hint({"question": "空回答?"})
        assert h.ctx.ws.send_json.await_args[0][0]["type"] == "reference_hint"
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_on_request_hint_full_mode_degrade_and_success():
    h = _make_handler()
    try:
        _seed_outline(h)
        h.ctx.reference_detail = "full"
        # full returns empty -> degrade to outline
        h._generate_full_reference_hint = AsyncMock(return_value="")  # type: ignore[method-assign]
        h._generate_reference_hint = AsyncMock(return_value="outline fallback")  # type: ignore[method-assign]
        await h._on_request_hint({"question": "full degrade?"})
        assert h.ctx.ws.send_json.await_args[0][0]["type"] == "reference_hint"
        assert h.ctx.ws.send_json.await_args[0][0]["content"] == "outline fallback"
        # full returns content directly
        h.ctx.ws.send_json.reset_mock()
        _seed_outline(h)
        h.ctx.reference_detail = "full"
        h._generate_full_reference_hint = AsyncMock(return_value="full answer")  # type: ignore[method-assign]
        h._generate_reference_hint = AsyncMock(return_value="should not use")  # type: ignore[method-assign]
        await h._on_request_hint({"question": "full ok?"})
        assert h.ctx.ws.send_json.await_args[0][0]["content"] == "full answer"
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_hint_rate_limited_en_and_generate_outline_both_langs():
    h = _make_handler()
    try:
        h.ctx.agent = MagicMock()
        h.ctx.agent.plan = SimpleNamespace(source="agent", language="en")
        await h._hint_rate_limited({"question": "tell me?"})
        assert h.ctx.ws.send_json.await_args[0][0]["type"] == "reference_hint_error"
        assert "Too many" in h.ctx.ws.send_json.await_args[0][0]["message"]
        # outline en
        _seed_outline(h, lang="en")
        out = await h._generate_reference_hint("What did you do?")
        assert out == "hint body"
        h.ctx.llm.chat.assert_awaited_once()
        # outline zh
        _seed_outline(h, lang="zh")
        out2 = await h._generate_reference_hint("讲讲项目?")
        assert out2 == "hint body"
        # outline LLM failure -> fallback
        h.ctx.llm.chat = AsyncMock(side_effect=RuntimeError("no backend"))
        out3 = await h._generate_reference_hint("q?")
        assert out3.strip() != ""
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_generate_full_reference_hint_branches():
    h = _make_handler()
    try:
        _seed_outline(h)
        db = MagicMock()
        db.close = MagicMock()
        # session None -> None
        h._load_session = MagicMock(return_value=None)  # type: ignore[method-assign]
        with patch("realmock.domains.interview.realtime.control.hint.SessionLocal", return_value=db):
            assert await h._generate_full_reference_hint("q?") is None
        # success path
        sess = MagicMock()
        h._load_session = MagicMock(return_value=sess)  # type: ignore[method-assign]
        with (
            patch("realmock.domains.interview.realtime.control.hint.SessionLocal", return_value=db),
            patch(
                "realmock.domains.interview.realtime.control.hint.generate_full_reference_hint",
                new=AsyncMock(return_value="full!"),
            ),
        ):
            assert await h._generate_full_reference_hint("q?") == "full!"
        # db.close raises -> swallowed
        db2 = MagicMock()
        db2.close = MagicMock(side_effect=RuntimeError("close boom"))
        h._load_session = MagicMock(return_value=None)  # type: ignore[method-assign]
        with patch("realmock.domains.interview.realtime.control.hint.SessionLocal", return_value=db2):
            assert await h._generate_full_reference_hint("q?") is None
    finally:
        await h._cancel_bg_tasks()

