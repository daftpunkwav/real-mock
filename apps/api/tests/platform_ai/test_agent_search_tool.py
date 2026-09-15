"""Web-search agent tool tests for apps/api/src/realmock/platform/capabilities/ai/agent/tools/search.py.

Covers: max-results clamping, empty-query guard, open/job-board merge paths and
search_tool_spec handler wiring.

Conventions: no real network (web_search_with_hits faked via monkeypatch); asyncio_mode=auto.
"""

from __future__ import annotations

import json

import pytest

import realmock.platform.capabilities.ai.agent.tools.search as search_mod


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def test_clamp_bad_input() -> None:
    assert search_mod._clamp_max_results("bad") == search_mod.SEARCH_DEFAULT_MAX_RESULTS
    assert search_mod._clamp_max_results(None) == search_mod.SEARCH_DEFAULT_MAX_RESULTS
    assert search_mod._clamp_max_results(100) == search_mod.SEARCH_HARD_MAX_RESULTS
    assert search_mod._clamp_max_results(0) == 1


@pytest.mark.asyncio
async def test_empty_query() -> None:
    out = json.loads(await search_mod.execute_web_search({}))
    assert out["error"] == "empty_query"


@pytest.mark.asyncio
async def test_open_search_merges_and_calls_back(monkeypatch) -> None:
    hits = [{"url": "https://a.example", "title": "a", "snippet": "s"}]

    def _fake(query, max_results, sites=None):
        assert sites is None
        return "open-block", list(hits)

    monkeypatch.setattr(search_mod, "web_search_with_hits", _fake)
    seen: dict = {}

    def _on(query, got):
        seen["q"] = query
        seen["n"] = len(got)

    out = json.loads(
        await search_mod.execute_web_search({"query": "python jobs", "max_results": 5}, on_hits=_on)
    )
    assert out["query"] == "python jobs"
    assert out["hit_count"] == 1
    assert "open-block" in out["text"]
    assert seen == {"q": "python jobs", "n": 1}


@pytest.mark.asyncio
async def test_job_board_merge_dedups(monkeypatch) -> None:
    open_hits = [{"url": "https://same.example", "title": "t", "snippet": "s"}]
    board_hits = [
        {"url": "https://same.example", "title": "t", "snippet": "s"},
        {"url": "https://new.example", "title": "n", "snippet": "s"},
    ]

    def _fake(query, max_results, sites=None):
        if sites is None:
            return "open", list(open_hits)
        return "board", list(board_hits)

    monkeypatch.setattr(search_mod, "web_search_with_hits", _fake)
    out = json.loads(
        await search_mod.execute_web_search(
            {"query": "q", "prefer_job_boards": True}, sites=["jobs.example"]
        )
    )
    assert out["hit_count"] == 2
    assert "[Job-board scoped]" in out["text"]


@pytest.mark.asyncio
async def test_job_board_no_extra_no_block(monkeypatch) -> None:
    hit = {"url": "https://same.example", "title": "t", "snippet": "s"}

    def _fake(query, max_results, sites=None):
        return "t", [dict(hit)]

    monkeypatch.setattr(search_mod, "web_search_with_hits", _fake)
    out = json.loads(
        await search_mod.execute_web_search({"query": "q", "prefer_job_boards": True}, sites=["j"])
    )
    assert out["hit_count"] == 1
    assert "[Job-board scoped]" not in out["text"]


@pytest.mark.asyncio
async def test_spec_forces_job_boards(monkeypatch) -> None:
    def _fake(query, max_results, sites=None):
        return ("board" if sites else "open"), [{"url": "https://x", "title": "t", "snippet": "s"}]

    monkeypatch.setattr(search_mod, "web_search_with_hits", _fake)
    spec = search_mod.search_tool_spec(sites=["jobs.example"], force_job_boards=True)
    assert spec.name == "web_search"
    assert "always included" in spec.description
    out = json.loads(await spec.handler({"query": "golang"}))
    assert out["query"] == "golang"
    plain = search_mod.search_tool_spec()
    assert "prefer_job_boards=true" in plain.description
