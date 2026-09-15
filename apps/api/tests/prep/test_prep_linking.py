"""Linking tests for realmock.domains.prep.services.linking.

Covers: format_linked_session edges and format_linked_sessions capping/skipping
Conventions: Temp DB only; corrupt payloads return empty string; rate limits reset per test
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

def test_format_linked_session_edges(db) -> None:
    from realmock.domains.prep.services.linking import format_linked_session

    assert format_linked_session(db, None) == ""
    assert format_linked_session(db, 999999999) == ""
    bad = PrepSession(
        access_token=new_access_token(), status="active", messages="not-json{{{",
    )
    db.add(bad)
    db.commit()
    db.refresh(bad)
    assert format_linked_session(db, bad.id) == ""
    nonlist = PrepSession(
        access_token=new_access_token(), status="active", messages='{"a": 1}',
    )
    db.add(nonlist)
    db.commit()
    db.refresh(nonlist)
    assert format_linked_session(db, nonlist.id) == ""
    empty_turns = PrepSession(
        access_token=new_access_token(), status="active",
        messages=json.dumps([{"role": "system", "content": "sys"}]),
        target_role="Backend", target_company="Acme",
    )
    db.add(empty_turns)
    db.commit()
    db.refresh(empty_turns)
    out = format_linked_session(db, empty_turns.id)
    assert "no conversation yet" in out

def test_format_linked_session_generic_error(monkeypatch, db) -> None:
    from realmock.domains.prep.services import linking as linking_mod

    row = PrepSession(access_token=new_access_token(), status="active", messages="[]")
    db.add(row)
    db.commit()
    db.refresh(row)

    class _BoomDB:
        def get(self, *args, **kwargs):
            raise RuntimeError("db-down")

    assert linking_mod.format_linked_session(_BoomDB(), row.id) == ""  # type: ignore[arg-type]

def test_format_linked_sessions_skips_and_caps(db) -> None:
    from realmock.domains.prep.services.linking import format_linked_sessions

    ids: list[int] = []
    for i in range(7):
        row = PrepSession(
            access_token=new_access_token(), status="active",
            messages=json.dumps([{"role": "user", "content": f"turn-{i}"}]),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        ids.append(row.id)
    out = format_linked_sessions(db, ["bad", None, -1, 0, *ids], exclude_id=None)  # type: ignore[list-item]
    # Capped at five sessions.
    assert out.count("Linked session #") == 5
    assert format_linked_sessions(db, [], exclude_id=None) == ""
