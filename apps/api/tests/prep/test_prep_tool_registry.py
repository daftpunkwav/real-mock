"""Prep tool registry and agent-state unit tests (no network, no LLM).

Covers ``realmock.domains.prep.agents.tools`` dispatch branches, the
``tool_exec`` failure paths, ``PrepAgent`` corrupt-message recovery, and the
create/history HTTP behavior that the stream tests do not exercise.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.prep.agents import tools as prep_tools
from realmock.domains.prep.agents.tools.basic import company_info as company_info_tool
from realmock.domains.prep.agents.tools.basic import web_search as web_search_tool
from realmock.domains.prep.agents.agent import PrepAgent
from realmock.domains.prep.agents.tool_exec import build_execute_callback
from realmock.domains.prep.models import PrepSession
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.core.session_auth import new_access_token

_LOCAL_TOOL_NAMES = frozenset({"web_search", "company_info", "quiz", "take_note"})
_GITHUB_TOOL_NAMES = frozenset({
    "github_list_repos",
    "github_get_readme",
    "github_get_repo",
    "github_list_commits",
    "github_get_user",
    "github_get_file",
})
_PROFILE_RESUME_NAMES = frozenset({
    "profile_list_sections",
    "profile_get_section",
    "resume_overview",
    "resume_get_section",
})
_MEMORY_TOOL_NAMES = frozenset({
    "memory_list_tags",
    "memory_list_summaries",
    "memory_get_detail",
    "memory_write",
})


def _memory() -> WorkingMemory:
    return WorkingMemory()


def _agent(messages: str = "[]") -> PrepAgent:
    session = PrepSession(
        access_token="test-token",
        status="active",
        messages=messages,
        target_company="",
    )
    return PrepAgent(session, SimpleNamespace(context_window=8000))


# --- Registry shape ---


def test_registry_contains_local_and_github_tools() -> None:
    assert _LOCAL_TOOL_NAMES <= set(prep_tools.TOOL_REGISTRY)
    assert _GITHUB_TOOL_NAMES <= set(prep_tools.TOOL_REGISTRY)
    assert _MEMORY_TOOL_NAMES <= set(prep_tools.TOOL_REGISTRY)
    # Profile/resume tools are appended to the model-facing definitions only,
    # they are not part of the local dispatch registry.
    assert not (_PROFILE_RESUME_NAMES & set(prep_tools.TOOL_REGISTRY))


def test_tool_definitions_are_valid_openai_schema() -> None:
    defs = prep_tools.PREP_TOOL_DEFINITIONS
    names = [d["function"]["name"] for d in defs]
    assert len(names) == len(set(names)), "tool definition names must be unique"
    for d in defs:
        assert d["type"] == "function"
        fn = d["function"]
        assert fn["name"] and fn["description"]
        assert fn["parameters"].get("type") == "object"
    assert _LOCAL_TOOL_NAMES | _GITHUB_TOOL_NAMES | _PROFILE_RESUME_NAMES <= set(names)


# --- execute_prep_tool dispatch ---


async def test_unknown_tool_returns_observation() -> None:
    text, hits = await prep_tools.execute_prep_tool("nope", {}, _memory())
    assert text == "Unknown tool: nope"
    assert hits == []


async def test_non_dict_args_are_parsed() -> None:
    memory = _memory()
    text, hits = await prep_tools.execute_prep_tool(
        "quiz", '{"question": "Q?", "type": "open"}', memory
    )
    assert "Q?" in text
    assert hits == []
    assert memory.pending_quiz == "open:Q?"


async def test_quiz_records_pending_question() -> None:
    memory = _memory()
    text, hits = await prep_tools.execute_prep_tool(
        "quiz", {"question": "Explain Raft.", "type": "choice"}, memory
    )
    assert "Explain Raft." in text and "(choice)" in text
    assert hits == []
    assert memory.pending_quiz == "choice:Explain Raft."


async def test_take_note_missing_content_records_nothing() -> None:
    memory = _memory()
    text, hits = await prep_tools.execute_prep_tool(
        "take_note", {"kind": "note", "content": "   "}, memory
    )
    assert text == "take_note missing content; nothing recorded."
    assert hits == []
    assert memory.notes == []


async def test_take_note_routes_weak_points() -> None:
    memory = _memory()
    text, _ = await prep_tools.execute_prep_tool(
        "take_note", {"kind": "weak_point", "content": " forgetting indexes "}, memory
    )
    assert "weak_point" in text
    assert "forgetting indexes" in memory.weak_points
    text, _ = await prep_tools.execute_prep_tool(
        "take_note", {"kind": "note", "content": "target: backend"}, memory
    )
    assert "target: backend" in memory.notes


async def test_web_search_empty_query_skips_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(args: dict, **kwargs) -> str:
        assert args["query"] == ""
        return json.dumps({"results": [], "text": "nothing"})

    monkeypatch.setattr(web_search_tool, "execute_web_search", fake_search)
    memory = _memory()
    text, hits = await prep_tools.execute_prep_tool("web_search", {"query": ""}, memory)
    assert (text, hits) == ("nothing", [])
    assert memory.notes == []


async def test_web_search_remembers_query(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search(args: dict, **kwargs) -> str:
        return json.dumps({"results": [{"title": "t"}], "text": "body"})

    monkeypatch.setattr(web_search_tool, "execute_web_search", fake_search)
    memory = _memory()
    text, hits = await prep_tools.execute_prep_tool(
        "web_search", {"query": "raft consensus"}, memory
    )
    assert text == "body"
    assert hits == [{"title": "t"}]
    assert "search:raft consensus" in memory.notes


async def test_web_search_non_json_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(args: dict, **kwargs) -> str:
        return "RAW-UPSTREAM"

    monkeypatch.setattr(web_search_tool, "execute_web_search", fake_search)
    text, hits = await prep_tools.execute_prep_tool(
        "web_search", {"query": "x"}, _memory()
    )
    assert (text, hits) == ("RAW-UPSTREAM", [])


async def test_web_search_non_list_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search(args: dict, **kwargs) -> str:
        return json.dumps({"results": "nope", "text": "T"})

    monkeypatch.setattr(web_search_tool, "execute_web_search", fake_search)
    text, hits = await prep_tools.execute_prep_tool(
        "web_search", {"query": "x"}, _memory()
    )
    assert (text, hits) == ("T", [])


async def test_company_info_returns_catalog_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        company_info_tool, "get_company_context", lambda company: f"CTX:{company}"
    )
    text, hits = await prep_tools.execute_prep_tool(
        "company_info", {"company": "bytedance"}, _memory()
    )
    assert (text, hits) == ("CTX:bytedance", [])


# --- tool_exec failure paths ---


def _callback(run_named_tool, **kwargs):
    return build_execute_callback(
        run_named_tool=run_named_tool,
        memory=kwargs.get("memory", _memory()),
        db=kwargs.get("db"),
        search_groups=kwargs.get("search_groups", []),
        events=kwargs.get("events"),
        asked_user=kwargs.get("asked_user"),
        error_context=kwargs.get("error_context"),
    )


async def test_execute_timeout_reports_search_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow(name, args, db):
        await asyncio.sleep(5)
        return "late", []

    import realmock.domains.prep.agents.tool_exec as tool_exec

    monkeypatch.setattr(tool_exec, "_TOOL_TIMEOUT_SEC", 0.05)
    execute = _callback(slow)
    out = await execute("web_search", {"query": "slow q"})
    assert "SEARCH_UNAVAILABLE" in out
    assert "Do not invent results" in out


async def test_execute_search_failure_appends_constraint_and_allows_retry() -> None:
    calls = 0

    async def flaky(name, args, db):
        nonlocal calls
        calls += 1
        return "SEARCH_UNAVAILABLE\nbackend down", []

    execute = _callback(flaky)
    first = await execute("web_search", {"query": "q"})
    assert "[System constraint] Retrieval failed." in first
    # Failed calls are not cached: the same args run again instead of deduping.
    second = await execute("web_search", {"query": "q"})
    assert "Duplicate call skipped" not in second
    assert calls == 2


async def test_execute_circuit_opens_after_three_consecutive_failures() -> None:
    calls = 0

    async def always_down(name, args, db):
        nonlocal calls
        calls += 1
        return "SEARCH_UNAVAILABLE\nbackend down", []

    execute = _callback(always_down)
    for i in range(3):
        out = await execute("web_search", {"query": f"q{i}"})
        assert "circuit_open" not in out
    assert calls == 3
    # Fourth call is refused without spending another tool call.
    blocked = await execute("web_search", {"query": "q3"})
    assert "circuit_open" in blocked
    assert calls == 3


async def test_execute_success_resets_error_streak() -> None:
    calls = 0

    async def flaky_then_ok(name, args, db):
        nonlocal calls
        calls += 1
        if calls <= 2:
            return "SEARCH_UNAVAILABLE\nbackend down", []
        return "ok result", []

    execute = _callback(flaky_then_ok)
    await execute("web_search", {"query": "q0"})
    await execute("web_search", {"query": "q1"})
    assert "ok result" in await execute("web_search", {"query": "q2"})
    # Streak was reset by the success: three more failures needed to trip.
    await execute("web_search", {"query": "q3"})
    await execute("web_search", {"query": "q4"})
    out = await execute("web_search", {"query": "q5"})
    assert "circuit_open" not in out
    assert calls == 6


async def test_execute_unexpected_exception_returns_json_and_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[dict] = []

    async def boom(name, args, db):
        raise RuntimeError("disk exploded")

    import realmock.domains.prep.agents.tool_exec as tool_exec

    monkeypatch.setattr(
        tool_exec, "log_agent_error",
        lambda **kw: records.append(kw),
    )
    execute = _callback(boom, error_context={"domain": "prep", "session": "7"})
    out = await execute("company_info", {"company": "x"})
    payload = json.loads(out.split("\n", 1)[1])
    assert payload["error"] == "tool_failed"
    assert payload["tool"] == "company_info"
    assert records and records[0]["domain"] == "prep"
    assert records[0]["session"] == "7"
    assert records[0]["kind"] == "tool_failed"


async def test_execute_timeout_is_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[dict] = []

    async def slow(name, args, db):
        await asyncio.sleep(5)
        return "late", []

    import realmock.domains.prep.agents.tool_exec as tool_exec

    monkeypatch.setattr(tool_exec, "_TOOL_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(
        tool_exec, "log_agent_error",
        lambda **kw: records.append(kw),
    )
    execute = _callback(slow, error_context={"domain": "prep", "session": "9"})
    out = await execute("web_search", {"query": "slow q"})
    assert "SEARCH_UNAVAILABLE" in out
    assert records and records[0]["kind"] == "timeout"
    assert records[0]["tool"] == "web_search"


def test_tool_round_policy_constants() -> None:
    import realmock.domains.prep.agents.agent as prep_agent
    import realmock.domains.prep.agents.tool_exec as tool_exec

    # Per-turn budget 12 rounds x 3 tools; breaker trips on 3 straight failures.
    assert prep_agent._MAX_TOOL_ROUNDS == 12
    assert prep_agent._MAX_TOOLS_PER_ROUND == 3
    assert tool_exec._TOOL_CIRCUIT_BREAKER_STREAK == 3


# --- ask_user dialog shapes ---


def test_ask_event_defaults_to_single_options_with_custom() -> None:
    from realmock.domains.prep.agents.ask_user import _build_ask_event

    event = _build_ask_event("Next?", ["a", "b"])
    assert event == {
        "question": "Next?",
        "options": ["a", "b"],
        "selection": "single",
        "widget": "options",
        "scale": {},
        "allow_custom": True,
        "suggested": "a",
    }


def test_ask_options_capped_at_eight() -> None:
    from realmock.domains.prep.agents.ask_user import normalize_ask_options

    assert len(normalize_ask_options([f"o{i}" for i in range(10)])) == 8
    assert normalize_ask_options(["a", "b", "a", " a "]) == ["a", "b"]


def test_ask_slider_scale_validation() -> None:
    from realmock.domains.prep.agents.ask_user import normalize_ask_scale

    assert normalize_ask_scale("slider", {"min": 0, "max": 10, "unit": "h"}) == {
        "min": 0.0, "max": 10.0, "step": 1.0, "unit": "h",
    }
    assert normalize_ask_scale("slider", {"min": 5, "max": 5}) is None
    assert normalize_ask_scale("slider", None) is None
    assert normalize_ask_scale("slider", {"min": True, "max": 10}) is None
    assert normalize_ask_scale("slider", {"min": 0, "max": float("inf")}) is None
    assert normalize_ask_scale("rating", {}) == {"max": 5}
    assert normalize_ask_scale("rating", {"max": 99}) == {"max": 10}
    assert normalize_ask_scale("rating", {"max": 1}) == {"max": 3}


def test_ask_allow_custom_only_explicit_negatives_off() -> None:
    from realmock.domains.prep.agents.ask_user import normalize_ask_allow_custom

    assert normalize_ask_allow_custom(True) is True
    assert normalize_ask_allow_custom(None) is True
    assert normalize_ask_allow_custom(False) is False
    assert normalize_ask_allow_custom(0) is False
    assert normalize_ask_allow_custom("false") is False
    assert normalize_ask_allow_custom("No") is False


def test_ask_invalid_scale_degrades_to_options() -> None:
    from realmock.domains.prep.agents.ask_user import _build_ask_event

    event = _build_ask_event("Q?", ["a", "b"], widget="slider", scale={"min": 1})
    assert event is not None and event["widget"] == "options"
    assert _build_ask_event("Q?", ["only"], widget="slider", scale=None) is None
    assert _build_ask_event("Q?", [], widget="options") is None


async def test_ask_dispatch_emits_full_event() -> None:
    from realmock.platform.capabilities.ai.agent.loop import AgentHalt

    events: asyncio.Queue = asyncio.Queue()
    asked_user: dict[str, bool] = {"on": False}
    execute = _callback(
        lambda name, args, db: (_ for _ in ()).throw(AssertionError("must not run")),
        events=events, asked_user=asked_user,
    )
    try:
        await execute("ask_user", {
            "question": "Which areas?",
            "options": ["a", "b", "c"],
            "selection": "multi",
            "widget": "options",
            "allow_custom": False,
        })
    except AgentHalt:
        pass
    assert asked_user["on"] is True
    event = await events.get()
    assert event["type"] == "ask_user"
    assert event["selection"] == "multi"
    assert event["allow_custom"] is False


async def test_ask_dispatch_slider_without_options() -> None:
    from realmock.platform.capabilities.ai.agent.loop import AgentHalt

    events: asyncio.Queue = asyncio.Queue()
    execute = _callback(
        lambda name, args, db: (_ for _ in ()).throw(AssertionError("must not run")),
        events=events,
    )
    try:
        await execute("ask_user", {
            "question": "Hours per week?",
            "options": [],
            "widget": "slider",
            "scale": {"min": 0, "max": 20, "unit": "h"},
        })
    except AgentHalt:
        pass
    event = await events.get()
    assert event["widget"] == "slider"
    assert event["scale"]["max"] == 20


async def test_ask_dispatch_incomplete_returns_observation() -> None:
    execute = _callback(lambda name, args, db: ("", []))
    out = await execute("ask_user", {"question": "", "options": []})
    assert "incomplete" in out


def test_ask_suggested_resolution() -> None:
    from realmock.domains.prep.agents.ask_user import _build_ask_event, fallback_reply

    assert fallback_reply("zh-CN") != fallback_reply("en")
    assert fallback_reply(None) == fallback_reply("en")
    event = _build_ask_event("Q?", ["a", "b", "c"], suggested_index=2)
    assert event is not None and event["suggested"] == "c"
    # Out-of-range indices clamp to the nearest bound; non-numeric falls back to first.
    assert _build_ask_event("Q?", ["a", "b"], suggested_index=9)["suggested"] == "b"
    assert _build_ask_event("Q?", ["a", "b"], suggested_index=-4)["suggested"] == "a"
    assert _build_ask_event("Q?", ["a", "b"], suggested_index="x")["suggested"] == "a"
    slider = _build_ask_event("Q?", [], widget="slider", scale={"min": 0, "max": 10, "unit": "h"})
    assert slider is not None and slider["suggested"] == "0.0h"
    rating = _build_ask_event("Q?", [], widget="rating", scale={})
    assert rating is not None and rating["suggested"] is None


def test_reply_locale_helpers() -> None:
    from realmock.domains.prep.agents.context import infer_text_locale, normalize_ui_locale

    assert normalize_ui_locale("zh-CN") == "zh-CN"
    assert normalize_ui_locale("fr") == ""
    assert normalize_ui_locale(None) == ""
    assert infer_text_locale("本科毕业于济南大学，无实习经历怎么办") == "zh-CN"
    assert infer_text_locale("How do I prepare for a backend interview at ByteDance") == "en"
    assert infer_text_locale("") == "zh-CN"


async def test_tool_step_carries_args_and_result() -> None:
    from realmock.domains.prep.agents.streaming import event_loopbacks

    seen: list[dict] = []
    events: asyncio.Queue = asyncio.Queue()
    _, on_tool, _ = event_loopbacks(events, on_tool_step=seen.append)
    await on_tool("web_search", {"query": "q", "max_results": 3}, "obs text", "c1")
    assert seen[0]["args"] == {"max_results": "3", "query": "q"}
    assert seen[0]["result"] == "obs text"
    assert seen[0]["query"] == "q"
    event = await events.get()
    assert event["type"] == "tool_step" and event["result"] == "obs text"


# --- memory tools (sessions.db roundtrip) ---


async def test_memory_write_list_detail_roundtrip(db) -> None:
    from realmock.domains.prep.services import list_memories

    assert list_memories(db, limit=1) is not None
    text, hits = await prep_tools.execute_prep_tool(
        "memory_write",
        {"summary": "User targets backend roles", "tags": ["target", "backend"],
         "user_input": "I want backend", "origin": "user_emphasis"},
        _memory(),
    )
    assert hits == []
    payload = json.loads(text)
    assert payload["id"] > 0

    text, _ = await prep_tools.execute_prep_tool(
        "memory_list_summaries", {"limit": 5}, _memory()
    )
    items = json.loads(text)["memories"]
    assert any(i["id"] == payload["id"] and i["summary"] == "User targets backend roles" for i in items)

    text, _ = await prep_tools.execute_prep_tool(
        "memory_get_detail", {"id": payload["id"]}, _memory()
    )
    detail = json.loads(text)
    assert detail["user_input"] == "I want backend"
    assert set(detail["tags"]) == {"target", "backend"}

    text, _ = await prep_tools.execute_prep_tool("memory_list_tags", {}, _memory())
    assert "backend" in json.loads(text)["tags"]


async def test_memory_write_requires_summary_and_validates_id(db) -> None:
    text, _ = await prep_tools.execute_prep_tool("memory_write", {"tags": ["x"]}, _memory())
    assert "missing summary" in text
    text, _ = await prep_tools.execute_prep_tool("memory_get_detail", {"id": -3}, _memory())
    assert json.loads(text)["error"] == "invalid_id"
    text, _ = await prep_tools.execute_prep_tool("memory_get_detail", {"id": 999999999}, _memory())
    assert json.loads(text)["error"] == "not_found"


# --- Agent state recovery ---


def test_load_messages_corrupt_json_recovers_empty() -> None:
    agent = _agent(messages="not-json{{{")
    assert agent.messages == []


async def test_ensure_system_seeds_coach_prompt() -> None:
    agent = _agent()
    assert agent.messages == []
    await agent._ensure_system(db=None)
    # Prefix-stable seed: one system message per block, stable instructions first.
    assert agent.messages and all(m["role"] == "system" for m in agent.messages)
    assert "interview-prep coach" in agent.messages[0]["content"]
    # Second call is a no-op once the history exists.
    seeded = list(agent.messages)
    await agent._ensure_system(db=None)
    assert agent.messages == seeded


# --- HTTP: create + history scrub ---


def test_create_prep_session_issues_id_and_cookie(db) -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/prep/sessions",
            json={"target_role": "Backend", "target_company": "bytedance"},
        )
    assert resp.status_code == 200
    assert isinstance(resp.json()["id"], int)
    assert resp.headers.get("set-cookie"), "creation must issue a session cookie"


def test_get_prep_messages_sanitizes_without_mutating_db(db) -> None:
    token = new_access_token()
    raw = json.dumps(
        [
            {"role": "system", "content": "sys"},
            {"role": "assistant", "content": "hello <|im_start|>leak"},
        ],
        ensure_ascii=False,
    )
    session = PrepSession(access_token=token, status="active", messages=raw)
    db.add(session)
    db.commit()
    db.refresh(session)

    with TestClient(app) as client:
        resp = client.get(
            f"/api/v1/prep/sessions/{session.id}/messages",
            headers={"X-Interview-Token": token},
        )
    assert resp.status_code == 200
    assistant = [m for m in resp.json() if m["role"] == "assistant"]
    assert len(assistant) == 1
    assert "<|im_start|>" not in assistant[0]["content"]
    assert "hello" in assistant[0]["content"]
    # Stored history keeps the original bytes; scrubbing is display-only.
    db.refresh(session)
    assert "<|im_start|>" in session.messages


# --- Error contract: business errors propagate, nothing else does ---


async def test_execute_business_error_propagates() -> None:
    from realmock.platform.core.errors import CATALOG, ApiBusinessError

    async def forbidden(name, args, db):
        raise ApiBusinessError(CATALOG["A3001"], message="gone")

    execute = _callback(forbidden, error_context={"domain": "prep", "session": "1"})
    try:
        await execute("memory_list_tags", {})
    except ApiBusinessError as exc:
        assert exc.error_code == "A3001"
    else:
        raise AssertionError("ApiBusinessError must propagate, not become an observation")


async def test_execute_refuses_tools_after_dialog() -> None:
    calls = 0

    async def runner(name, args, db):
        nonlocal calls
        calls += 1
        return "obs", []

    # Dialog already shown: domain tools are refused without executing.
    execute = _callback(runner, asked_user={"on": True})
    out = await execute("web_search", {"query": "q"})
    assert "already awaiting the user" in out
    # A second dialog in the same turn is refused as well.
    dup = await execute("ask_user", {"question": "Q?", "options": ["a", "b"]})
    assert "already shown this turn" in dup
    assert calls == 0


async def test_timeout_observation_carries_structured_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow(name, args, db):
        await asyncio.sleep(5)
        return "late", []

    import realmock.domains.prep.agents.tool_exec as tool_exec

    monkeypatch.setattr(tool_exec, "_TOOL_TIMEOUT_SEC", 0.05)
    execute = _callback(slow)
    out = await execute("web_search", {"query": "slow q"})
    # Legacy marker stays for older prompts; the structured code is authoritative.
    assert "SEARCH_UNAVAILABLE" in out
    assert tool_exec.RETRIEVAL_ERROR_CODE in out
    line = next(text for text in out.splitlines() if text.startswith("{"))
    payload = json.loads(line)
    assert payload["error"] == tool_exec.RETRIEVAL_ERROR_CODE


def test_definitions_cover_registry() -> None:
    """Model-facing definitions must stay a superset of the dispatch registry."""
    defs = {d["function"]["name"] for d in prep_tools.PREP_TOOL_DEFINITIONS}
    assert set(prep_tools.TOOL_REGISTRY) <= defs


# --- memory_write idempotency ---


async def test_memory_write_deduplicates_by_summary(db) -> None:
    from realmock.domains.prep.services import list_memories

    memory = _memory()
    first, _ = await prep_tools.execute_prep_tool(
        "memory_write", {"summary": "Idempotent target fact", "tags": ["t"]}, memory
    )
    second, _ = await prep_tools.execute_prep_tool(
        "memory_write", {"summary": "Idempotent target fact", "tags": ["t"]}, _memory()
    )
    assert json.loads(first)["id"] == json.loads(second)["id"]
    assert json.loads(second).get("deduplicated") is True
    db.expire_all()
    rows = [r for r in list_memories(db, limit=50) if r.summary == "Idempotent target fact"]
    assert len(rows) == 1


async def test_memory_write_idempotency_key_survives_retries(db) -> None:
    memory = _memory()
    args = {"summary": "Keyed fact for retry", "idempotency_key": "turn-42-topic"}
    first, _ = await prep_tools.execute_prep_tool("memory_write", args, memory)
    second, _ = await prep_tools.execute_prep_tool("memory_write", args, memory)
    assert json.loads(first)["id"] == json.loads(second)["id"]
    assert json.loads(second).get("deduplicated") is True


async def test_memory_write_per_turn_budget(db) -> None:
    """At most 2 memory_write dispatches per turn; the 3rd is refused without side effects."""
    agent = _agent()
    kw = {"db": db}
    first, _ = await agent._run_named_tool("memory_write", {"summary": "Budget fact one"}, **kw)
    second, _ = await agent._run_named_tool("memory_write", {"summary": "Budget fact two"}, **kw)
    assert "budget exhausted" not in first + second
    third, _ = await agent._run_named_tool("memory_write", {"summary": "Budget fact three"}, **kw)
    assert "budget exhausted" in third
    agent._turn_state.reset()
    fourth, _ = await agent._run_named_tool("memory_write", {"summary": "Budget fact four"}, **kw)
    assert "budget exhausted" not in fourth


# --- Context cache layout ---


def test_system_messages_are_prefix_stable() -> None:
    from realmock.domains.prep.agents.context import (
        LANG_HINT_MARKER,
        PREP_SYSTEM,
        build_system_message,
        build_system_messages,
    )

    blocks = build_system_messages(
        db=None, resume_id=None, target_company="", linked_session_id=None
    )
    assert len(blocks) >= 1
    assert all(b["role"] == "system" for b in blocks)
    # Stable instructions first and byte-identical regardless of volatile tail.
    assert blocks[0]["content"] == PREP_SYSTEM
    # Reply-language hint is a per-turn suffix, never part of the seed.
    assert all(LANG_HINT_MARKER not in b["content"] for b in blocks)
    assert LANG_HINT_MARKER not in build_system_message(
        db=None, resume_id=None, target_company=""
    )


def test_upsert_lang_hint_is_idempotent() -> None:
    from realmock.domains.prep.agents.context import LANG_HINT_MARKER, upsert_lang_hint

    base = [{"role": "user", "content": "hi"}]
    once = upsert_lang_hint(base, "zh-CN")
    assert once[-1]["role"] == "system"
    assert once[-1]["content"].startswith(LANG_HINT_MARKER)
    twice = upsert_lang_hint(once, "en")
    hints = [m for m in twice if str(m.get("content") or "").startswith(LANG_HINT_MARKER)]
    # No accumulation: exactly one trailing hint, refreshed to the new locale.
    assert len(hints) == 1 and twice[-1] is hints[0]
    assert "UI language is en." in hints[0]["content"]


# --- Schema validation ---


def test_message_request_rejects_blank_content() -> None:
    import pydantic

    from realmock.domains.prep.schemas import PrepMessageRequest

    with pytest.raises(pydantic.ValidationError):
        PrepMessageRequest(content="   ")
    assert PrepMessageRequest(content="  hi ").content == "hi"


def test_memory_batch_delete_rejects_empty_ids() -> None:
    import pydantic

    from realmock.domains.prep.schemas import PrepMemoryBatchDelete

    with pytest.raises(pydantic.ValidationError):
        PrepMemoryBatchDelete(ids=[])


# --- Context breakdown ---


def test_context_breakdown_buckets_messages() -> None:
    from realmock.domains.prep.agents.context import (
        BREAKDOWN_ORDER,
        build_context_breakdown,
    )

    counts = build_context_breakdown([
        {"role": "system", "content": "Coach instructions"},
        {"role": "user", "content": "hello world"},
        {"role": "assistant", "content": "hi there", "thinking": "reasoning here",
         "tool_calls": [{"id": "c1", "function": {"name": "quiz"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "observation text"},
        {"role": "system", "content": "[Working memory]\n{}"},
        {"role": "system", "content": "[Conversation Minutes] prior notes"},
        {"role": "system", "content": "[Referenced sessions]\nLinked session #1"},
        {"role": "system", "content": "[Reply language] The UI language is en."},
    ])
    assert set(counts) == set(BREAKDOWN_ORDER)
    assert counts["user"] > 0 and counts["assistant"] > 0
    assert counts["thinking"] > 0 and counts["tools"] > 0
    # Seeded prompt and lang hint are system; memory/summary/refs are memory.
    assert counts["system"] > 0 and counts["memory"] > 0
    assert counts["other"] == 0


def test_strip_ref_blocks_keeps_history_clean() -> None:
    from realmock.domains.prep.agents.context import strip_ref_blocks

    kept = [{"role": "user", "content": "q"}]
    messages = kept + [{"role": "system", "content": "[Referenced sessions]\nLinked session #2"}]
    assert strip_ref_blocks(messages) == kept


def test_format_linked_sessions_caps_and_skips_unknown(db) -> None:
    import json as _json

    from realmock.domains.prep.agents.context import format_linked_sessions
    from realmock.domains.prep.models import PrepSession
    from realmock.platform.core.session_auth import new_access_token as _token

    first = PrepSession(access_token=_token(), status="active",
                        messages=_json.dumps([{"role": "user", "content": "turn one"}]))
    second = PrepSession(access_token=_token(), status="active",
                         messages=_json.dumps([{"role": "user", "content": "turn two"}]))
    db.add_all([first, second])
    db.commit()
    db.refresh(first)
    db.refresh(second)
    out = format_linked_sessions(
        db, [first.id, 999999999, second.id, first.id, -3], exclude_id=second.id + 1000,
    )
    assert "turn one" in out and "turn two" in out
    # Self references never leak into the block.
    own = format_linked_sessions(db, [first.id], exclude_id=first.id)
    assert own == ""


def test_message_request_context_refs_bounded() -> None:
    import pydantic

    from realmock.domains.prep.schemas import PrepMessageRequest

    assert PrepMessageRequest(content="hi", context_session_ids=[1, 2]).context_session_ids == [1, 2]
    assert PrepMessageRequest(content="hi").context_session_ids is None
    with pytest.raises(pydantic.ValidationError):
        PrepMessageRequest(content="hi", context_session_ids=[1, 2, 3, 4, 5, 6])
