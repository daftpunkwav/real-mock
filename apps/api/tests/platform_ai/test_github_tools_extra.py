"""GitHub tools extra tests for apps/api/src/realmock/platform/capabilities/integrations/github/tools.py.

Covers: execute_github_tool unknown-tool, get_user/list_repos delegation,
repo/readme/commits/pulls/issues/file/languages delegation and
missing-argument/execution-failed branches.

Conventions: no real network (GitHub client faked); asyncio_mode=auto.
"""

from __future__ import annotations

import json

import pytest

import realmock.platform.capabilities.integrations.github.tools as tools_mod



@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


@pytest.mark.asyncio
async def test_execute_unknown_tool() -> None:
    out = json.loads(await tools_mod.execute_github_tool("nope_tool", {}))
    assert out["error"] == "unknown_github_tool"


@pytest.mark.asyncio
async def test_execute_get_user_and_list_repos() -> None:
    class _GH:
        async def get_user(self, username):
            return {"login": username}

        async def list_repos(self, username, per_page=10):
            return {"username": username, "count": 0, "repos": []}

        async def get_repo(self, o, r):
            raise AssertionError("not called")

    assert json.loads(
        await tools_mod.execute_github_tool("github_get_user", {"username": "o"}, client=_GH())  # type: ignore[arg-type]
    ) == {"login": "o"}
    assert json.loads(
        await tools_mod.execute_github_tool("github_list_repos", {"username": "o"}, client=_GH())  # type: ignore[arg-type]
    )["username"] == "o"


@pytest.mark.asyncio
async def test_execute_repo_readme_commits_pulls_issues_file_langs() -> None:
    class _GH:
        async def get_repo(self, o, r):
            return {"full_name": f"{o}/{r}"}

        async def get_readme(self, o, r):
            return {"content": "readme"}

        async def list_commits(self, o, r, per_page=10, author=None):
            return {"count": 1, "author": author}

        async def list_pull_requests(self, o, r, state="all", per_page=10):
            return {"state": state}

        async def list_issues(self, o, r, state="all", per_page=10):
            return {"state": state}

        async def get_file_content(self, o, r, path, ref=None):
            return {"path": path, "ref": ref}

        async def get_languages(self, o, r):
            return {"Python": 10}

    gh = _GH()
    assert json.loads(
        await tools_mod.execute_github_tool("github_get_repo", {"owner": "o", "repo": "r"}, client=gh)  # type: ignore[arg-type]
    )["full_name"] == "o/r"
    assert json.loads(
        await tools_mod.execute_github_tool("github_get_readme", {"owner": "o", "repo": "r"}, client=gh)  # type: ignore[arg-type]
    )["content"] == "readme"
    assert json.loads(
        await tools_mod.execute_github_tool(
            "github_list_commits", {"owner": "o", "repo": "r", "author": "bob"}, client=gh  # type: ignore[arg-type]
        )
    )["author"] == "bob"
    assert json.loads(
        await tools_mod.execute_github_tool("github_list_pulls", {"owner": "o", "repo": "r"}, client=gh)  # type: ignore[arg-type]
    )["state"] == "all"
    assert json.loads(
        await tools_mod.execute_github_tool("github_list_issues", {"owner": "o", "repo": "r"}, client=gh)  # type: ignore[arg-type]
    )["state"] == "all"
    assert json.loads(
        await tools_mod.execute_github_tool("github_get_file", {"owner": "o", "repo": "r", "path": "a.py"}, client=gh)  # type: ignore[arg-type]
    )["path"] == "a.py"
    assert json.loads(
        await tools_mod.execute_github_tool("github_get_languages", {"owner": "o", "repo": "r"}, client=gh)  # type: ignore[arg-type]
    ) == {"Python": 10}


@pytest.mark.asyncio
async def test_execute_missing_arg_and_failure() -> None:
    class _GH:
        async def get_repo(self, o, r):
            raise KeyError("repo")

        async def get_user(self, username):
            raise RuntimeError("net down")

    out = json.loads(
        await tools_mod.execute_github_tool("github_get_repo", {"owner": "o"}, client=_GH())  # type: ignore[arg-type]
    )
    assert out["error"] == "missing_argument"
    out2 = json.loads(
        await tools_mod.execute_github_tool("github_get_user", {"username": "o"}, client=_GH())  # type: ignore[arg-type]
    )
    assert out2["error"] == "execution_failed"
