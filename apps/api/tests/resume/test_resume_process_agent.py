"""Review process agent tests for src/realmock/domains/resume/agents/process.py.

Covers: _decode_escapes surrogate/CJK branches, ReviewProcess._parse_titles
shape branches, update_step invalid-mode/unknown/last-skip branches,
plan_titles_from_tool_names prefix/filter branches, process_tool_specs
invalid-plan/get/unknown branches.
Conventions: no real network/model downloads (all clients mocked); pure logic.
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_decode_surrogate_kept() -> None:
    from realmock.domains.resume.agents.process import _decode_escapes

    # Lone surrogate stays escaped.
    assert _decode_escapes(r"\ud800 hi") == r"\ud800 hi"
    assert _decode_escapes(r"\u4e2d") == "中"


@pytest.mark.asyncio
async def test_parse_titles_branches() -> None:
    from realmock.domains.resume.agents.process import ReviewProcess

    p = ReviewProcess()
    assert isinstance(p._parse_titles("not-a-list"), str)
    assert isinstance(p._parse_titles([]), str)
    assert isinstance(p._parse_titles([{}, "  "]), str)
    # Too few steps.
    assert isinstance(p._parse_titles(["only one Generate evaluation JSON"]), str)
    # Last step missing evaluation keyword.
    titles = [f"step {i}" for i in range(8)]
    assert isinstance(p._parse_titles(titles), str)


@pytest.mark.asyncio
async def test_update_step_invalid_mode_unknown_and_last_skip() -> None:
    from realmock.domains.resume.agents.process import ReviewProcess

    p = ReviewProcess()
    await p.set_plan([f"step {i}" for i in range(7)] + ["Generate evaluation JSON"])
    out = json.loads(await p.update_step("1", "done", "", mode="bogus"))
    assert out["error"] == "invalid_mode"
    out2 = json.loads(await p.update_step("ghost", "done", ""))
    assert out2["error"] == "unknown_step"
    last_id = p.steps[-1].id
    out3 = json.loads(await p.update_step(last_id, "skipped", ""))
    assert out3["error"] == "last_step_cannot_skip"


@pytest.mark.asyncio
async def test_plan_titles_skips_review_prefix() -> None:
    from realmock.domains.resume.agents.process import plan_titles_from_tool_names

    titles = plan_titles_from_tool_names(["review_set_plan", "web_search", "web_search"])
    assert titles[-1] == "Generate evaluation JSON"
    assert "web search" in titles
    assert not any(t.startswith("review_") for t in titles)


@pytest.mark.asyncio
async def test_process_tool_specs_invalid_plan_and_get() -> None:
    from realmock.domains.resume.agents.process import ReviewProcess, process_tool_specs

    p = ReviewProcess()
    specs = {s.name: s for s in process_tool_specs(p)}
    out = json.loads(await specs["review_set_plan"].handler({"steps": []}))
    assert out["error"] == "invalid_plan"
    out2 = json.loads(await specs["review_get_plan"].handler({}))
    assert out2["steps"] == []
    out3 = json.loads(await specs["review_update_step"].handler({"id": "ghost", "status": "done"}))
    assert out3["error"] == "unknown_step"
