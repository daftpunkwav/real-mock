"""Analyze routes extra tests for src/realmock/domains/resume/routes/analyze.py.

Covers: _error_event shape, analyze_resume missing-row 404 branch,
analyze_resume_stream LLM-error path (store/slot/LLM mocked).
Conventions: no real network/model downloads (all clients mocked); DB/store mocked;
rate limits reset per test.
"""

from __future__ import annotations

import asyncio
import json
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
    """A missing resume row is the A1005 / 404 contract, not a generic failure."""
    import realmock.domains.resume.routes.analyze as mod
    from realmock.platform.core.errors import ApiBusinessError

    req = MagicMock()
    req.body = AsyncMock(return_value=b"{}")
    with patch.object(mod.store, "get_row", return_value=None):
        with pytest.raises(ApiBusinessError) as exc:
            await mod.analyze_resume(999999, req, db)
    assert exc.value.error_code == "A1005"
    assert exc.value.status_code == 404


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


@pytest.mark.asyncio
async def test_analyze_stream_error_masks_embedded_credential(db, monkeypatch, caplog) -> None:
    """The SSE message is generic copy, and the log line must not carry the key."""
    import logging

    import realmock.domains.resume.routes.analyze as mod

    row = MagicMock()
    monkeypatch.setattr(mod.store, "get_row", lambda db_arg, rid: row)

    class _Req:
        async def body(self):
            return b"{}"

        async def is_disconnected(self):
            return False

    calls = 0

    async def _boom(*a, **k):
        nonlocal calls
        calls += 1
        raise RuntimeError("evaluator 401: Incorrect API key provided: sk-proj-abcdefghij123456789")

    monkeypatch.setattr(mod, "analyze_resume_with_llm", _boom)
    monkeypatch.setattr(mod.analyze_slots, "acquire_slot", AsyncMock())
    monkeypatch.setattr(mod.analyze_slots, "release_slot", AsyncMock())
    with caplog.at_level(logging.ERROR):
        resp = await mod.analyze_resume_stream(1, _Req(), db)  # type: ignore[arg-type]
        chunks = []
        async for chunk in resp.body_iterator:
            chunks.append(chunk)
            if len(chunks) > 20:
                break
    assert chunks
    # The mocked analyzer must actually have run and raised, or this test
    # would pass on a stream that never reached the error path.
    assert calls == 1
    events = []
    for chunk in chunks:
        for line in str(chunk).splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert any(e.get("type") == "error" for e in events)
    assert "sk-proj-abcdefghij123456789" not in caplog.text
    # The failure must actually be logged, with the sanitized detail.
    errors = [
        r
        for r in caplog.records
        if r.levelname == "ERROR" and "Resume analyze stream failed" in r.getMessage()
    ]
    assert errors, "the stream failure must be logged"
    # The traceback stays attached for diagnosis; the configured pipeline
    # (RedactFilter + SafeFormatter) is what scrubs the rendered text.
    from realmock.platform.core.logging import SafeFormatter

    formatter = SafeFormatter()
    for record in errors:
        assert "sk-proj-abcdefghij123456789" not in formatter.format(record)
