"""Chat agent tests for realmock.domains.prep.agents.chat.

Covers: polish_final, _drop_trailing_assistant, _inject_refs, _begin_turn, _force_compact_context, _final_answer_with_overflow_retry, content-state helpers, run_chat and run_chat_stream branches including inline ask-user handling
Conventions: No real LLM/network; LLM and context builders faked via monkeypatch; rate limits reset per test
"""
from __future__ import annotations
import asyncio
from types import SimpleNamespace
import pytest
from realmock.domains.prep.agents.turn_state import TurnState
from realmock.platform.capabilities.ai.context.options import CompactionOptions

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

class _FakeSession:
    messages = "[]"
    resume_id = None
    target_company = ""
    token_usage = 0
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0

class _FakeDB:
    def commit(self) -> None:
        pass

def _make_agent(monkeypatch=None, llm=None):
    from realmock.domains.prep.agents.agent import PrepAgent

    agent = PrepAgent(_FakeSession(), llm or SimpleNamespace(context_window=8000))  # type: ignore[arg-type]
    return agent

async def _collect(agen):
    return [i async for i in agen]

def test_polish_final_strips_and_recovers() -> None:
    from realmock.domains.prep.agents.chat import polish_final

    text, event = polish_final("hello <|im_start|> world")
    assert "<|im_start|>" not in text
    assert event is None
    body = 'intro <tool_call>{"name": "ask_user", "arguments": {"question": "Q?", "options": ["A","B"]}}</tool_call> tail'
    cleaned, ask = polish_final(body)
    assert "<tool_call>" not in cleaned
    assert ask is not None and ask["question"] == "Q?"

def test_drop_trailing_assistant() -> None:
    from realmock.domains.prep.agents.chat import _drop_trailing_assistant

    agent = SimpleNamespace(messages=[{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}])
    _drop_trailing_assistant(agent)  # type: ignore[arg-type]
    assert agent.messages == [{"role": "user", "content": "q"}]
    _drop_trailing_assistant(agent)
    assert agent.messages == [{"role": "user", "content": "q"}]
    agent2 = SimpleNamespace(messages=[{"role": "user", "content": "q"}])
    _drop_trailing_assistant(agent2)  # type: ignore[arg-type]
    assert len(agent2.messages) == 1
    agent3 = SimpleNamespace(messages=["not-a-dict"])
    _drop_trailing_assistant(agent3)  # type: ignore[arg-type]
    assert agent3.messages == ["not-a-dict"]

@pytest.mark.asyncio
async def test_inject_refs_empty_and_block(monkeypatch) -> None:
    import realmock.domains.prep.agents.chat as chat_mod

    agent = _make_agent()
    out = await chat_mod._inject_refs(agent, [{"role": "user", "content": "hi"}], _FakeDB(), None)  # type: ignore[arg-type]
    assert out == [{"role": "user", "content": "hi"}]
    out2 = await chat_mod._inject_refs(agent, [{"role": "user", "content": "hi"}], _FakeDB(), [])  # type: ignore[arg-type]
    assert len(out2) == 1

    monkeypatch.setattr(chat_mod, "format_linked_sessions", lambda db, ids, exclude_id=None: "")
    out3 = await chat_mod._inject_refs(agent, [{"role": "user", "content": "hi"}], _FakeDB(), [1])  # type: ignore[arg-type]
    assert len(out3) == 1

    monkeypatch.setattr(
        chat_mod, "format_linked_sessions", lambda db, ids, exclude_id=None: "[refs] block"
    )
    out4 = await chat_mod._inject_refs(agent, [{"role": "user", "content": "hi"}], _FakeDB(), [1, 2])  # type: ignore[arg-type]
    assert out4[-1] == {"role": "system", "content": "[refs] block"}

