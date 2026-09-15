"""Ledger-tool tests for realmock.domains.records.agents.report.ledger_tools.

Covers: _turns/_turn_text edges and ledger_read_turns/ledger_search handlers
Conventions: Pure in-memory ledger; no LLM/DB; rate limits reset per test
"""
from __future__ import annotations
import asyncio
import json
import pytest
from realmock.platform.core.ratelimit import reset_rate_limit

@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()

@pytest.mark.asyncio
async def test_ledger_gaps() -> None:
    from realmock.domains.records.agents.report import ledger_tools as mod

    assert mod._turns({}) == []
    assert mod._turns({"turns": "bad"}) == []
    assert "hi" in mod._turn_text({"assistant": "hi string", "user": None})
    ledger = {
        "turns": [
            {
                "turn_id": f"t-{i:04d}",
                "phase": "tech",
                "assistant": {"text": f"q{i} keyword"},
                "user": {"text": f"a{i}"},
                "tools": [],
            }
            for i in range(10)
        ]
    }
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}
    out = json.loads(await specs["ledger_read_turns"].handler({"turn_ids": ["t-0001"]}))
    assert out["returned"] == 1
    empty = json.loads(await specs["ledger_search"].handler({"keyword": ""}))
    assert empty["error"] == "empty_keyword"
    many = json.loads(await specs["ledger_search"].handler({"keyword": "keyword"}))
    assert len(many["matches"]) <= 8
    await asyncio.sleep(0)
