"""Interview tools dispatch tests for src/realmock/domains/interview/agents/tools.py.

Covers: tool definitions, _cap_result, findings caps, github/profile/resume/company/search/past dispatch
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from realmock.domains.interview.agents import tools as tmod
from realmock.domains.interview.agents.tools import (
    _cap_result,
    _note_company_finding,
    execute_interview_tool,
    get_interview_tool_definitions,
)


def test_tool_definitions_include_local_and_github() -> None:
    tools = get_interview_tool_definitions()
    names = {(t.get("function") or {}).get("name") for t in tools}
    assert "lookup_company_profile" in names
    assert "lookup_resume_projects" in names
    assert "web_search" in names
    assert "web_fetch" in names
    assert "github_get_user" in names
    assert "search_past_interviews" not in names


def test_tool_definitions_include_past_records_when_flag() -> None:
    tools = get_interview_tool_definitions(include_past_records=True)
    names = {(t.get("function") or {}).get("name") for t in tools}
    assert "search_past_interviews" in names
    assert "read_past_round" in names


@pytest.mark.asyncio
async def test_cap_result_passthrough_small() -> None:
    assert _cap_result("hello") == "hello"


@pytest.mark.asyncio
async def test_cap_result_large_no_llm_marks_excerpt() -> None:
    big = "x" * 90000
    out = _cap_result(big)
    assert "middle omitted" in out


@pytest.mark.asyncio
async def test_cap_result_large_keeps_head_and_tail() -> None:
    big = "y" * 90000
    out = _cap_result(big)
    assert "middle omitted" in out
    assert out.startswith("y") and out.endswith("y")


def test_note_company_finding_none_state_noop() -> None:
    # None agent_state is the documented noop: returns None, creates nothing.
    assert (
        _note_company_finding(None, tool="lookup_company_profile", subject="bytedance", result="r")
        is None
    )


def test_note_company_finding_appends_and_caps() -> None:
    state: dict = {}
    _note_company_finding(
        state, tool="lookup_company_profile", subject="bytedance", result="r" * 600
    )
    assert state["company_findings"][0]["tool"] == "lookup_company_profile"
    assert len(state["company_findings"][0]["preview"]) == 600
    for i in range(12):
        _note_company_finding(state, tool="t", subject=str(i), result="r")
    assert len(state["company_findings"]) == 10


@contextmanager
def _fake_api_db(row=None):
    class _Ctx:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    yield _Ctx()


@pytest.mark.asyncio
async def test_execute_github_tool_records_findings(monkeypatch) -> None:
    async def fake_github(name, args):
        return json.dumps({"ok": True, "name": name, "args": args})

    monkeypatch.setattr(tmod, "execute_github_tool", fake_github)
    state: dict = {}
    out = await execute_interview_tool(
        "github_get_repo", {"owner": "o", "repo": "r"}, db=None, agent_state=state
    )
    assert '"ok": true' in out or '"ok": True' in out or "ok" in out
    assert state["github_findings"][0]["tool"] == "github_get_repo"


@pytest.mark.asyncio
async def test_execute_github_autofills_username_from_profile(monkeypatch) -> None:
    seen: dict = {}

    async def fake_github(name, args):
        seen.update(args)
        return "{}"

    class _Profile:
        github_username = "octocat"

    monkeypatch.setattr(tmod, "execute_github_tool", fake_github)
    monkeypatch.setattr(tmod, "api_db_session", lambda: _fake_api_db())
    monkeypatch.setattr(tmod, "get_user_profile", lambda db, pid: _Profile())
    state: dict = {}
    await execute_interview_tool("github_get_user", {}, db=None, profile_id=7, agent_state=state)
    assert seen.get("username") == "octocat"
    assert len(state["github_findings"]) == 1


@pytest.mark.asyncio
async def test_execute_github_findings_capped_at_20(monkeypatch) -> None:
    async def fake_github(name, args):
        return "r"

    monkeypatch.setattr(tmod, "execute_github_tool", fake_github)
    state: dict = {
        "github_findings": [{"tool": "x", "args": {}, "preview": "p"} for _ in range(20)]
    }
    await execute_interview_tool("github_list_repos", {"username": "u"}, db=None, agent_state=state)
    assert len(state["github_findings"]) == 20


@pytest.mark.asyncio
async def test_execute_profile_tool_success(monkeypatch) -> None:
    from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec

    async def handler(args):
        return json.dumps({"section": "basics"})

    monkeypatch.setattr(tmod, "api_db_session", lambda: _fake_api_db())
    monkeypatch.setattr(tmod, "get_user_profile", lambda db, pid: object())
    monkeypatch.setattr(tmod, "profile_from_orm", lambda row: object())
    monkeypatch.setattr(
        tmod,
        "profile_tool_specs",
        lambda snap: [
            ToolSpec(name="profile_list_sections", description="d", parameters={}, handler=handler)
        ],
    )
    out = await execute_interview_tool("profile_list_sections", {}, db=None, profile_id=1)
    assert "basics" in out


@pytest.mark.asyncio
async def test_execute_profile_unknown_tool(monkeypatch) -> None:
    monkeypatch.setattr(tmod, "api_db_session", lambda: _fake_api_db())
    monkeypatch.setattr(tmod, "get_user_profile", lambda db, pid: None)
    monkeypatch.setattr(tmod, "profile_from_orm", lambda row: object())
    monkeypatch.setattr(tmod, "profile_tool_specs", lambda snap: [])
    out = await execute_interview_tool("profile_nope", {}, db=None, profile_id=1)
    assert json.loads(out)["error"] == "unknown_tool"


@pytest.mark.asyncio
async def test_execute_resume_no_bound(monkeypatch) -> None:
    monkeypatch.setattr(tmod, "api_db_session", lambda: _fake_api_db())
    monkeypatch.setattr(tmod, "get_resume_agent_payload", lambda db, rid: None)
    out = await execute_interview_tool("resume_get_text", {}, db=None, resume_id=None)
    assert json.loads(out)["error"] == "no_resume_bound"


@pytest.mark.asyncio
async def test_execute_resume_unknown_tool(monkeypatch) -> None:
    monkeypatch.setattr(tmod, "api_db_session", lambda: _fake_api_db())
    monkeypatch.setattr(tmod, "get_resume_agent_payload", lambda db, rid: {"a": 1})
    monkeypatch.setattr(tmod, "snapshot_from_payload", lambda p: object())
    monkeypatch.setattr(tmod, "resume_tool_specs", lambda snap: [])
    out = await execute_interview_tool("resume_nope", {}, db=None, resume_id=5)
    assert json.loads(out)["error"] == "unknown_tool"


@pytest.mark.asyncio
async def test_execute_resume_success(monkeypatch) -> None:
    from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec

    async def handler(args):
        return "resume-text"

    monkeypatch.setattr(tmod, "api_db_session", lambda: _fake_api_db())
    monkeypatch.setattr(tmod, "get_resume_agent_payload", lambda db, rid: {"a": 1})
    monkeypatch.setattr(tmod, "snapshot_from_payload", lambda p: object())
    monkeypatch.setattr(
        tmod,
        "resume_tool_specs",
        lambda snap: [
            ToolSpec(name="resume_get_text", description="d", parameters={}, handler=handler)
        ],
    )
    out = await execute_interview_tool("resume_get_text", {}, db=None, resume_id=5)
    assert "resume-text" in out


@pytest.mark.asyncio
async def test_lookup_company_profile_records_finding() -> None:
    state: dict = {}
    out = await execute_interview_tool(
        "lookup_company_profile", {"company_id": "bytedance"}, db=None, agent_state=state
    )
    assert "ByteDance" in out or "bytedance" in out.lower()
    assert state["company_findings"][0]["tool"] == "lookup_company_profile"


@pytest.mark.asyncio
async def test_lookup_company_profile_unknown_company() -> None:
    out = await execute_interview_tool(
        "lookup_company_profile", {"company_id": ""}, db=None, agent_state=None
    )
    assert isinstance(out, str) and len(out) > 0


@pytest.mark.asyncio
async def test_lookup_resume_projects_no_resume() -> None:
    out = await execute_interview_tool("lookup_resume_projects", {}, db=None, resume_id=None)
    assert json.loads(out)["error"] == "no_resume_bound"


@pytest.mark.asyncio
async def test_lookup_resume_projects_not_found(monkeypatch) -> None:
    monkeypatch.setattr(tmod, "api_db_session", lambda: _fake_api_db())
    monkeypatch.setattr(tmod, "get_resume_detail", lambda db, rid: None)
    out = await execute_interview_tool("lookup_resume_projects", {}, db=None, resume_id=9)
    assert json.loads(out)["error"] == "resume_not_found"


@pytest.mark.asyncio
async def test_lookup_resume_projects_filters_focus(monkeypatch) -> None:
    profile = {
        "name": "Ada",
        "skills": ["Python", "Go"],
        "projects": [
            {"name": "FastAPI app", "stack": "Python"},
            {"name": "K8s deploy", "stack": "Go"},
        ],
        "summary": "backend dev",
    }
    monkeypatch.setattr(tmod, "api_db_session", lambda: _fake_api_db())
    monkeypatch.setattr(tmod, "get_resume_detail", lambda db, rid: ("r.pdf", profile))
    state: dict = {}
    out = await execute_interview_tool(
        "lookup_resume_projects", {"focus": "fastapi"}, db=None, resume_id=1, agent_state=state
    )
    assert "FastAPI" in out
    assert "K8s" not in out
    assert state["company_findings"][0]["tool"] == "lookup_resume_projects"


@pytest.mark.asyncio
async def test_web_search_empty_query() -> None:
    out = await execute_interview_tool("web_search", {"query": ""}, db=None)
    assert json.loads(out)["error"] == "empty_query"


@pytest.mark.asyncio
async def test_web_search_success(monkeypatch) -> None:
    async def fake_search(args):
        return json.dumps({"text": "hits for x"})

    monkeypatch.setattr(tmod, "execute_web_search", fake_search)
    out = await execute_interview_tool("web_search", {"query": "bytedance interview"}, db=None)
    assert "hits for x" in out


@pytest.mark.asyncio
async def test_web_search_failure_turns_observation(monkeypatch) -> None:
    async def boom(args):
        raise RuntimeError("net down")

    monkeypatch.setattr(tmod, "execute_web_search", boom)
    out = await execute_interview_tool("web_search", {"query": "q"}, db=None)
    data = json.loads(out)
    assert data["error"] == "search_failed"
    assert "net down" in data["message"]


@pytest.mark.asyncio
async def test_web_fetch_success(monkeypatch) -> None:
    async def fake_fetch(args):
        return json.dumps({"url": args["url"], "title": "T", "text": "page body"})

    monkeypatch.setattr(tmod, "execute_web_fetch", fake_fetch)
    out = await execute_interview_tool("web_fetch", {"url": "https://example.com/post"}, db=None)
    assert "page body" in out


@pytest.mark.asyncio
async def test_web_fetch_failure_stays_observation(monkeypatch) -> None:
    async def unavailable(args):
        return "FETCH_FAILED could not fetch the page"

    monkeypatch.setattr(tmod, "execute_web_fetch", unavailable)
    out = await execute_interview_tool("web_fetch", {"url": "https://example.com/post"}, db=None)
    assert out.startswith("FETCH_FAILED")


@pytest.mark.asyncio
async def test_past_tools_require_session() -> None:
    out = await execute_interview_tool(
        "search_past_interviews", {"query": "cache"}, db=None, session=None
    )
    assert json.loads(out)["error"] == "no_process_context"
    out2 = await execute_interview_tool("read_past_round", {"round_no": 1}, db=None, session=None)
    assert json.loads(out2)["error"] == "no_process_context"


@pytest.mark.asyncio
async def test_past_tools_dispatch(monkeypatch) -> None:
    import realmock.domains.interview.agents.past_records as pr

    monkeypatch.setattr(pr, "search_past_interviews", lambda db, s, q: '{"matches":[]}')
    monkeypatch.setattr(pr, "read_past_round", lambda db, s, r, o: '{"turns":[]}')
    sentinel = object()
    out = await execute_interview_tool(
        "search_past_interviews", {"query": "x"}, db=None, session=sentinel
    )
    assert "matches" in out
    out2 = await execute_interview_tool(
        "read_past_round", {"round_no": 1, "offset": 0}, db=None, session=sentinel
    )
    assert "turns" in out2


@pytest.mark.asyncio
async def test_unknown_tool() -> None:
    out = await execute_interview_tool("does_not_exist", {}, db=None)
    assert json.loads(out)["error"] == "unknown_tool"


@pytest.mark.asyncio
async def test_read_past_round_rejects_malformed_args_without_raising() -> None:
    """Non-numeric paging args answer with an observation instead of raising
    into ToolGuard, whose breaker would open the tool after two bad calls."""
    for bad in ({"round_no": "two"}, {"round_no": {"a": 1}}, {"round_no": 1, "offset": "x"}):
        out = await execute_interview_tool("read_past_round", bad, db=None, session=object())
        assert json.loads(out)["error"] == "invalid_argument"
