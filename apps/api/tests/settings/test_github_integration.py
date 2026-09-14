"""GitHub integration settings + rate-limit hardening (no real network)."""

from __future__ import annotations

import asyncio
import json

import pytest

from realmock.domains.settings.services import github_integration as gh_settings
from realmock.domains.settings.services.github_integration import (
    clear_github_token,
    get_github_status,
    save_github_token,
)
from realmock.platform.capabilities.integrations.github import github_http
from realmock.platform.capabilities.integrations.github.client import GitHubClient
from realmock.platform.capabilities.integrations.github.token_store import (
    has_stored_token,
    read_stored_token,
)
from realmock.platform.core.errors import ApiBusinessError


class _FakeResp:
    def __init__(self, status=200, payload=None, headers=None, text=""):
        self.status_code = status
        self.headers = headers or {}
        body = json.dumps(payload) if payload is not None else text
        self.content = body.encode() if isinstance(body, str) else b""
        self._text = text if payload is None else body

    def json(self):
        return json.loads(self.content.decode() or "null")

    @property
    def text(self):
        return self._text


class _FakeHttp:
    """Fake httpx.AsyncClient recording requests and replaying responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, headers=None, params=None):
        self.calls.append({"url": url, "headers": dict(headers or {})})
        resp = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        return resp


def _patch_http(monkeypatch, responses):
    fake = _FakeHttp(responses)
    monkeypatch.setattr(
        "realmock.platform.capabilities.integrations.github.client.httpx.AsyncClient",
        lambda **kwargs: fake,
    )
    return fake


# ── Credential store ─────────────────────────────────────────────────────────


def test_save_status_clear_round_trip(api_db) -> None:
    assert get_github_status(api_db) == {"configured": False, "tail": ""}
    assert not has_stored_token(db=api_db)
    saved = save_github_token(api_db, "github_pat_abc123XYZ")
    assert saved == {"configured": True, "tail": "…3XYZ"}
    assert has_stored_token(db=api_db)
    assert read_stored_token(db=api_db) == "github_pat_abc123XYZ"
    cleared = clear_github_token(api_db)
    assert cleared == {"configured": False, "tail": ""}
    assert not has_stored_token(db=api_db)


def test_save_rejects_garbage(api_db) -> None:
    for bad in ["", "   ", "not-a-token", "Bearer xyz", "x" * 501]:
        with pytest.raises(ApiBusinessError):
            save_github_token(api_db, bad)
    assert not has_stored_token(db=api_db)


def test_client_prefers_stored_over_env(api_db, monkeypatch) -> None:
    save_github_token(api_db, "github_pat_stored1")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_envtoken")
    client = GitHubClient()
    assert client.token == "github_pat_stored1"
    assert client._headers["Authorization"] == "Bearer github_pat_stored1"
    explicit = GitHubClient(token="ghp_direct")
    assert explicit.token == "ghp_direct"


# ── Rate-limit mapping + bounded retry ───────────────────────────────────────


@pytest.mark.asyncio
async def test_429_retries_once_then_reports(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    limited = _FakeResp(
        status=429,
        text="API rate limit exceeded",
        headers={"retry-after": "2", "x-ratelimit-remaining": "0"},
    )
    ok = _FakeResp(status=200, payload={"login": "octocat"})
    fake = _patch_http(monkeypatch, [limited, ok])
    data = await GitHubClient(token="t").get_user("octocat")
    assert data["login"] == "octocat"
    assert sleeps == [2]
    assert len(fake.calls) == 2
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer t"


@pytest.mark.asyncio
async def test_429_long_wait_degrades_without_sleeping(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    limited = _FakeResp(
        status=429, text="slow down", headers={"retry-after": "120"}
    )
    _patch_http(monkeypatch, [limited])
    data = await GitHubClient(token="t").get_user("octocat")
    assert data["error"] == "rate_limited"
    assert data["status"] == 429
    assert sleeps == [], "waits beyond the turn budget must not sleep"


@pytest.mark.asyncio
async def test_403_permission_stays_forbidden(monkeypatch) -> None:
    denied = _FakeResp(status=403, text="Resource not accessible by integration")
    _patch_http(monkeypatch, [denied])
    data = await GitHubClient(token="t").get_user("octocat")
    assert data["error"] == "forbidden_or_rate_limited"


@pytest.mark.asyncio
async def test_quota_headers_are_recorded(monkeypatch) -> None:
    ok = _FakeResp(
        status=200,
        payload={"login": "octocat"},
        headers={"x-ratelimit-limit": "5000", "x-ratelimit-remaining": "4999"},
    )
    _patch_http(monkeypatch, [ok])
    await GitHubClient(token="t").get_user("octocat")
    assert github_http.get_last_quota()["remaining"] == 4999


# ── Connectivity test ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_github_probe_reports_quota(monkeypatch, api_db) -> None:
    payload = {"resources": {"core": {"limit": 5000, "remaining": 4990, "reset": 9999999999}}}
    _patch_http(monkeypatch, [_FakeResp(status=200, payload=payload)])
    out = await gh_settings.test_github_token(api_db, candidate="github_pat_probe1")
    assert out["ok"] is True
    assert out["remaining"] == 4990
    assert out["authenticated"] is True


@pytest.mark.asyncio
async def test_github_probe_failure_is_structured(monkeypatch, api_db) -> None:
    _patch_http(monkeypatch, [_FakeResp(status=401, text="Bad credentials")])
    out = await gh_settings.test_github_token(api_db, candidate="ghp_wrong")
    assert out["ok"] is False
    assert out["status"] == 401
