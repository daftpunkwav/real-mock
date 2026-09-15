"""LLM client extension tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/llm_client_ext.py.

Covers: test_connection success/HTTP-error/generic-error branches and embed
unsafe-base guard.

Conventions: no real network (chat client faked); asyncio_mode=auto.
"""

from __future__ import annotations

import httpx
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


@pytest.mark.asyncio
async def test_llm_ext_test_connection_success() -> None:
    from realmock.platform.capabilities.ai.llm.client import llm_client_ext as mod

    class _C:
        async def chat(self, messages, temperature=0):
            assert temperature == 0
            return "ok-" + "x" * 200

    ok, reply = await mod.test_connection(_C())  # type: ignore[arg-type]
    assert ok is True
    assert reply == ("ok-" + "x" * 200)[:100]


@pytest.mark.asyncio
async def test_llm_ext_test_connection_http_error() -> None:
    from realmock.platform.capabilities.ai.llm.client import llm_client_ext as mod

    req = httpx.Request("POST", "https://example.test/v1/chat")
    resp = httpx.Response(429, text="rate limited slow down", request=req)

    class _C:
        async def chat(self, messages, temperature=0):
            raise httpx.HTTPStatusError("429", request=req, response=resp)

    ok, msg = await mod.test_connection(_C())  # type: ignore[arg-type]
    assert ok is False
    assert "HTTP 429" in msg


@pytest.mark.asyncio
async def test_llm_ext_test_connection_generic_error() -> None:
    from realmock.platform.capabilities.ai.llm.client import llm_client_ext as mod

    class _C:
        async def chat(self, messages, temperature=0):
            raise RuntimeError("conn reset")

    ok, msg = await mod.test_connection(_C())  # type: ignore[arg-type]
    assert ok is False
    assert "conn reset" in msg


@pytest.mark.asyncio
async def test_llm_ext_embed_unsafe_base_raises(monkeypatch) -> None:
    from realmock.platform.capabilities.ai.llm.client import llm_client_ext as mod
    from realmock.platform.core.security import UnsafeURLError

    monkeypatch.setattr(mod, "is_safe_http_url", lambda *a, **k: False)

    class _C:
        api_base = "http://127.0.0.1:9999/v1"
        api_key = "k"

    with pytest.raises(UnsafeURLError):
        await mod.embed(_C(), ["hi"])  # type: ignore[arg-type]
