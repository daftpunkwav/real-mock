"""Compact tool tests for realmock.domains.prep.agents.tools.system.compact.

Covers: run_compact_out_of_loop guard
Conventions: No LLM; direct call only; rate limits reset per test
"""
from __future__ import annotations
import pytest
from realmock.platform.capabilities.ai.agent import WorkingMemory

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def _memory() -> WorkingMemory:
    return WorkingMemory()

@pytest.mark.asyncio
async def test_compact_out_of_loop() -> None:
    from realmock.domains.prep.agents.tools.system.compact import run_compact_out_of_loop

    text, hits = await run_compact_out_of_loop({}, _memory())
    assert "inside the turn loop only" in text
    assert hits == []
