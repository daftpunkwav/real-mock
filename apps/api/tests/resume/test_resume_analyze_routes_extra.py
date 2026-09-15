"""Analyze routes extra tests for src/realmock/domains/resume/routes/analyze.py.

Covers: _error_event shape, analyze_resume missing-row 404 branch,
analyze_resume_stream LLM-error path (store/slot/LLM mocked).
Conventions: no real network/model downloads (all clients mocked); DB/store mocked;
rate limits reset per test.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def test_analyze_error_event_shape() -> None:
    import realmock.domains.resume.routes.analyze as mod

    exc = RuntimeError("boom")
    evt = mod._error_event(exc)
    assert evt["type"] == "error"


@pytest.mark.asyncio
async def test_analyze_missing_row_is_404(db) -> None:
    import realmock.domains.resume.routes.analyze as mod

    req = MagicMock()
    req.body = AsyncMock(return_value=b"{}")
    with patch.object(mod.store, "get_row", return_value=None):
        with patch.object(mod, "raise_error", side_effect=RuntimeError("A1005")):
            try:
                await mod.analyze_resume(999999, req, db)
                assert False
            except RuntimeError:
                pass


@pytest.mark.asyncio
async def test_analyze_stream_error_path(db, monkeypatch) -> None:
    import realmock.domains.resume.routes.analyze as mod

    row = MagicMock()
    monkeypatch.setattr(mod.store, "get_row", lambda db_arg, rid: row)

    class _Req:
        async def body(self):
            return b"{}"

        async def is_disconnected(self):
            return False

    async def _boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(mod, "analyze_resume_with_llm", _boom)
    monkeypatch.setattr(mod.analyze_slots, "acquire_slot", AsyncMock())
    monkeypatch.setattr(mod.analyze_slots, "release_slot", AsyncMock())
    resp = await mod.analyze_resume_stream(1, _Req(), db)  # type: ignore[arg-type]
    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk)
        if len(chunks) > 20:
            break
    assert chunks
    await asyncio.sleep(0)
