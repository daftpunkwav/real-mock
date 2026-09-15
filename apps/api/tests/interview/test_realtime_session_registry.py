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
async def test_verify_and_database_paths(monkeypatch):
    r = WsConnectionRegistry()
    h = _conn(2)
    assert await r.verify_lease(h) is True
    monkeypatch.setattr("realmock.domains.interview.realtime.core.session_registry.get_settings", lambda: MagicMock(ws_lease_backend="database"))
    with patch("realmock.domains.interview.realtime.core.session_registry._db_lease_matches_sync", return_value=True):
        assert await r.verify_lease(h) is True
    with patch("realmock.domains.interview.realtime.core.session_registry._db_lease_matches_sync", return_value=False):
        assert await r.verify_lease(h) is False
        assert h._superseded is True
    h2 = _conn(3)
    with patch("realmock.domains.interview.realtime.core.session_registry._persist_lease_sync", return_value=None):
        await r.claim(h2)
    with patch("realmock.domains.interview.realtime.core.session_registry._release_lease_sync", return_value=None):
        await r.release(h2)
    reset_session_registry_for_tests()
    assert active_handlers_for_tests() == {}


@pytest.mark.asyncio
async def test_sync_persist_release_match():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    cm = MagicMock()
    cm.__enter__.return_value = db
    cm.__exit__.return_value = False
    with patch("realmock.domains.interview.realtime.core.session_registry.sessions_db_session", return_value=cm):
        _persist_lease_sync(1, "tok")
        assert db.add.called
        row = MagicMock(lease_token="tok")
        db.query.return_value.filter.return_value.first.return_value = row
        assert _db_lease_matches_sync(1, "tok") is True
        assert _db_lease_matches_sync(1, "other") is False
        db2 = MagicMock()
        db2.query.return_value.filter.return_value.filter.return_value.first.return_value = row
        cm2 = MagicMock()
        cm2.__enter__.return_value = db2
        cm2.__exit__.return_value = False
        with patch("realmock.domains.interview.realtime.core.session_registry.sessions_db_session", return_value=cm2):
            _release_lease_sync(1, "tok")
            assert db2.delete.called


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