def test_begin_turn_resets_and_clears_quiz() -> None:
    import realmock.domains.prep.agents.chat as chat_mod

    agent = _make_agent()
    agent.memory.pending_quiz = "open:q?"
    policy = chat_mod._begin_turn(agent, CompactionOptions(intensity="light", directive="d", retain=2))
    assert agent.memory.pending_quiz == ""
    assert agent.last_turn_id
    assert policy.intensity == "light"

@pytest.mark.asyncio
async def test_force_compact_context(monkeypatch) -> None:
    import realmock.domains.prep.agents.chat as chat_mod

    agent = _make_agent()
    agent._turn_state.mid_turn_base = [{"role": "user", "content": "x"}]

    async def _fake_build(*args, **kwargs):
        assert kwargs.get("force") is True
        assert kwargs["options"].intensity == "aggressive"
        return [{"role": "system", "content": "compacted"}]

    monkeypatch.setattr(agent, "_build_context", _fake_build)
    monkeypatch.setattr(chat_mod, "format_linked_sessions", lambda db, ids, exclude_id=None: "")
    out = await chat_mod._force_compact_context(
        agent, CompactionOptions(), _FakeDB(), None  # type: ignore[arg-type]
    )
    assert out == [{"role": "system", "content": "compacted"}]
    assert agent._turn_state.mid_turn_base is None

@pytest.mark.asyncio
async def test_final_answer_overflow_retry(monkeypatch) -> None:
    import realmock.domains.prep.agents.chat as chat_mod

    calls = {"n": 0}

    class _LLM:
        async def chat(self, messages, temperature=0.7):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("context_length_exceeded: too long")
            return "recovered"

    agent = SimpleNamespace(session=SimpleNamespace(id=1), llm=_LLM(), _turn_state=TurnState())
    agent.usage_snapshot = lambda: None  # type: ignore[attr-defined]
    agent.note_round_usage = lambda before: None  # type: ignore[attr-defined]
    agent._build_context = None  # type: ignore[attr-defined]

    async def _fake_force(agent_, policy, db, ids):
        return [{"role": "system", "content": "compacted"}]

    monkeypatch.setattr(chat_mod, "_force_compact_context", _fake_force)
    out = await chat_mod._final_answer_with_overflow_retry(
        agent, [{"role": "user", "content": "hi"}], CompactionOptions(), _FakeDB(), None  # type: ignore[arg-type]
    )
    assert out == "recovered"

    class _BoomLLM:
        async def chat(self, messages, temperature=0.7):
            raise RuntimeError("boom-not-overflow")

    agent2 = SimpleNamespace(session=SimpleNamespace(id=1), llm=_BoomLLM(), _turn_state=TurnState())
    agent2.usage_snapshot = lambda: None  # type: ignore[attr-defined]
    agent2.note_round_usage = lambda before: None  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="boom-not-overflow"):
        await chat_mod._final_answer_with_overflow_retry(
            agent2, [], CompactionOptions(), _FakeDB(), None  # type: ignore[arg-type]
        )

def test_new_content_state_and_mid_turn_report() -> None:
    import realmock.domains.prep.agents.chat as chat_mod

    st = chat_mod._new_content_state()
    assert st["streamed"] is False
    assert callable(st["filter"].flush)

    agent = SimpleNamespace(_turn_state=SimpleNamespace(mid_turn_report=None), context_window=8000)
    assert chat_mod._take_mid_turn_report_event(agent) is None  # type: ignore[arg-type]
    agent._turn_state.mid_turn_report = {
        "before": 10, "after": 4, "prompt_tokens": 1, "completion_tokens": 2, "latency_ms": 3.0
    }
    evt = chat_mod._take_mid_turn_report_event(agent)  # type: ignore[arg-type]
    assert evt is not None and evt["type"] == "compaction"
    assert evt["before"] == 10
    assert agent._turn_state.mid_turn_report is None

