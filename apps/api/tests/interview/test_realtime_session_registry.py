"""Session registry tests for realtime/core/session_registry.py.

Covers: lease token, memory claim/release, verify lease DB paths,
sync persist/release/match, exception wrappers, supersede.
Conventions: no real network/LLM (all external calls mocked); uses _conn helper for fake connections.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from realmock.domains.interview.realtime.core.session_registry import (
    WsConnectionRegistry,
    _db_lease_matches_sync,
    _lease_token,
    _persist_lease_sync,
    _release_lease_sync,
    active_handlers_for_tests,
    reset_session_registry_for_tests,
)

def _conn(sid=7, token="t1"):
    """Build a minimal fake connection exposing send/ws/lease fields."""
    m = MagicMock(session_id=sid, _superseded=False, lease_token=token)
    m.send = AsyncMock()
    m.ws = MagicMock(close=AsyncMock())
    return m

@pytest.mark.asyncio
async def test_lease_token_and_memory_claim_release():
    reset_session_registry_for_tests()
    assert _lease_token(MagicMock(lease_token="abc")) == "abc"
    assert _lease_token(MagicMock(spec=[])) != ""
    r = WsConnectionRegistry()
    a = _conn(1)
    b = _conn(1, token="t2")
    await r.claim(a)
    assert r.snapshot_for_tests()[1] is a
    await r.claim(b)
    assert a._superseded is True and r.snapshot_for_tests()[1] is b
    a.ws.close.assert_awaited_once()
    await r.release(a)
    assert r.snapshot_for_tests()[1] is b
    await r.release(b)
    assert 1 not in r.snapshot_for_tests()
    r.clear_for_tests()


@pytest.mark.asyncio
async def test_verify_lease_memory_backend_short_circuits():
    r = WsConnectionRegistry()
    h = _conn(2)
    # Memory backend (default): lease is always valid, handler untouched.
    assert await r.verify_lease(h) is True
    assert h._superseded is False
    reset_session_registry_for_tests()
    assert active_handlers_for_tests() == {}


@pytest.mark.asyncio
async def test_database_backend_lease_roundtrip(monkeypatch, db):
    """ws_lease_backend=database lifecycle through the public registry API.

    Drives claim → verify → reclaim-by-other-window → verify → release against
    the real sqlite sessions DB, so inlining the private *_sync helpers into
    the registry methods cannot silently bypass these tests.
    """
    import realmock.domains.interview.models  # noqa: F401 — register WsSessionLease
    from realmock.domains.interview.models import WsSessionLease
    from realmock.platform.config import get_settings

    monkeypatch.setenv("WS_LEASE_BACKEND", "database")
    get_settings.cache_clear()
    try:
        r = WsConnectionRegistry()
        h = _conn(42, token="tok-42")

        await r.claim(h)
        row = db.query(WsSessionLease).filter(WsSessionLease.session_id == 42).first()
        assert row is not None and row.lease_token == "tok-42"
        assert await r.verify_lease(h) is True
        assert h._superseded is False

        # Another window reclaimed the lease: verification must fail and mark
        # this handler superseded.
        row.lease_token = "tok-other"
        db.commit()
        assert await r.verify_lease(h) is False
        assert h._superseded is True

        # Releasing with the stale token must NOT delete the newer lease...
        await r.release(h)
        db.expire_all()
        row2 = db.query(WsSessionLease).filter(WsSessionLease.session_id == 42).first()
        assert row2 is not None and row2.lease_token == "tok-other"

        # ...while the current leaseholder's release does remove the row, and
        # verification of a leaseless session reports False.
        h2 = _conn(42, token="tok-other")
        await r.release(h2)
        db.expire_all()
        assert (
            db.query(WsSessionLease).filter(WsSessionLease.session_id == 42).first() is None
        )
        assert await r.verify_lease(h2) is False
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_sync_exceptions_and_wrappers():
    from realmock.domains.interview.realtime.core import session_registry as reg
    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")
    cm = MagicMock()
    cm.__enter__.return_value = db
    cm.__exit__.return_value = False
    with patch.object(reg, "sessions_db_session", return_value=cm):
        _persist_lease_sync(1, "t")
        _release_lease_sync(1, "t")
        assert _db_lease_matches_sync(1, "t") is False
    h = _conn(9)
    h.send = AsyncMock(side_effect=RuntimeError("send fail"))
    h.ws.close = AsyncMock(side_effect=RuntimeError("close fail"))
    await reg.get_ws_connection_registry()._supersede_old(h, 9)
    reset_session_registry_for_tests()
    await reg.claim_session_connection(h)
    assert await reg.verify_connection_lease(h) is True
    await reg.release_session_connection(h)

