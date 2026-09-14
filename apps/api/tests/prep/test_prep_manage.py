"""Prep session management routes: delete, archive, link (no network, no LLM)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.prep.models import PrepSession
from realmock.platform.core.session_auth import new_access_token


def _session(db, **kwargs) -> PrepSession:
    kwargs.setdefault("status", "active")
    kwargs.setdefault("messages", "[]")
    kwargs.setdefault("access_token", new_access_token())
    session = PrepSession(**kwargs)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _headers(session: PrepSession) -> dict[str, str]:
    return {"X-Interview-Token": session.access_token}


_CSRF = {"Origin": "http://localhost:8080"}


def _mgmt_headers(session: PrepSession | None = None) -> dict[str, str]:
    h = dict(_CSRF)
    if session is not None:
        h["X-Interview-Token"] = session.access_token
    return h


def test_delete_session_removes_row(db) -> None:
    session = _session(db)
    sid = session.id
    with TestClient(app) as client:
        resp = client.delete(
            f"/api/v1/prep/sessions/{sid}", headers=_mgmt_headers(session)
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": sid}
    db.expire_all()
    assert db.get(PrepSession, sid) is None


def test_delete_orphan_without_token_succeeds(db) -> None:
    """Regression: lost-cookie / empty-token sessions must stay deletable (A0401 dead-lock)."""
    session = _session(
        db,
        access_token="",
        messages=json.dumps([{"role": "user", "content": "orphan with content"}]),
    )
    sid = session.id
    with TestClient(app) as client:
        # No token at all, only same-origin CSRF header.
        resp = client.delete(f"/api/v1/prep/sessions/{sid}", headers=dict(_CSRF))
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.get(PrepSession, sid) is None


def test_delete_requires_csrf(db) -> None:
    session = _session(db)
    with TestClient(app) as client:
        denied = client.delete(f"/api/v1/prep/sessions/{session.id}")
    assert denied.status_code == 403


def test_archive_and_restore_toggle_status(db) -> None:
    session = _session(db)
    with TestClient(app) as client:
        archived = client.patch(
            f"/api/v1/prep/sessions/{session.id}/archive",
            json={"archived": True},
            headers=_mgmt_headers(session),
        )
        assert archived.json()["status"] == "archived"
        restored = client.patch(
            f"/api/v1/prep/sessions/{session.id}/archive",
            json={"archived": False},
            headers=_mgmt_headers(session),
        )
        assert restored.json()["status"] == "active"


def test_archive_orphan_without_token_succeeds(db) -> None:
    session = _session(db, access_token="")
    with TestClient(app) as client:
        resp = client.patch(
            f"/api/v1/prep/sessions/{session.id}/archive",
            json={"archived": True},
            headers=dict(_CSRF),
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "archived"


def test_link_rejects_self_and_missing_target(db) -> None:
    session = _session(db)
    with TestClient(app) as client:
        self_link = client.put(
            f"/api/v1/prep/sessions/{session.id}/link",
            json={"linked_session_id": session.id},
            headers=_mgmt_headers(session),
        )
        assert self_link.status_code == 422
        missing = client.put(
            f"/api/v1/prep/sessions/{session.id}/link",
            json={"linked_session_id": 999999999},
            headers=_mgmt_headers(session),
        )
        assert missing.status_code == 404


def test_link_injects_block_and_unlink_removes_it(db) -> None:
    linked = _session(
        db,
        target_role="Backend",
        messages=json.dumps([
            {"role": "user", "content": "How do I explain Raft?"},
            {"role": "assistant", "content": "Start with leader election."},
        ]),
    )
    session = _session(
        db,
        messages=json.dumps([{"role": "system", "content": "sys"}]),
    )
    with TestClient(app) as client:
        resp = client.put(
            f"/api/v1/prep/sessions/{session.id}/link",
            json={"linked_session_id": linked.id},
            headers=_mgmt_headers(session),
        )
        assert resp.json() == {"id": session.id, "linked_session_id": linked.id}
    db.expire_all()
    messages = json.loads(db.get(PrepSession, session.id).messages)
    assert messages[0]["content"] == "sys", "original system message untouched"
    assert messages[1]["content"].startswith("[Linked session context]")
    assert "How do I explain Raft?" in messages[1]["content"]

    with TestClient(app) as client:
        resp = client.put(
            f"/api/v1/prep/sessions/{session.id}/link",
            json={"linked_session_id": None},
            headers=_mgmt_headers(session),
        )
        assert resp.json()["linked_session_id"] is None
    db.expire_all()
    messages = json.loads(db.get(PrepSession, session.id).messages)
    assert all("[Linked session context]" not in str(m.get("content") or "") for m in messages)


def test_linked_session_visible_in_summary_list(db) -> None:
    linked = _session(db)
    session = _session(db)
    with TestClient(app) as client:
        client.put(
            f"/api/v1/prep/sessions/{session.id}/link",
            json={"linked_session_id": linked.id},
            headers=_mgmt_headers(session),
        )
        listed = client.get("/api/v1/prep/sessions")
    row = next(s for s in listed.json() if s["id"] == session.id)
    assert row["linked_session_id"] == linked.id


def test_purge_empty_deletes_only_contentless(db) -> None:
    empty = _session(db)
    empty_id = empty.id
    full = _session(
        db,
        messages=json.dumps([{"role": "user", "content": "hello"}]),
    )
    full_id = full.id
    with TestClient(app) as client:
        denied = client.post("/api/v1/prep/sessions/purge-empty")
        assert denied.status_code == 403
        resp = client.post(
            "/api/v1/prep/sessions/purge-empty",
            headers={"Origin": "http://localhost:8080"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] >= 1
    db.expire_all()
    assert db.get(PrepSession, empty_id) is None
    assert db.get(PrepSession, full_id) is not None


def test_purge_all_deletes_everything_without_token(db) -> None:
    empty = _session(db)
    full = _session(
        db,
        messages=json.dumps([{"role": "user", "content": "hello"}]),
    )
    ids = {empty.id, full.id}
    with TestClient(app) as client:
        denied = client.post("/api/v1/prep/sessions/purge-all")
        assert denied.status_code == 403
        resp = client.post(
            "/api/v1/prep/sessions/purge-all",
            headers={"Origin": "http://localhost:8080"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] >= 2
    db.expire_all()
    for sid in ids:
        assert db.get(PrepSession, sid) is None