@pytest.mark.asyncio
async def test_run_chat_asked_user_and_early_paths(monkeypatch) -> None:
    import realmock.domains.prep.agents.chat as chat_mod

    async def _prep(agent, user_text, db, **kwargs):
        return CompactionOptions(), "turn1", [{"role": "user", "content": user_text}], [], {}

    monkeypatch.setattr(chat_mod, "_prepare_turn", _prep)
    finalized = {}
    monkeypatch.setattr(
        chat_mod, "finalize", lambda *a, **k: finalized.update({"ok": True})
    )

    # asked_user branch returns pending text and surfaces the dialog payload
    agent = _make_agent()
    agent.pending_reply_text = lambda: "waiting-line"  # type: ignore[method-assign]

    async def _rounds_asked(working, db, asked_user=None):
        asked_user["on"] = True
        asked_user["event"] = {"question": "Which?", "options": ["A", "B"]}
        return working, None, [], [], ""

    monkeypatch.setattr(agent, "_run_tool_rounds", _rounds_asked)
    out = await chat_mod.run_chat(agent, "hi", _FakeDB())  # type: ignore[arg-type]
    assert out == "waiting-line"
    assert agent.last_ask_event == {"question": "Which?", "options": ["A", "B"]}

    # early branch polishes model tail text
    async def _rounds_early(working, db, asked_user=None):
        return working, "early answer <|im_end|>", [], [{"name": "x"}], "think"

    monkeypatch.setattr(agent, "_run_tool_rounds", _rounds_early)
    out2 = await chat_mod.run_chat(agent, "hi", _FakeDB())  # type: ignore[arg-type]
    assert "early answer" in out2
    assert agent.last_ask_event is None

    # an inline ask_user rescued from the body becomes the dialog payload;
    # surrounding prose stays as the reply body (mirrors the stream channel)
    async def _rounds_inline(working, db, asked_user=None):
        return working, (
            'some prose first '
            '<tool_call>{"name": "ask_user", "arguments": '
            '{"question": "Q?", "options": ["A", "B"]}}</tool_call>'
        ), [], [], ""

    monkeypatch.setattr(agent, "_run_tool_rounds", _rounds_inline)
    out2b = await chat_mod.run_chat(agent, "hi", _FakeDB())  # type: ignore[arg-type]
    assert out2b == "some prose first"
    assert agent.last_ask_event is not None
    assert agent.last_ask_event["question"] == "Q?"

    # a dialog rescued from an otherwise-empty body keeps the waiting line
    async def _rounds_inline_bare(working, db, asked_user=None):
        return working, (
            '<tool_call>{"name": "ask_user", "arguments": '
            '{"question": "Q?", "options": ["A", "B"]}}</tool_call>'
        ), [], [], ""

    monkeypatch.setattr(agent, "_run_tool_rounds", _rounds_inline_bare)
    out2c = await chat_mod.run_chat(agent, "hi", _FakeDB())  # type: ignore[arg-type]
    assert out2c == "waiting-line"
    assert agent.last_ask_event is not None

    # early empty (no dialog) falls through to the closing answer, never the
    # waiting line — that copy would be misleading without a dialog
    async def _rounds_empty(working, db, asked_user=None):
        return working, "<|im_start|>", [], [], ""

    async def _fake_closing(agent_, working, policy, db, ids):
        return "closing answer"

    monkeypatch.setattr(agent, "_run_tool_rounds", _rounds_empty)
    monkeypatch.setattr(chat_mod, "_final_answer_with_overflow_retry", _fake_closing)
    out3 = await chat_mod.run_chat(agent, "hi", _FakeDB())  # type: ignore[arg-type]
    assert out3 == "closing answer"
    assert agent.last_ask_event is None

    # non-string final coerced to empty
    async def _rounds_none(working, db, asked_user=None):
        return working, None, [], [], ""

    async def _fake_final(agent_, working, policy, db, ids):
        return None  # type: ignore[return-value]

    monkeypatch.setattr(agent, "_run_tool_rounds", _rounds_none)
    monkeypatch.setattr(chat_mod, "_final_answer_with_overflow_retry", _fake_final)
    out4 = await chat_mod.run_chat(agent, "hi", _FakeDB())  # type: ignore[arg-type]
    assert out4 == ""

