"""Web-search tool tests for realmock.domains.prep.agents.tools.basic.web_search.

Covers: run_web_search fake passthrough and GitHubClient.get_user fake
Conventions: execute_web_search and GitHubClient faked; no network; rate limits reset per test
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
async def test_web_search_fake_and_github_client_fake(monkeypatch) -> None:
    from realmock.domains.prep.agents.tools.basic import web_search as web_search_tool
    from realmock.platform.capabilities.integrations.github.client import GitHubClient

    async def _fake_execute(args, **kwargs):
        return '{"results": [], "text": "fake-web"}'

    monkeypatch.setattr(web_search_tool, "execute_web_search", _fake_execute)
    text, hits = await web_search_tool.run_web_search({"query": "q", "max_results": "bad"}, _memory())
    assert text == "fake-web"
    assert hits == []

    async def _fake_get_user(self, username):
        return {"login": username}

    monkeypatch.setattr(GitHubClient, "get_user", _fake_get_user)
    client = GitHubClient(token="t")
    assert (await client.get_user("octocat"))["login"] == "octocat"
