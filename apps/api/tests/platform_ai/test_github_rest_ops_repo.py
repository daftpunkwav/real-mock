"""GitHub repo REST ops tests for src/realmock/platform/capabilities/integrations/github/rest_ops_repo.py.

Covers: _get_repo/_get_readme/_list_commits/_list_pull_requests/_list_issues/
_get_tree/_get_file_content/_get_languages mapping, clamp, truncation, and error
branches (client._get faked).
Conventions: no real network/model downloads (all clients mocked).
"""
from __future__ import annotations

import base64

import pytest

from realmock.platform.capabilities.integrations.github import rest_ops_repo as repo_mod
from realmock.platform.capabilities.integrations.github.github_http import MAX_TEXT_CHARS


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def _get(self, path, params=None):
        self.calls.append({"path": path, "params": params})
        resp = self._response
        if callable(resp):
            return resp(path, params)
        return resp


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


@pytest.mark.asyncio
async def test_get_repo_success_and_error():
    err = {"error": "not_found", "status": 404}
    assert await repo_mod._get_repo(_FakeClient(err), "o", "r") == err
    payload = {
        "full_name": "o/r",
        "description": "d",
        "language": "Python",
        "languages_url": "u",
        "stargazers_count": 5,
        "forks_count": 1,
        "open_issues_count": 2,
        "default_branch": "main",
        "created_at": "2020",
        "updated_at": "2021",
        "pushed_at": "2022",
        "topics": None,
        "license": None,
        "html_url": "https://github.com/o/r",
        "size": 100,
    }
    out = await repo_mod._get_repo(_FakeClient(payload), "o", "r")
    assert out["full_name"] == "o/r"
    assert out["topics"] == []
    assert out["license"] is None
    payload2 = dict(payload, topics=["a"], license={"spdx_id": "MIT"})
    out2 = await repo_mod._get_repo(_FakeClient(payload2), "o", "r")
    assert out2["topics"] == ["a"]
    assert out2["license"] == "MIT"


@pytest.mark.asyncio
async def test_get_readme_base64_and_truncation(monkeypatch):
    text = "hello readme"
    payload = {
        "content": _b64(text),
        "encoding": "base64",
        "name": "README.md",
        "path": "README.md",
    }
    out = await repo_mod._get_readme(_FakeClient(payload), "o", "r")
    assert out["content"] == text
    assert out["truncated"] is False
    # Force truncation with small limit.
    monkeypatch.setattr(repo_mod, "MAX_TEXT_CHARS", 4)
    out2 = await repo_mod._get_readme(_FakeClient(payload), "o", "r")
    assert out2["content"] == text[:4]
    assert out2["truncated"] is True


@pytest.mark.asyncio
async def test_get_readme_decode_failed():
    payload = {"content": "a", "encoding": "base64"}
    out = await repo_mod._get_readme(_FakeClient(payload), "o", "r")
    assert out["error"] == "decode_failed"


@pytest.mark.asyncio
async def test_get_readme_error_and_raw_and_unavailable():
    err = {"error": "not_found"}
    assert await repo_mod._get_readme(_FakeClient(err), "o", "r") == err
    raw_text = "raw body text"
    out = await repo_mod._get_readme(_FakeClient({"raw": raw_text}), "o", "r")
    assert out["content"] == raw_text
    assert out["truncated"] is False
    # Long raw truncates at real limit.
    long_raw = "x" * (MAX_TEXT_CHARS + 10)
    out2 = await repo_mod._get_readme(_FakeClient({"raw": long_raw}), "o", "r")
    assert out2["truncated"] is True
    assert len(out2["content"]) == MAX_TEXT_CHARS
    out3 = await repo_mod._get_readme(_FakeClient({}), "o", "r")
    assert out3["error"] == "readme_unavailable"


@pytest.mark.asyncio
async def test_list_commits_mapping_and_clamp():
    payload = [
        {
            "sha": "abcdef123456",
            "commit": {
                "message": "first line\nsecond line",
                "author": {"name": "a", "date": "2020"},
            },
            "html_url": "https://x/1",
        },
        {"sha": "", "commit": {}, "html_url": None},
    ]
    client = _FakeClient(payload)
    out = await repo_mod._list_commits(client, "o", "r", per_page=100, author="bob")
    assert out["count"] == 2
    assert out["commits"][0]["sha"] == "abcdef12"
    assert out["commits"][0]["message"] == "first line"
    assert client.calls[0]["params"] == {"per_page": 20, "author": "bob"}
    client2 = _FakeClient(payload)
    await repo_mod._list_commits(client2, "o", "r", per_page=0)
    assert client2.calls[0]["params"]["per_page"] == 1
    assert await repo_mod._list_commits(_FakeClient({"error": "x"}), "o", "r") == {"error": "x"}
    assert await repo_mod._list_commits(_FakeClient({}), "o", "r") == {
        "error": "unexpected_response"
    }
    # Long message truncated to 200.
    long_msg = "m" * 300
    payload_long = [{"sha": "s", "commit": {"message": long_msg, "author": {}}, "html_url": None}]
    out_long = await repo_mod._list_commits(_FakeClient(payload_long), "o", "r")
    assert len(out_long["commits"][0]["message"]) == 200


