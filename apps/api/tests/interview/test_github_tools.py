"""Unit tests for the GitHub tool layer (without accessing the real network)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from realmock.platform.capabilities.integrations.github.client import GitHubClient
from realmock.platform.capabilities.integrations.github.tools import GITHUB_TOOL_DEFINITIONS, execute_github_tool
from realmock.domains.interview.services.interview.tools import (
    get_interview_tool_definitions,
    parse_tool_arguments,
)


def test_tool_definitions_non_empty():
    assert len(GITHUB_TOOL_DEFINITIONS) >= 8
    names = {t["function"]["name"] for t in GITHUB_TOOL_DEFINITIONS}
    assert "github_get_readme" in names
    assert "github_list_commits" in names


def test_interview_tools_include_github_and_local():
    tools = get_interview_tool_definitions()
    names = {t["function"]["name"] for t in tools}
    assert "github_get_user" in names
    assert "lookup_company_profile" in names
    assert "lookup_resume_projects" in names


def test_parse_tool_arguments():
    assert parse_tool_arguments('{"username": "octocat"}') == {"username": "octocat"}
    assert parse_tool_arguments({"a": 1}) == {"a": 1}
    assert parse_tool_arguments("not-json") == {}
    assert parse_tool_arguments(None) == {}


@pytest.mark.asyncio
async def test_execute_github_get_user_mocked():
    client = GitHubClient(token="")
    fake = {
        "login": "octocat",
        "name": "The Octocat",
        "bio": "hi",
        "public_repos": 8,
        "followers": 1000,
        "following": 9,
        "company": "GitHub",
        "blog": "",
        "location": "SF",
        "created_at": "2011-01-01",
        "html_url": "https://github.com/octocat",
    }
    with patch.object(client, "get_user", new=AsyncMock(return_value=fake)):
        raw = await execute_github_tool(
            "github_get_user",
            {"username": "octocat"},
            client=client,
        )
    data = json.loads(raw)
    assert data["login"] == "octocat"
    assert data["public_repos"] == 8


@pytest.mark.asyncio
async def test_execute_unknown_tool():
    raw = await execute_github_tool("not_a_tool", {})
    data = json.loads(raw)
    assert data["error"] == "unknown_github_tool"


@pytest.mark.asyncio
async def test_github_client_get_user_http(monkeypatch):
    """Mock httpx response."""
    class FakeResp:
        status_code = 200
        content = b'{"login":"u","name":"U","bio":null,"public_repos":1,"followers":0,"following":0,"company":null,"blog":"","location":null,"created_at":"2020","html_url":"https://github.com/u"}'

        def json(self):
            return json.loads(self.content)

        @property
        def text(self):
            return self.content.decode()

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, headers=None, params=None):
            return FakeResp()

    with patch("realmock.platform.capabilities.integrations.github.client.httpx.AsyncClient", return_value=FakeClient()):
        client = GitHubClient(token="t")
        data = await client.get_user("u")
    assert data["login"] == "u"


@pytest.mark.asyncio
async def test_github_client_get_tree_http():
    """Public get_tree method: recursively fetch the tree and return compact entries (the tree-fetching path used by repo_evidence)."""
    import httpx  # noqa: F401 - the patched target module attribute must already be imported

    tree_payload = {
        "sha": "abc123",
        "truncated": False,
        "tree": [
            {"path": "pyproject.toml", "type": "blob", "size": 100},
            {"path": "src", "type": "tree", "size": None},
        ],
    }

    class FakeResp:
        status_code = 200
        content = json.dumps(tree_payload).encode()

        def json(self):
            return json.loads(self.content)

        @property
        def text(self):
            return self.content.decode()

    captured: dict = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, headers=None, params=None):
            captured["url"] = url
            captured["params"] = params
            return FakeResp()

    with patch("realmock.platform.capabilities.integrations.github.client.httpx.AsyncClient", return_value=FakeClient()):
        client = GitHubClient(token="t")
        data = await client.get_tree("owner", "repo", branch="main")
    assert captured["url"].endswith("/repos/owner/repo/git/trees/main")
    assert captured["params"] == {"recursive": "1"}
    assert data["sha"] == "abc123"
    assert data["truncated"] is False
    assert data["tree"][0]["path"] == "pyproject.toml"


@pytest.mark.asyncio
async def test_github_client_get_tree_error_passthrough():
    """Pass API error responses through as a dict containing an error key so the caller can degrade gracefully."""

    class FakeResp:
        status_code = 404
        content = b'{"message": "Not Found"}'

        def json(self):
            return {"message": "Not Found"}

        @property
        def text(self):
            return self.content.decode()

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, headers=None, params=None):
            return FakeResp()

    with patch("realmock.platform.capabilities.integrations.github.client.httpx.AsyncClient", return_value=FakeClient()):
        client = GitHubClient(token="t")
        data = await client.get_tree("owner", "repo", branch="dev")
    assert "error" in data
