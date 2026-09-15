"""Session-notes tests for realmock.domains.prep.services.session_notes.

Covers: note_rating_into_session missing, rated/unrated, corrupt and rollback branches
Conventions: Temp DB fixture; never raises on corrupt data; rate limits reset per test
"""
from __future__ import annotations
import json
import pytest
from realmock.domains.prep.models import PrepSession
from realmock.platform.core.session_auth import new_access_token

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def _session(db, **kwargs) -> PrepSession:
    kwargs.setdefault("status", "active")
    kwargs.setdefault("messages", "[]")
    kwargs.setdefault("access_token", new_access_token())
    row = PrepSession(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def test_note_rating_into_session_edges(db) -> None:
    from realmock.domains.prep.services.session_notes import note_rating_into_session

    # Missing row is ignored, never raises.
    note_rating_into_session(db, 999999, 1, 8)

    row = _session(db)
    note_rating_into_session(db, row.id, 42, 9)
    db.expire_all()
    stored = json.loads(db.get(PrepSession, row.id).messages)
    assert any("9/10" in str(m) for m in stored)

    row2 = _session(db)
    note_rating_into_session(db, row2.id, 7, None)
    db.expire_all()
    stored2 = json.loads(db.get(PrepSession, row2.id).messages)
    assert any("unrated" in str(m) for m in stored2)

    # Corrupt JSON and non-list stores are ignored.
    corrupt = _session(db, messages="not-json{")
    note_rating_into_session(db, corrupt.id, 1, 5)
    nonlist = _session(db, messages='{"a": 1}')
    note_rating_into_session(db, nonlist.id, 1, 5)

    # DB failure rolls back and never raises.
    class _BoomDB:
        def get(self, *args, **kwargs):
            raise RuntimeError("boom")

        def rollback(self) -> None:
            pass

    note_rating_into_session(_BoomDB(), 1, 1, 5)  # type: ignore[arg-type]
