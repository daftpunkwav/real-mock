"""Prep agent tests for realmock.domains.prep.agents.agent.

Covers: message loading, _ensure_system fallback, waiting-line alias, named-tool dispatch, tool-round timeout/error paths and tool definitions
Conventions: No real LLM/network; agent loop faked; rate limits reset per test
"""
from __future__ import annotations
import asyncio
import json
from types import SimpleNamespace
import pytest
from realmock.domains.prep.agents.agent import PrepAgent

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
    target_role = ""
    token_usage = 0
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0

class _FakeDB:
    def commit(self) -> None:
        pass

def _agent(messages: str = "[]", llm=None) -> PrepAgent:
    sess = _FakeSession()
    sess.messages = messages
    fake_llm = llm or SimpleNamespace(context_window=8000)
    return PrepAgent(sess, fake_llm)  # type: ignore[arg-type]

def test_load_messages_non_list_resets() -> None:
    agent = _agent(messages='{"a": 1}')
    assert agent.messages == []

def test_load_messages_type_error_resets() -> None:
    sess = _FakeSession()
    sess.messages = None  # type: ignore[assignment]
    agent = PrepAgent(sess, SimpleNamespace(context_window=8000))  # type: ignore[arg-type]
    assert agent.messages == []

@pytest.mark.asyncio
async def test_ensure_system_degraded_falls_back(monkeypatch) -> None:
    import realmock.domains.prep.agents.agent as agent_mod

    agent = _agent()
    assert agent.messages == []

    def _boom(*args, **kwargs):
        raise RuntimeError("seed-db-down")

    monkeypatch.setattr(agent_mod, "build_system_messages", _boom)
    logged: list[dict] = []
    monkeypatch.setattr(agent_mod, "log_agent_error", lambda **kw: logged.append(kw))
    await agent._ensure_system(_FakeDB())  # type: ignore[arg-type]
    assert len(agent.messages) == 1
    assert agent.messages[0]["role"] == "system"
    assert logged and logged[0]["kind"] == "seed_degraded"

def test_waiting_line_alias_matches_pending() -> None:
    agent = _agent()
    agent.reply_locale = "en"
    assert agent.waiting_line() == agent.pending_reply_text()
    assert agent.waiting_line() != ""

@pytest.mark.asyncio
async def test_run_named_tool_compact_context_delegates(monkeypatch) -> None:
    agent = _agent()

    async def _fake_compact(args, db):
        return ("compacted-text", [{"title": "t"}])

    monkeypatch.setattr(agent, "_compact_current_round", _fake_compact)
    text, hits = await agent._run_named_tool("compact_context", {}, _FakeDB())  # type: ignore[arg-type]
    assert text == "compacted-text"
    assert hits == [{"title": "t"}]

@pytest.mark.asyncio
async def test_run_named_tool_search_invalid_json_select(monkeypatch) -> None:
    import realmock.domains.prep.agents.agent as agent_mod

    agent = _agent()

    async def _fake_exec(name, args, memory, resume_id=None):
        return ("not-json{{{", [])

    monkeypatch.setattr(agent_mod, "execute_prep_tool", _fake_exec)
    text, hits = await agent._run_named_tool(
        "search_tools", {"query": "repo"}, _FakeDB()  # type: ignore[arg-type]
    )
    assert text == "not-json{{{"
    assert hits == []
    assert agent._turn_state.expanded is True

@pytest.mark.asyncio
async def test_run_tool_rounds_compact_observation_timeout_paths(monkeypatch) -> None:
    import realmock.domains.prep.agents.agent as agent_mod

    async def _timeout_blob(llm, text, purpose=None):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(agent_mod, "compress_text_blob", _timeout_blob)

    captured: dict = {}

    async def _fake_loop(llm, working, **kwargs):
        compact = kwargs.get("compact_observation")
        assert compact is not None
        short = await compact("hello")
        assert short == "hello"
        long_text = "x" * 5000
        clipped = await compact(long_text)
        assert "COMPRESSION_TIMEOUT" in clipped
        assert len(clipped) < len(long_text)
        captured["ok"] = True
        return SimpleNamespace(messages=working, final_content="done", thinking="t")

    monkeypatch.setattr(agent_mod, "run_agent_loop", _fake_loop)
    agent = _agent()
    working = [{"role": "user", "content": "hi"}]
    out = await agent._run_tool_rounds(working, _FakeDB())  # type: ignore[arg-type]
    assert captured.get("ok") is True
    assert out[1] == "done"

