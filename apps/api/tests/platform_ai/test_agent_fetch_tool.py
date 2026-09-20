"""Fetch tool tests for apps/api/src/realmock/platform/capabilities/ai/agent/tools/fetch.py.

Covers: _strip_html unclosed-script truncation, _header_charset variants,
_fetch_page empty-text unavailable branch, UnsafeURL blocking and tool-spec delegation.

Conventions: no real network (pinned client/fetch faked via monkeypatch); asyncio_mode=auto.
"""

from __future__ import annotations

import json

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


def test_fetch_shadow_truncates_unclosed_script() -> None:
    from realmock.platform.capabilities.ai.agent.tools.fetch import _strip_html

    text = _strip_html("hello <script>var x=1;")
    assert text == "hello"


def test_fetch_header_charset_none() -> None:
    from realmock.platform.capabilities.ai.agent.tools.fetch import _header_charset

    assert _header_charset(None) is None
    assert _header_charset("text/html") is None
    assert _header_charset("text/html; charset=utf-8") == "utf-8"


@pytest.mark.asyncio
async def test_fetch_empty_text_is_unavailable(monkeypatch) -> None:
    from realmock.platform.capabilities.ai.agent.tools import fetch as mod

    class _Resp:
        status_code = 200
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield b"<script>var x=1;</script>"

    class _Stream:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, *exc):
            return False

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, *a, **k):
            return _Stream()

    async def _pinned(*a, **k):
        return _Client()

    monkeypatch.setattr(mod.asyncio, "to_thread", lambda f, *a, **k: f(*a, **k))
    monkeypatch.setattr(mod, "make_pinned_async_client", _pinned)
    out = await mod._fetch_page("https://example.test/x", 6000)
    assert "FETCH_FAILED" in out
    assert "no readable text" in out


@pytest.mark.asyncio
async def test_fetch_unsafe_url_blocked(monkeypatch) -> None:
    from realmock.platform.capabilities.ai.agent.tools import fetch as mod
    from realmock.platform.core.security.url import UnsafeURLError

    async def _boom(url, max_chars):
        raise UnsafeURLError("blocked")

    monkeypatch.setattr(mod, "_fetch_page", _boom)
    out = await mod.execute_web_fetch({"url": "https://example.test/x"})
    assert "FETCH_FAILED" in out
    assert "blocked by policy" in out


@pytest.mark.asyncio
async def test_fetch_loopback_blocked(monkeypatch) -> None:
    """Model-supplied loopback URLs never reach the wire (no local-endpoint drive-by)."""
    from realmock.platform.capabilities.ai.agent.tools import fetch as mod

    monkeypatch.setattr(mod.asyncio, "to_thread", lambda f, *a, **k: f(*a, **k))
    out = await mod.execute_web_fetch({"url": "http://127.0.0.1/"})
    assert "FETCH_FAILED" in out
    assert "blocked by policy" in out


@pytest.mark.asyncio
async def test_fetch_tool_handler_delegates() -> None:
    from realmock.platform.capabilities.ai.agent.tools.fetch import web_fetch_tool_spec

    spec = web_fetch_tool_spec()
    out = await spec.handler({})
    assert json.loads(out)["error"] == "empty_url"
