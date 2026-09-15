"""GitHub client tests for apps/api/src/realmock/platform/capabilities/integrations/github/client.py.

Covers: GitHubClient thin wrappers delegating to _get (rate_limit/user/repos/repo/
tree/readme/commits/pulls/issues/file/languages).

Conventions: no real network (client._get faked); asyncio_mode=auto.
"""

from __future__ import annotations

import pytest



@pytest.mark.asyncio
async def test_client_thin_wrappers_delegate(monkeypatch) -> None:
    from realmock.platform.capabilities.integrations.github.client import GitHubClient

    async def _fake_get(path, params=None):
        if path == "/rate_limit":
            return {"ok": True}
        if path.startswith("/users/") and path.endswith("/repos"):
            return []
        if path.startswith("/users/"):
            return {"login": "o", "public_repos": 1}
        if "/git/trees/" in path:
            return {"sha": "s", "tree": []}
        if path.endswith("/readme"):
            return {"raw": "hi"}
        if path.endswith("/commits"):
            return []
        if path.endswith("/pulls"):
            return []
        if path.endswith("/issues"):
            return []
        if "/contents/" in path:
            return {"type": "file", "content": "aGVsbG8=", "encoding": "base64", "path": "a.py"}
        if path.endswith("/languages"):
            return {"Python": 10}
        return {"full_name": "o/r"}

    c = GitHubClient.__new__(GitHubClient)
    c._headers = {}
    c._get = _fake_get  # type: ignore[method-assign]
    assert await c.get_rate_limit() == {"ok": True}
    assert (await c.get_user("o"))["login"] == "o"
    assert (await c.list_repos("o", per_page=5))["count"] == 0
    assert (await c.get_repo("o", "r"))["full_name"] == "o/r"
    assert (await c.get_tree("o", "r", branch="main"))["tree"] == []
    assert (await c.get_readme("o", "r"))["content"] == "hi"
    assert (await c.list_commits("o", "r"))["count"] == 0
    assert (await c.list_pull_requests("o", "r"))["count"] == 0
    assert (await c.list_issues("o", "r"))["count"] == 0
    assert (await c.get_file_content("o", "r", "a.py"))["content"] == "hello"
    assert (await c.get_languages("o", "r"))["languages"]["Python"]["bytes"] == 10
