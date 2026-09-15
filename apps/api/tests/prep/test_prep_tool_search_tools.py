"""Search-tools tests for realmock.domains.prep.agents.tools.system.search_tools.

Covers: search_specs catalog/empty/bad-spec/description-match branches, run_search_tools flows and mini_spec
Conventions: Catalog faked; no network; rate limits reset per test
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

def test_search_specs_catalog_failure_returns_empty(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.system.search_tools as search_mod

    monkeypatch.setattr(search_mod, "_secondary_catalog", lambda: 1 / 0)
    assert search_mod.search_specs("repo") == []

def test_search_specs_skips_empty_name_and_bad_spec(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.system.search_tools as search_mod
    from realmock.domains.prep.agents.tools.spec import ToolSpec

    async def _noop(args, memory):
        return "x", []

    empty = ToolSpec(name="", description="d", parameters={}, handler=_noop)
    bad_kw = ToolSpec(
        name="demo-tool", description="demo desc", parameters={},
        handler=_noop, keywords=(123,),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        search_mod, "_secondary_catalog", lambda: {"e": empty, "b": bad_kw}
    )
    assert search_mod.search_specs("zzz-no-match-xyz") == []
    assert search_mod.search_specs("") == []

@pytest.mark.asyncio
async def test_run_search_tools_catalog_failure(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.system.search_tools as search_mod

    monkeypatch.setattr(search_mod, "_secondary_catalog", lambda: 1 / 0)
    text, hits = await search_mod.run_search_tools({"query": "repo"}, _memory())
    assert "candidates" in text
    assert hits == []

@pytest.mark.asyncio
async def test_run_search_tools_select_flows(monkeypatch) -> None:
    import json as _json

    import realmock.domains.prep.agents.tools.system.search_tools as search_mod

    text, _ = await search_mod.run_search_tools(
        {"query": "repo file", "select": "not-a-list"}, _memory()
    )
    payload = _json.loads(text)
    assert "candidates" in payload
    assert payload["loaded"] == []

    text2, _ = await search_mod.run_search_tools(
        {"query": "github file", "select": ["github_get_file", "not_a_tool"]}, _memory()
    )
    payload2 = _json.loads(text2)
    assert "github_get_file" in payload2["loaded"]
    assert "not_a_tool" in payload2["unknown"]
    assert "github_get_file" in payload2["catalog"]

def test_mini_spec_non_dict_params() -> None:
    from realmock.domains.prep.agents.tools.system.search_tools import mini_spec
    from realmock.domains.prep.agents.tools.spec import ToolSpec

    async def _noop(args, memory):
        return "x", []

    spec = ToolSpec(name="demo", description="First. Second.", parameters=[], handler=_noop)
    card = mini_spec(spec)
    assert card["name"] == "demo"
    assert card["params"] == []
    assert card["summary"] == "First"

def test_search_specs_description_match() -> None:
    from realmock.domains.prep.agents.tools.system.search_tools import search_specs

    # "followers" lives only in github_get_user description, not in name/keywords.
    hits = search_specs("followers")
    assert any(h.name == "github_get_user" for h in hits)