@pytest.mark.asyncio
async def test_run_chat_stream_start_event_unexpected_tail_mid_and_asked(monkeypatch) -> None:
    import realmock.domains.prep.agents.chat as chat_mod

    async def _prep(agent, user_text, db, **kwargs):
        return CompactionOptions(), "turn9", [{"role": "user", "content": "hi"}], [{"role": "user", "content": "hi"}], {}

    monkeypatch.setattr(chat_mod, "_prepare_turn", _prep)
    monkeypatch.setattr(
        chat_mod, "compaction_event", lambda *a, **k: {"type": "compaction", "before": 9, "after": 3}
    )

    agent = _make_agent()
    agent.pending_reply_text = lambda: "wait-line"  # type: ignore[method-assign]

    async def _fake_rounds(runner, outcome, events, working, db, asked_user=None, content_state=None):
        outcome["value"] = ("unexpected-shape",)
        if False:
            yield "x"

    monkeypatch.setattr(chat_mod, "stream_tool_rounds", _fake_rounds)
    # unexpected shape logs warning then falls to closing stream
    agent.llm = SimpleNamespace(
        chat_stream=lambda *a, **k: _agen(["closing"]),
        context_window=8000,
    )

    async def _agen(items):
        for i in items:
            yield i

    async def _slice(text):
        yield text

    monkeypatch.setattr(chat_mod, "slice_stream", _slice)
    monkeypatch.setattr(chat_mod, "finalize_with_delta", lambda *a, **k: None)

    items = [i async for i in chat_mod.run_chat_stream(agent, "hi", _FakeDB())]  # type: ignore[arg-type]
    types = [i.get("type") for i in items if isinstance(i, dict)]
    assert "compaction" in types
    assert "status" in types
    assert "closing" in "".join(i for i in items if isinstance(i, str))

    # tail flush + mid-turn report + asked_user with delta
    async def _prep2(agent, user_text, db, **kwargs):
        return CompactionOptions(), "t2", [{"role": "user", "content": "hi"}], [], {}

    monkeypatch.setattr(chat_mod, "_prepare_turn", _prep2)
    monkeypatch.setattr(chat_mod, "compaction_event", lambda *a, **k: None)
    agent._turn_state.mid_turn_report = {"before": 5, "after": 2}

    async def _fake_rounds2(runner, outcome, events, working, db, asked_user=None, content_state=None):
        asked_user["on"] = True
        content_state["filter"] = SimpleNamespace(flush=lambda: "tail-tok")
        outcome["value"] = ([], None, [], [], "")
        if False:
            yield "x"

    monkeypatch.setattr(chat_mod, "stream_tool_rounds", _fake_rounds2)
    monkeypatch.setattr(chat_mod, "finalize_with_delta", lambda *a, **k: {"type": "usage", "prompt_tokens": 1})
    items2 = [i async for i in chat_mod.run_chat_stream(agent, "hi", _FakeDB())]  # type: ignore[arg-type]
    assert "tail-tok" in items2
    assert any(isinstance(i, dict) and i.get("type") == "compaction" for i in items2)
    assert any(isinstance(i, dict) and i.get("type") == "usage" for i in items2)

