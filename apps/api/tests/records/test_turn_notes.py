"""Turn notes tests for src/realmock/domains/records/agents/report/turn_notes_agent.py.

Covers: _invoke_tool/_extract_notes/_run_loop/run_turn_notes_batch/_repair_missing bounds
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.records.agents.report.turn_notes_agent import (
    _extract_notes,
    _invoke_tool,
    _repair_missing,
    _run_loop,
    run_turn_notes_batch,
)
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _llm_empty() -> MagicMock:
    m = MagicMock()
    m.api_key = ""
    return m


# ---- finalize ----
















# ---- synthesis ----










# ---- turn notes ----


@pytest.mark.asyncio
async def test_invoke_tool_returns_raw() -> None:
    from realmock.platform.capabilities.ai.agent.tools.spec import ToolBundle

    bundle = ToolBundle()
    with patch(
        "realmock.domains.records.agents.report.turn_notes_agent.invoke_with_timeout",
        new=AsyncMock(return_value=("raw", "done")),
    ):
        assert await _invoke_tool(bundle, "x", {}) == "raw"


def test_extract_notes_variants() -> None:
    assert _extract_notes(None, ["t-0001"]) == []
    assert _extract_notes({"notes": "bad"}, ["t-0001"]) == []
    single = _extract_notes({"turn_id": "t-0001", "score": 80}, ["t-0001"])
    assert len(single) == 1 and single[0]["turn_id"] == "t-0001"
    # Unknown turn filtered.
    assert _extract_notes({"turn_id": "t-9999", "score": 80}, ["t-0001"]) == []
    # Garbage note dropped.
    assert _extract_notes({"notes": ["garbage"]}, ["t-0001"]) == []


@pytest.mark.asyncio
async def test_run_loop_thinking_emits_only_nonblank() -> None:
    events: list[dict] = []

    async def _on_event(event: dict) -> None:
        events.append(event)

    async def _fake_run(*a, **k):
        on_thinking = k.get("on_thinking")
        await on_thinking("  hello  ")
        await on_thinking("   ")
        return SimpleNamespace()

    with patch("realmock.platform.capabilities.ai.agent.run_agent_loop", side_effect=_fake_run):
        await _run_loop(MagicMock(), [], [], AsyncMock(), AsyncMock(), _on_event)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_run_turn_notes_batch_no_missing() -> None:
    ledger = {"turns": [{"turn_id": "t-0001"}]}
    loop = SimpleNamespace(final_content="{}", messages=[])
    payload = {"notes": [{"turn_id": "t-0001", "score": 80}]}
    with (
        patch(
            "realmock.domains.records.agents.report.turn_notes_agent._run_loop",
            new=AsyncMock(return_value=loop),
        ),
        patch(
            "realmock.domains.records.agents.report.turn_notes_agent.finalize_json",
            new=AsyncMock(return_value=payload),
        ),
        patch(
            "realmock.domains.records.agents.report.turn_notes_agent._repair_missing",
            new=AsyncMock(),
        ) as rep,
    ):
        notes = await run_turn_notes_batch(
            _llm_empty(),
            ledger=ledger,
            turn_ids=["t-0001"],
            batch_label="b1",
            role="r",
            level="l",
            company="c",
            context_specs=[],
        )
    assert [n["turn_id"] for n in notes] == ["t-0001"]
    rep.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_turn_notes_batch_repairs_missing() -> None:
    ledger = {"turns": [{"turn_id": "t-0001"}]}
    loop = SimpleNamespace(final_content="{}", messages=[])
    with (
        patch(
            "realmock.domains.records.agents.report.turn_notes_agent._run_loop",
            new=AsyncMock(return_value=loop),
        ),
        patch(
            "realmock.domains.records.agents.report.turn_notes_agent.finalize_json",
            new=AsyncMock(return_value={"notes": []}),
        ),
        patch(
            "realmock.domains.records.agents.report.turn_notes_agent._repair_missing",
            new=AsyncMock(return_value=[{"turn_id": "t-0001", "score": 60}]),
        ),
    ):
        notes = await run_turn_notes_batch(
            _llm_empty(),
            ledger=ledger,
            turn_ids=["t-0001"],
            batch_label="b1",
            role="r",
            level="l",
            company="c",
            context_specs=[],
        )
    assert notes[0]["turn_id"] == "t-0001"


@pytest.mark.asyncio
async def test_repair_missing_bounds_turns() -> None:
    ledger = {"turns": []}
    turn_ids = [f"t-{i:04d}" for i in range(20)]
    loop = SimpleNamespace(final_content="{}", messages=[])
    seen: dict = {}
    real_specs = __import__(
        "realmock.domains.records.agents.report.ledger_tools", fromlist=["ledger_tool_specs"]
    ).ledger_tool_specs

    def _spy(ledger_arg, turn_ids=None):
        seen["n"] = len(turn_ids or [])
        return real_specs(ledger_arg, turn_ids=turn_ids)

    with (
        patch(
            "realmock.domains.records.agents.report.turn_notes_agent.ledger_tool_specs",
            side_effect=_spy,
        ),
        patch(
            "realmock.domains.records.agents.report.turn_notes_agent._run_loop",
            new=AsyncMock(return_value=loop),
        ),
        patch(
            "realmock.domains.records.agents.report.turn_notes_agent.finalize_json",
            new=AsyncMock(return_value={"notes": []}),
        ),
    ):
        out = await _repair_missing(
            _llm_empty(),
            ledger,
            turn_ids=turn_ids,
            batch_label="b",
            role="r",
            level="l",
            company="c",
            context_specs=[],
            on_event=None,
        )
    assert out == []
    assert seen["n"] == 12
