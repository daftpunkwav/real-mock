"""GitHub user REST-op tests for apps/api/src/realmock/platform/capabilities/integrations/github/rest_ops_user.py.

Covers: _get_user success/error mapping and _list_repos success/error/unexpected
branches with per_page clamping.

Conventions: no real network (client._get faked); asyncio_mode=auto.
"""

from __future__ import annotations

import pytest

import realmock.platform.capabilities.integrations.github.rest_ops_user as user_mod



@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.calls: list = []

    async def _get(self, path, params=None):
        self.calls.append({"path": path, "params": params})
        resp = self._response
        if callable(resp):
            return resp(path, params)
        return resp


@pytest.mark.asyncio
async def test_get_user_success_and_error() -> None:
    err = {"error": "not_found"}
    assert await user_mod._get_user(_FakeClient(err), "octo") == err
    payload = {
        "login": "octo",
        "name": "O",
        "bio": "b",
        "public_repos": 3,
        "followers": 5,
        "following": 1,
        "company": "c",
        "blog": "blog",
        "location": "loc",
        "created_at": "2020",
        "html_url": "https://github.com/octo",
    }
    out = await user_mod._get_user(_FakeClient(payload), "octo")
    assert out["login"] == "octo"
    assert out["followers"] == 5


@pytest.mark.asyncio
async def test_list_repos_success_error_and_unexpected() -> None:
    err = {"error": "rate_limited"}
    assert await user_mod._list_repos(_FakeClient(err), "octo") == err
    assert await user_mod._list_repos(_FakeClient({"a": 1}), "octo") == {
        "error": "unexpected_response",
        "raw_type": "dict",
    }
    payload = [
        {
            "name": "r",
            "full_name": "octo/r",
            "description": "d",
            "language": "Python",
            "stargazers_count": 2,
            "forks_count": 1,
            "open_issues_count": 0,
            "updated_at": "2021",
            "html_url": "https://github.com/octo/r",
            "topics": None,
            "default_branch": "main",
        }
    ]
    client = _FakeClient(payload)
    out = await user_mod._list_repos(client, "octo", per_page=100)
    assert out["count"] == 1
    assert out["repos"][0]["topics"] == []
    # Clamped to 30.
    assert client.calls[0]["params"]["per_page"] == 30