@pytest.mark.asyncio
async def test_list_pulls_mapping():
    payload = [
        {
            "number": 1,
            "title": "t",
            "state": "open",
            "user": {"login": "u"},
            "created_at": "c",
            "merged_at": None,
            "html_url": "h",
        }
    ]
    client = _FakeClient(payload)
    out = await repo_mod._list_pull_requests(client, "o", "r", state="open", per_page=5)
    assert out["count"] == 1
    assert out["pulls"][0]["user"] == "u"
    assert client.calls[0]["params"] == {"state": "open", "per_page": 5, "sort": "updated"}
    assert await repo_mod._list_pull_requests(_FakeClient({"error": "e"}), "o", "r") == {
        "error": "e"
    }
    assert await repo_mod._list_pull_requests(_FakeClient({}), "o", "r") == {
        "error": "unexpected_response"
    }


@pytest.mark.asyncio
async def test_list_issues_filters_prs():
    payload = [
        {
            "number": 1,
            "title": "issue",
            "state": "open",
            "user": {"login": "u"},
            "comments": 2,
            "created_at": "c",
            "html_url": "h",
        },
        {"number": 2, "title": "pr", "pull_request": {"url": "x"}},
    ]
    out = await repo_mod._list_issues(_FakeClient(payload), "o", "r", state="all", per_page=10)
    assert out["count"] == 1
    assert out["issues"][0]["number"] == 1
    assert await repo_mod._list_issues(_FakeClient({"error": "e"}), "o", "r") == {"error": "e"}
    assert await repo_mod._list_issues(_FakeClient("bad"), "o", "r") == {
        "error": "unexpected_response"
    }


@pytest.mark.asyncio
async def test_get_tree_variants():
    err = {"error": "not_found"}
    assert await repo_mod._get_tree(_FakeClient(err), "o", "r", branch="main") == err
    assert await repo_mod._get_tree(_FakeClient({}), "o", "r", branch="main") == {
        "error": "unexpected_response"
    }
    assert await repo_mod._get_tree(_FakeClient({"tree": {}}), "o", "r", branch="main") == {
        "error": "unexpected_response"
    }
    payload = {
        "sha": "s",
        "truncated": True,
        "tree": [
            {"path": "a.py", "type": "blob", "size": 10},
            {"path": "dir", "type": "tree", "size": None},
            "bad-entry",
        ],
    }
    client = _FakeClient(payload)
    out = await repo_mod._get_tree(client, "o", "r", branch="main", recursive=True)
    assert out["truncated"] is True
    assert len(out["tree"]) == 2
    assert out["tree"][0]["path"] == "a.py"
    assert client.calls[0]["params"] == {"recursive": "1"}
    client2 = _FakeClient(payload)
    await repo_mod._get_tree(client2, "o", "r", branch="dev", recursive=False)
    assert client2.calls[0]["params"] is None
    assert client2.calls[0]["path"] == "/repos/o/r/git/trees/dev"


@pytest.mark.asyncio
async def test_get_file_content_variants(monkeypatch):
    err = {"error": "not_found"}
    assert await repo_mod._get_file_content(_FakeClient(err), "o", "r", "a.py") == err
    # Directory listing capped at 50.
    entries = [{"name": f"f{i}", "type": "file", "path": f"f{i}", "size": i} for i in range(60)]
    out = await repo_mod._get_file_content(_FakeClient(entries), "o", "r", "dir")
    assert out["type"] == "dir"
    assert len(out["entries"]) == 50
    assert await repo_mod._get_file_content(_FakeClient("bad"), "o", "r", "x") == {
        "error": "unexpected_response"
    }
    out2 = await repo_mod._get_file_content(_FakeClient({"type": "symlink"}), "o", "r", "x")
    assert out2["type"] == "symlink"
    assert out2["message"] == "non-file node"
    # Decode failure.
    out3 = await repo_mod._get_file_content(
        _FakeClient({"type": "file", "content": "a"}), "o", "r", "x"
    )
    assert out3["error"] == "decode_failed"
    # Success file + truncation.
    text = "hello file"
    payload = {
        "type": "file",
        "path": "a.py",
        "size": 10,
        "content": _b64(text),
        "html_url": "h",
    }
    client = _FakeClient(payload)
    out4 = await repo_mod._get_file_content(client, "o", "r", "/a.py", ref="main")
    assert out4["content"] == text
    assert out4["truncated"] is False
    assert client.calls[0]["path"] == "/repos/o/r/contents/a.py"
    assert client.calls[0]["params"] == {"ref": "main"}
    client2 = _FakeClient(payload)
    await repo_mod._get_file_content(client2, "o", "r", "a.py")
    assert client2.calls[0]["params"] is None
    # Long file truncates.
    monkeypatch.setattr(repo_mod, "MAX_TEXT_CHARS", 3)
    out5 = await repo_mod._get_file_content(_FakeClient(payload), "o", "r", "a.py")
    assert out5["content"] == text[:3]
    assert out5["truncated"] is True


@pytest.mark.asyncio
async def test_get_languages_variants():
    err = {"error": "x"}
    assert await repo_mod._get_languages(_FakeClient(err), "o", "r") == err
    assert await repo_mod._get_languages(_FakeClient([]), "o", "r") == {
        "error": "unexpected_response"
    }
    out = await repo_mod._get_languages(_FakeClient({"Python": 80, "JS": 20}), "o", "r")
    assert out["languages"]["Python"]["pct"] == 80.0
    assert out["languages"]["JS"]["bytes"] == 20
    # Non-numeric ignored; empty dict avoids div-zero.
    out2 = await repo_mod._get_languages(_FakeClient({"Python": "x"}), "o", "r")
    assert out2["languages"] == {}
    out3 = await repo_mod._get_languages(_FakeClient({}), "o", "r")
    assert out3["languages"] == {}