@pytest.mark.asyncio
async def test_run_chat_stream_error_and_overflow_and_cancel(monkeypatch) -> None:
    import realmock.domains.prep.agents.chat as chat_mod

    async def _prep(agent, user_text, db, **kwargs):
        return CompactionOptions(), "t3", [{"role": "user", "content": "hi"}], [], {}

    monkeypatch.setattr(chat_mod, "_prepare_turn", _prep)
    monkeypatch.setattr(chat_mod, "compaction_event", lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, "slice_stream", lambda text: _agen([text]))

    async def _agen(items):
        for i in items:
            yield i

    # error propagation branch
    agent = _make_agent()

    async def _boom_rounds(runner, outcome, events, working, db, asked_user=None, content_state=None):
        outcome["error"] = RuntimeError("loop-boom")
        if False:
            yield "x"

    monkeypatch.setattr(chat_mod, "stream_tool_rounds", _boom_rounds)
    with pytest.raises(RuntimeError, match="loop-boom"):
        async for _ in chat_mod.run_chat_stream(agent, "hi", _FakeDB()):  # type: ignore[arg-type]
            pass

    # search_groups branch + streamed-finish + overflow retry in closing stream
    async def _ok_rounds(runner, outcome, events, working, db, asked_user=None, content_state=None):
        outcome["value"] = ([{"role": "user", "content": "hi"}], None, [{"query": "q"}], [], "")
        if False:
            yield "x"

    monkeypatch.setattr(chat_mod, "stream_tool_rounds", _ok_rounds)

    calls = {"n": 0}

    async def _closing_stream(messages, temperature=0.7):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("context_length_exceeded now")
        yield "after-compact"

    agent.llm = SimpleNamespace(chat_stream=_closing_stream, context_window=8000)

    async def _fake_force(agent_, policy, db, ids):
        return [{"role": "system", "content": "c"}]

    monkeypatch.setattr(chat_mod, "_force_compact_context", _fake_force)
    monkeypatch.setattr(chat_mod, "finalize_with_delta", lambda *a, **k: None)
    items = [i async for i in chat_mod.run_chat_stream(agent, "hi", _FakeDB())]  # type: ignore[arg-type]
    assert any(isinstance(i, dict) and i.get("type") == "search_results" for i in items)
    assert "after-compact" in "".join(i for i in items if isinstance(i, str))

    # streamed content finishes without regeneration (polish path)
    async def _streamed_rounds(runner, outcome, events, working, db, asked_user=None, content_state=None):
        content_state["streamed"] = True
        content_state["filtered_text"] = "already heard"
        outcome["value"] = ([], None, [], [], "")
        if False:
            yield "x"

    monkeypatch.setattr(chat_mod, "stream_tool_rounds", _streamed_rounds)
    agent.llm = SimpleNamespace(
        chat_stream=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not regenerate")),
        context_window=8000,
    )
    items2 = [i async for i in chat_mod.run_chat_stream(agent, "hi", _FakeDB())]  # type: ignore[arg-type]
    assert agent is not None
    assert isinstance(items2, list)

@pytest.mark.asyncio
async def test_run_chat_stream_cancel_persists(monkeypatch) -> None:
    import asyncio

    import realmock.domains.prep.agents.chat as chat_mod

    async def _prep(agent, user_text, db, **kwargs):
        return CompactionOptions(), "tc", [{"role": "user", "content": "hi"}], [], {}

    monkeypatch.setattr(chat_mod, "_prepare_turn", _prep)
    monkeypatch.setattr(chat_mod, "compaction_event", lambda *a, **k: None)

    async def _cancel_rounds(runner, outcome, events, working, db, asked_user=None, content_state=None):
        raise asyncio.CancelledError()
        if False:
            yield "x"

    monkeypatch.setattr(chat_mod, "stream_tool_rounds", _cancel_rounds)
    persisted = {}
    monkeypatch.setattr(chat_mod, "persist_cancel", lambda *a, **k: persisted.update({"ok": True}))
    agent = _make_agent()
    with pytest.raises(asyncio.CancelledError):
        async for _ in chat_mod.run_chat_stream(agent, "hi", _FakeDB()):  # type: ignore[arg-type]
            pass
    assert persisted.get("ok") is True

