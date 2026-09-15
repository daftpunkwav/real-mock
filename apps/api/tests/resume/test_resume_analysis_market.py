"""Analysis market tests for src/realmock/domains/resume/services/analysis_market.py.

Covers: get_market_context_cached hit/evict branches, gather_resume_market_context
empty/open/board/dedup/error branches (generate/gather and web_search faked).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


@pytest.mark.asyncio
async def test_market_cache_hit_and_evict(monkeypatch) -> None:
    import realmock.domains.resume.services.analysis_market as mk
    from realmock.platform.models import Resume

    mk._MARKET_CACHE.clear()
    row = Resume(filename="a.pdf", file_type="pdf", raw_text="body-text", parsed_profile="{}")
    calls = {"gen": 0}

    async def _gen(r, llm):
        calls["gen"] += 1
        return ["q1"], True

    async def _gather(r, queries):
        return "ctx", queries

    monkeypatch.setattr(mk, "generate_market_queries", _gen)
    monkeypatch.setattr(mk, "gather_resume_market_context", _gather)
    ctx1, q1 = await mk.get_market_context_cached(row, SimpleNamespace())
    ctx2, q2 = await mk.get_market_context_cached(row, SimpleNamespace())
    assert ctx1 == ctx2 == "ctx"
    assert calls["gen"] == 1

    mk._MARKET_CACHE.clear()
    from realmock.domains.resume.schemas.limits import MARKET_CACHE_MAX

    async def _gen2(r, llm):
        return ["q"], True

    async def _gather2(r, queries):
        return "c", queries

    monkeypatch.setattr(mk, "generate_market_queries", _gen2)
    monkeypatch.setattr(mk, "gather_resume_market_context", _gather2)
    for i in range(MARKET_CACHE_MAX + 2):
        r = Resume(filename="a.pdf", file_type="pdf", raw_text=f"body-{i}", parsed_profile="{}")
        await mk.get_market_context_cached(r, SimpleNamespace())
    assert len(mk._MARKET_CACHE) == MARKET_CACHE_MAX
    mk._MARKET_CACHE.clear()


@pytest.mark.asyncio
async def test_gather_market_context_branches(monkeypatch) -> None:
    import realmock.domains.resume.services.analysis_market as mk
    from realmock.platform.models import Resume

    assert await mk.gather_resume_market_context(Resume(filename="a", file_type="pdf", raw_text="x"), []) == ("", [])

    import realmock.platform.capabilities.knowledge.search.web as web_mod

    def _fake_search(query, hits_n, sites=None):
        if query == "boom":
            raise RuntimeError("net-down")
        if sites:
            return "board-text", [{"title": "b", "url": "https://board.example/j", "snippet": "s"}]
        return "open-text", [{"title": "t", "url": "https://example.com/a", "snippet": "s"}]

    monkeypatch.setattr(web_mod, "web_search_with_hits", _fake_search)
    row = Resume(filename="a", file_type="pdf", raw_text="x")
    ctx, used = await mk.gather_resume_market_context(row, ["q1", "boom"])
    assert used == ["q1"]
    assert "[Open web]" in ctx
    assert "[Job-board scoped]" in ctx
    assert "https://example.com/a" in ctx

    def _dup_search(query, hits_n, sites=None):
        hit = {"title": "t", "url": "https://same.example/a", "snippet": "s"}
        return "t", [hit]

    monkeypatch.setattr(web_mod, "web_search_with_hits", _dup_search)
    ctx2, used2 = await mk.gather_resume_market_context(row, ["q2"])
    assert used2 == ["q2"]
    # same URL in board+open yields no extra board block
    assert "[Job-board scoped]" not in ctx2
