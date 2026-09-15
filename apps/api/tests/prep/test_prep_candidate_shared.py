"""Candidate shared-tool tests for realmock.domains.prep.agents.tools.candidate.shared.

Covers: run_profile_or_resume passthrough and load_profile_or_resume_spec branches
Conventions: No real DB/LLM; api_db_session and profile/resume loaders faked; rate limits reset per test
"""
from __future__ import annotations
import json
from types import SimpleNamespace
import pytest

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def _tool_spec(name: str):
    async def _handler(args: dict):
        return f"obs:{name}:{json.dumps(args, ensure_ascii=False)}"

    return SimpleNamespace(name=name, handler=_handler)

@pytest.mark.asyncio
async def test_run_profile_or_resume_passthrough_and_success(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.candidate.shared as shared

    monkeypatch.setattr(shared, "load_profile_or_resume_spec", lambda name, rid: '{"error":"x"}')
    out, hits = await shared.run_profile_or_resume("profile_list_sections", {}, resume_id=None)
    assert out == '{"error":"x"}'
    assert hits == []

    async def _handler(args: dict):
        return "ok-obs"

    monkeypatch.setattr(shared, "load_profile_or_resume_spec", lambda name, rid: SimpleNamespace(handler=_handler))
    out2, hits2 = await shared.run_profile_or_resume("resume_overview", {"a": 1}, resume_id=3)
    assert out2 == "ok-obs"
    assert hits2 == []

def test_load_profile_or_resume_spec_branches(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.candidate.shared as shared

    class _Ctx:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(shared, "api_db_session", lambda: _Ctx())

    # profile unknown tool
    monkeypatch.setattr(shared, "get_default_user_profile", lambda db: object())
    monkeypatch.setattr(shared, "profile_from_orm", lambda p: {"x": 1})
    monkeypatch.setattr(shared, "profile_tool_specs", lambda snap: [_tool_spec("profile_list_sections")])
    err = shared.load_profile_or_resume_spec("profile_unknown", None)
    assert json.loads(err)["error"] == "unknown_tool"
    ok = shared.load_profile_or_resume_spec("profile_list_sections", None)
    assert ok.name == "profile_list_sections"

    # resume no bound
    monkeypatch.setattr(shared, "get_resume_agent_payload", lambda db, rid: None)
    err2 = shared.load_profile_or_resume_spec("resume_overview", None)
    assert json.loads(err2)["error"] == "no_resume_bound"

    # resume unknown + success
    monkeypatch.setattr(shared, "get_resume_agent_payload", lambda db, rid: {"id": 1})
    monkeypatch.setattr(shared, "snapshot_from_payload", lambda p: {"s": 1})
    monkeypatch.setattr(shared, "resume_tool_specs", lambda snap: [_tool_spec("resume_overview")])
    err3 = shared.load_profile_or_resume_spec("resume_missing", 1)
    assert json.loads(err3)["error"] == "unknown_tool"
    ok2 = shared.load_profile_or_resume_spec("resume_overview", 1)
    assert ok2.name == "resume_overview"
