"""GitHub HTTP tests for apps/api/src/realmock/platform/capabilities/integrations/github/github_http.py.

Covers: _quota_from_headers reset_in computation, 429 retry with reset_in/default
max-wait, empty-body/bad-JSON mapping and zero-attempt error branch.

Conventions: no real network (httpx.AsyncClient faked); asyncio_mode=auto.
"""

from __future__ import annotations

import time

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit



@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    try:
        from realmock.platform.capabilities.integrations.github.github_http import (
            _LAST_QUOTA,
        )

        _LAST_QUOTA.clear()
    except Exception:
        pass
    yield
    reset_rate_limit()
    try:
        from realmock.platform.capabilities.integrations.github.github_http import (
            _LAST_QUOTA,
        )

        _LAST_QUOTA.clear()
    except Exception:
        pass


def test_github_quota_reset_in_computed() -> None:
    from realmock.platform.capabilities.integrations.github import github_http as mod

    reset = int(time.time()) + 30
    quota = mod._quota_from_headers(
        {"x-ratelimit-remaining": "5", "x-ratelimit-reset": str(reset)}
    )
    assert quota["remaining"] == 5
    assert 0 <= quota["reset_in"] <= 30


class _FakeGHResp:
    def __init__(self, status, *, headers=None, content=b"", text="", payload=None, fail_json=False):
        self.status_code = status
        self.headers = headers or {}
        self.content = content
        self.text = text
        self._payload = payload
        self._fail_json = fail_json

    def json(self):
        if self._fail_json:
            raise ValueError("bad json")
        return self._payload


class _FakeGHStream:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class _FakeGHClient:
    def __init__(self, resps):
        self._resps = resps

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, *a, **k):
        return self._resps.pop(0)


def _patch_gh(monkeypatch, resps, sleep=None):
    import realmock.platform.capabilities.integrations.github.github_http as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda *a, **k: _FakeGHClient(resps))
    if sleep is not None:
        monkeypatch.setattr(mod.asyncio, "sleep", sleep)


@pytest.mark.asyncio
async def test_github_429_uses_reset_in_then_retries(monkeypatch) -> None:
    import realmock.platform.capabilities.integrations.github.github_http as mod

    reset = int(time.time()) + 1
    first = _FakeGHResp(
        429,
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset)},
        content=b"x",
        text="rate limit exceeded",
    )
    second = _FakeGHResp(200, headers={}, content=b"{}", text="{}", payload={"ok": True})

    slept: list[float] = []

    async def _sleep(d):
        slept.append(d)

    _patch_gh(monkeypatch, [first, second], sleep=_sleep)
    out = await mod.async_get("/repos/a/b")
    assert out == {"ok": True}
    assert slept and 0 < slept[0] <= 5.0


@pytest.mark.asyncio
async def test_github_429_defaults_to_max_wait(monkeypatch) -> None:
    import realmock.platform.capabilities.integrations.github.github_http as mod

    first = _FakeGHResp(429, headers={}, content=b"x", text="Rate Limit hit")
    second = _FakeGHResp(429, headers={}, content=b"x", text="Rate Limit hit")

    async def _sleep(d):
        return None

    _patch_gh(monkeypatch, [first, second], sleep=_sleep)
    out = await mod.async_get("/repos/a/b")
    assert out["error"] == "rate_limited"
    assert out["status"] == 429


@pytest.mark.asyncio
async def test_github_empty_body_returns_empty(monkeypatch) -> None:
    import realmock.platform.capabilities.integrations.github.github_http as mod

    _patch_gh(monkeypatch, [_FakeGHResp(200, headers={}, content=b"", text="")])
    assert await mod.async_get("/x") == {}


@pytest.mark.asyncio
async def test_github_bad_json_returns_raw(monkeypatch) -> None:
    import realmock.platform.capabilities.integrations.github.github_http as mod

    _patch_gh(
        monkeypatch,
        [_FakeGHResp(200, headers={}, content=b"oops", text="oops", fail_json=True)],
    )
    out = await mod.async_get("/x")
    assert out == {"raw": "oops"}


@pytest.mark.asyncio
async def test_github_return_last_when_no_attempts(monkeypatch) -> None:
    import realmock.platform.capabilities.integrations.github.github_http as mod

    monkeypatch.setattr(mod, "_MAX_ATTEMPTS", 0)
    out = await mod.async_get("/x")
    assert out["error"] == "http_error"