def test_run_chat_stream_inline_ask_empty_body_uses_waiting(monkeypatch) -> None:
    import realmock.domains.prep.agents.chat as chat_mod

    async def _prep(agent, user_text, db, **kwargs):
        return CompactionOptions(), "ti", [{"role": "user", "content": "hi"}], [], {}

    monkeypatch.setattr(chat_mod, "_prepare_turn", _prep)
    monkeypatch.setattr(chat_mod, "compaction_event", lambda *a, **k: None)

    async def _rounds(runner, outcome, events, working, db, asked_user=None, content_state=None):
        outcome["value"] = (
            working,
            '<tool_call>{"name":"ask_user","arguments":{"question":"Q?","options":["A","B"]}}</tool_call>',
            [],
            [],
            "",
        )
        if False:
            yield "x"

    monkeypatch.setattr(chat_mod, "stream_tool_rounds", _rounds)
    monkeypatch.setattr(chat_mod, "slice_stream", lambda text: _agen([text]))

    async def _agen(items):
        for i in items:
            yield i

    def _polish(text):
        return "", {"question": "Q?", "options": ["A", "B"]}

    monkeypatch.setattr(chat_mod, "polish_final", _polish)
    agent = _make_agent()
    agent.pending_reply_text = lambda: "wait-line"  # type: ignore[method-assign]
    monkeypatch.setattr(chat_mod, "finalize_with_delta", lambda *a, **k: None)
    items = asyncio.run(_collect(chat_mod.run_chat_stream(agent, "hi", _FakeDB())))  # type: ignore[arg-type]
    assert any(isinstance(i, dict) and i.get("type") == "ask_user" for i in items)
    assert "wait-line" in "".join(i for i in items if isinstance(i, str))


@pytest.mark.asyncio
async def test_run_chat_persists_question_when_turn_fails(monkeypatch) -> None:
    """A turn that dies before finalize still persists the typed question."""
    import realmock.domains.prep.agents.chat as chat_mod
    from realmock.platform.core.errors import ApiBusinessError, CATALOG

    async def _prep(agent, user_text, db, **kwargs):
        agent.messages.append({"role": "user", "content": user_text})
        return CompactionOptions(), "turn1", [{"role": "user", "content": user_text}], [], {}

    monkeypatch.setattr(chat_mod, "_prepare_turn", _prep)

    agent = _make_agent()

    async def _boom(working, db, asked_user=None):
        raise ApiBusinessError(CATALOG["A3001"], message="quota gone")

    monkeypatch.setattr(agent, "_run_tool_rounds", _boom)
    saved: dict = {}
    monkeypatch.setattr(
        agent, "_save", lambda db: saved.setdefault("last", list(agent.messages))
    )

    with pytest.raises(ApiBusinessError):
        await chat_mod.run_chat(agent, "my typed question", _FakeDB())  # type: ignore[arg-type]
    assert agent.messages[-1]["content"] == "my typed question"
    assert saved["last"][-1]["content"] == "my typed question"


@pytest.mark.asyncio
async def test_run_chat_stream_error_persists_question(monkeypatch) -> None:
    """Stream-channel failures persist the question before the error surfaces."""
    import realmock.domains.prep.agents.chat as chat_mod

    async def _prep(agent, user_text, db, **kwargs):
        agent.messages.append({"role": "user", "content": user_text})
        return CompactionOptions(), "turn1", [{"role": "user", "content": user_text}], [], {}

    monkeypatch.setattr(chat_mod, "_prepare_turn", _prep)

    async def _boom_run(*args, **kwargs):
        raise RuntimeError("stream exploded")
        yield  # pragma: no cover

    monkeypatch.setattr(chat_mod, "stream_tool_rounds", _boom_run)

    agent = _make_agent()
    saved: dict = {}
    monkeypatch.setattr(
        agent, "_save", lambda db: saved.setdefault("last", list(agent.messages))
    )

    with pytest.raises(RuntimeError):
        async for _ in chat_mod.run_chat_stream(agent, "typed question", _FakeDB()):  # type: ignore[arg-type]
            pass
    assert saved["last"][-1]["content"] == "typed question"