@pytest.mark.asyncio
async def test_run_tool_rounds_business_error_propagates(monkeypatch) -> None:
    import realmock.domains.prep.agents.agent as agent_mod
    from realmock.platform.core.errors import CATALOG, ApiBusinessError

    async def _boom(*args, **kwargs):
        raise ApiBusinessError(CATALOG["A3001"], message="gone")

    monkeypatch.setattr(agent_mod, "run_agent_loop", _boom)
    agent = _agent()
    with pytest.raises(ApiBusinessError):
        await agent._run_tool_rounds([{"role": "user", "content": "hi"}], _FakeDB())  # type: ignore[arg-type]

@pytest.mark.asyncio
async def test_run_tool_rounds_turn_timeout_returns_working(monkeypatch) -> None:
    import realmock.domains.prep.agents.agent as agent_mod

    async def _hang(*args, **kwargs):
        await asyncio.sleep(30)
        return SimpleNamespace(messages=[], final_content=None, thinking="")

    monkeypatch.setattr(agent_mod, "run_agent_loop", _hang)
    monkeypatch.setattr(agent_mod, "_TURN_TIMEOUT_SECONDS", 0.05)
    logged: list[dict] = []
    monkeypatch.setattr(agent_mod, "log_agent_error", lambda **kw: logged.append(kw))
    agent = _agent()
    working = [{"role": "user", "content": "hi"}]
    messages, early, groups, steps, thinking = await agent._run_tool_rounds(
        working, _FakeDB()  # type: ignore[arg-type]
    )
    assert messages == working
    assert early is None
    assert thinking == ""
    assert logged and logged[0]["kind"] == "turn_timeout"

@pytest.mark.asyncio
async def test_run_tool_rounds_generic_error_returns_working(monkeypatch) -> None:
    import realmock.domains.prep.agents.agent as agent_mod

    async def _boom(*args, **kwargs):
        raise RuntimeError("loop exploded")

    monkeypatch.setattr(agent_mod, "run_agent_loop", _boom)
    agent = _agent()
    working = [{"role": "user", "content": "hi"}]
    messages, early, groups, steps, thinking = await agent._run_tool_rounds(
        working, _FakeDB()  # type: ignore[arg-type]
    )
    assert messages == working
    assert early is None
    assert thinking == ""

def test_tool_definitions_empty_user_text() -> None:
    agent = _agent()
    defs = agent._tool_definitions("")
    names = {str((d.get("function") or {}).get("name") or "") for d in defs}
    assert "compact_context" in names
    assert json.dumps(defs, ensure_ascii=False) != ""


@pytest.mark.asyncio
async def test_run_tool_rounds_final_round_is_tool_free(monkeypatch) -> None:
    """The round cap ends with a tool-free request and a matching hint."""
    import realmock.domains.prep.agents.agent as agent_mod

    captured: dict = {}

    async def _fake_loop(llm, working, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(messages=working, final_content="done", thinking="t")

    monkeypatch.setattr(agent_mod, "run_agent_loop", _fake_loop)
    agent = _agent()
    await agent._run_tool_rounds([{"role": "user", "content": "hi"}], _FakeDB())  # type: ignore[arg-type]
    assert captured.get("final_round_tool_free") is True
    hint = captured.get("wrap_up_hint") or {}
    assert "tools are unavailable" in hint.get("content", ""), (
        "the closing hint must not offer a tool call the model cannot make"
    )
