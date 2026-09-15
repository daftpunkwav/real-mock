"""Report-agent branch tests for realmock.domains.records.agents.report.agent.

Covers: _turn_ids/split_turn_ids edges, build_context_specs resume/profile/github wiring, synthesis-none raise and turn-notes batch-failure fallback
Conventions: DB/LLM faked; no network; rate limits reset per test
"""
from __future__ import annotations
from unittest.mock import patch
import pytest
from realmock.domains.records.schemas.report import DebriefReport
from realmock.platform.core.ratelimit import reset_rate_limit

@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()

def test_agent_turn_ids_non_list() -> None:
    from realmock.domains.records.agents.report import agent as mod

    assert mod._turn_ids({}) == []
    assert mod._turn_ids({"turns": "bad"}) == []
    assert mod.split_turn_ids([]) == []

def test_agent_build_context_with_resume(monkeypatch) -> None:
    import realmock.domains.records.agents.report.agent as mod

    @patch("realmock.domains.records.agents.report.agent.api_db_session")
    def _run(mock_sess):
        mock_db = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        mock_sess.return_value.__enter__.return_value = mock_db
        monkeypatch.setattr(
            mod, "get_resume_agent_payload", lambda db, rid: {"id": rid}
        )
        monkeypatch.setattr(mod, "snapshot_from_payload", lambda p: "snap")
        monkeypatch.setattr(mod, "resume_tool_specs", lambda snap: ["rspec"])
        monkeypatch.setattr(mod, "get_user_profile", lambda db, pid: "row")
        monkeypatch.setattr(mod, "profile_from_orm", lambda row: "psnap")
        monkeypatch.setattr(mod, "profile_tool_specs", lambda snap: ["pspec"])
        monkeypatch.setattr(mod, "github_tool_specs", lambda: ["gspec"])
        specs = mod.build_context_specs(resume_id=1, profile_id=2)
        assert specs == ["rspec", "pspec", "gspec"]

    _run()

@pytest.mark.asyncio
async def test_agent_synthesis_none_raises(monkeypatch) -> None:
    from realmock.domains.records.agents.report.agent import DeepReportAgent
    from tests.fakes import FakeLLMClient

    async def _none(*a, **k):
        return None

    async def _empty_batch(*a, **k):
        return []

    monkeypatch.setattr(
        "realmock.domains.records.agents.report.agent.run_synthesis", _none
    )
    monkeypatch.setattr(
        "realmock.domains.records.agents.report.agent.run_turn_notes_batch",
        _empty_batch,
    )
    agent = DeepReportAgent(FakeLLMClient(), context_specs=[])
    with pytest.raises(RuntimeError, match="no payload"):
        await agent.run(role="BE", level="S", company="Acme", ledger={"turns": []})

@pytest.mark.asyncio
async def test_agent_batch_failure_returns_empty(monkeypatch) -> None:
    from realmock.domains.records.agents.report.agent import DeepReportAgent
    from tests.fakes import FakeLLMClient

    async def _boom(*a, **k):
        raise RuntimeError("batch down")

    async def _synth(*a, **k):
        return {"overall_score": 80, "turn_notes": []}

    monkeypatch.setattr(
        "realmock.domains.records.agents.report.agent.run_turn_notes_batch", _boom
    )
    monkeypatch.setattr(
        "realmock.domains.records.agents.report.agent.run_synthesis", _synth
    )
    agent = DeepReportAgent(FakeLLMClient(), context_specs=[])
    ledger = {"turns": [{"turn_id": "t-0001"}]}
    report = await agent.run(role="BE", level="S", company="Acme", ledger=ledger)
    assert isinstance(report, DebriefReport)
