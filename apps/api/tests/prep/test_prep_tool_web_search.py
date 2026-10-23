"""Web-search tool tests for realmock.domains.prep.agents.tools.basic.web_search.

Covers: run_web_search fake passthrough and GitHubClient.get_user fake
Conventions: execute_web_search and GitHubClient faked; no network; rate limits reset per test
"""

from __future__ import annotations

import json

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
async def test_web_search_fake_and_github_client_fake(monkeypatch) -> None:
    from realmock.domains.prep.agents.tools.basic import web_search as web_search_tool
    from realmock.platform.capabilities.integrations.github.client import GitHubClient

    async def _fake_execute(args, **kwargs):
        return '{"results": [], "text": "fake-web"}'

    monkeypatch.setattr(web_search_tool, "execute_web_search", _fake_execute)
    text, hits = await web_search_tool.run_web_search(
        {"query": "q", "max_results": "bad"}, _memory()
    )
    assert text == "fake-web"
    assert hits == []

    async def _fake_get_user(self, username):
        return {"login": username}

    monkeypatch.setattr(GitHubClient, "get_user", _fake_get_user)
    client = GitHubClient(token="t")
    assert (await client.get_user("octocat"))["login"] == "octocat"


@pytest.mark.asyncio
async def test_web_search_non_finite_max_results_degrades(monkeypatch) -> None:
    """A non-finite max_results falls back to the default, not raise.

    ``json.loads`` accepts ``Infinity`` (and ``1e400``), so a model answer can
    carry ``inf``; ``int(float('inf'))`` raises OverflowError, which is not a
    ValueError and therefore slips past the tolerant coercion.
    """
    from realmock.domains.prep.agents.tools.basic import web_search as web_search_tool

    seen: list[dict] = []

    async def _fake_execute(args, **kwargs):
        seen.append(args)
        return '{"results": [], "text": "fake-web"}'

    monkeypatch.setattr(web_search_tool, "execute_web_search", _fake_execute)
    cases = [
        {"query": "q", "max_results": float("inf")},
        json.loads('{"query": "q", "max_results": Infinity}'),
    ]
    for args in cases:
        text, hits = await web_search_tool.run_web_search(args, _memory())
        assert text == "fake-web"
        assert hits == []
    assert [call["max_results"] for call in seen] == [
        web_search_tool._WEB_SEARCH_MAX_RESULTS,
        web_search_tool._WEB_SEARCH_MAX_RESULTS,
    ]
