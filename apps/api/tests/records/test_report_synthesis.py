"""Report synthesis tests for src/realmock/domains/records/agents/report/synthesis_agent.py.

Covers: web-budget consume, loop passthrough, synthesis events/finalize, budget exhaustion
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.records.agents.report.synthesis_agent import (
    _consume_web_budget,
    run_agent_loop_safe,
    run_synthesis,
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


def test_consume_web_budget_unknown_tool_free() -> None:
    budget = {"web_search": 1}
    assert _consume_web_budget(budget, "report_read_notes") is None
    assert budget == {"web_search": 1}


@pytest.mark.asyncio
async def test_run_agent_loop_safe_passthrough() -> None:
    sentinel = object()
    with patch(
        "realmock.platform.capabilities.ai.agent.run_agent_loop",
        new=AsyncMock(return_value=sentinel),
    ):
        out = await run_agent_loop_safe(MagicMock(), [], [], AsyncMock(), None, None)
        assert out is sentinel


@pytest.mark.asyncio
async def test_run_synthesis_emits_events_and_finalizes() -> None:
    events: list[dict] = []

    async def _on_event(event: dict) -> None:
        events.append(event)

    ledger = {"turns": []}
    notes = [{"turn_id": "t-0001"}]
    fake_loop = SimpleNamespace(final_content='{"overall_score": 70}', messages=[])

    with (
        patch(
            "realmock.domains.records.agents.report.synthesis_agent.run_agent_loop_safe",
            new=AsyncMock(return_value=fake_loop),
        ),
        patch(
            "realmock.domains.records.agents.report.synthesis_agent.finalize_json",
            new=AsyncMock(return_value={"overall_score": 70}),
        ) as fin,
    ):
        out = await run_synthesis(
            _llm_empty(),
            ledger=ledger,
            notes=notes,
            role="Backend",
            level="junior",
            company="acme",
            workflow_type="technical",
            strictness=3,
            interview_style="deep_dive",
            session_result="passed",
            process_context="ctx",
            on_event=_on_event,
        )
    assert out == {"overall_score": 70}
    fin.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_synthesis_execute_charges_web_budget() -> None:
    ledger = {"turns": []}
    captured: dict = {}

    async def _fake_loop(llm, messages, tools, execute, on_tool, on_thinking):
        # Exhaust web_search budget: 4 allowed then exhaustion marker.
        for _ in range(5):
            captured.setdefault("results", []).append(await execute("web_search", {}))
        await on_tool("web_search", {"q": "x"}, "ok", "tc-1")
        await on_thinking("  thinking here  ")
        await on_thinking("   ")
        return SimpleNamespace(final_content="{}", messages=[])

    with (
        patch(
            "realmock.domains.records.agents.report.synthesis_agent.run_agent_loop_safe",
            side_effect=_fake_loop,
        ),
        patch(
            "realmock.platform.capabilities.ai.agent.tools.invoke_with_timeout",
            new=AsyncMock(return_value=("raw-ok", "done")),
        ),
        patch(
            "realmock.domains.records.agents.report.synthesis_agent.finalize_json",
            new=AsyncMock(return_value={}),
        ),
    ):
        await run_synthesis(
            _llm_empty(),
            ledger=ledger,
            notes=[],
            role="r",
            level="l",
            company="c",
            workflow_type="technical",
            strictness=3,
            interview_style="deep_dive",
            session_result=None,
        )
    assert captured["results"][4].startswith("SEARCH_UNAVAILABLE")


# ---- turn notes ----












