"""Prep session list API: summary fields and ordering needed for resume-grouped display."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import event

from realmock.asgi import app
from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.routes.lists import list_prep_sessions
from realmock.platform.models import Resume


@contextmanager
def _captured_statements(db) -> Iterator[list[str]]:
    """Collect the SQL statements issued on the session's engine inside the block."""
    engine = db.get_bind()
    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
        seen.append(" ".join(statement.split()))

    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", _record)


def _seed(db, rows: list[PrepSession], resume: Resume | None = None) -> None:
    if resume is not None:
        db.add(resume)
    db.add_all(rows)
    db.commit()


def test_list_prep_sessions_groups_by_resume(db, api_db) -> None:
    resume = Resume(filename="Resume_TwoPage.pdf", file_type="pdf")
    api_db.add(resume)
    api_db.commit()
    api_db.refresh(resume)
    older = PrepSession(
        resume_id=None,
        messages=json.dumps(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "Help me analyze the resume's strengths"},
                {"role": "assistant", "content": "Okay"},
            ],
            ensure_ascii=False,
        ),
        token_usage=100,
    )
    newer = PrepSession(
        resume_id=resume.id,  # Use the actual auto-incremented id; do not assume it starts at 1
        messages=json.dumps(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "Generate MCP practice questions"},
                {"role": "assistant", "content": "Good", "steps": [{"name": "quiz", "query": "q"}]},
                {"role": "user", "content": "Give me another question"},
            ],
            ensure_ascii=False,
        ),
        token_usage=55,
    )
    _seed(db, [older, newer])

    with TestClient(app) as client:
        res = client.get("/api/v1/prep/sessions")
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list) and len(items) >= 2

    by_id = {i["id"]: i for i in items}
    n = by_id[newer.id]
    assert n["resume_filename"] == "Resume_TwoPage.pdf"
    assert n["summary"] == "Generate MCP practice questions"
    assert n["message_count"] == 3  # system is not counted
    assert n["token_usage"] == 55
    assert "access_token" not in n and "messages" not in n

    o = by_id[older.id]
    assert o["resume_id"] is None and o["resume_filename"] is None
    assert o["summary"] == "Help me analyze the resume's strengths"

    # Sorting only needs to be stable when updated_at values are close, but a newly inserted session must not be missing from the list.
    ids = [i["id"] for i in items]
    assert newer.id in ids and older.id in ids


def test_list_prep_sessions_orders_by_recent_activity(db) -> None:
    old = PrepSession(resume_id=None, messages="[]")
    db.add(old)
    db.commit()
    # Simulate earlier activity: move updated_at backward
    old.updated_at = old.created_at.replace(year=2020)
    db.commit()
    new = PrepSession(resume_id=None, messages="[]")
    db.add(new)
    db.commit()

    with TestClient(app) as client:
        items = client.get("/api/v1/prep/sessions").json()
    ids = [i["id"] for i in items]
    assert ids.index(new.id) < ids.index(old.id)


def test_list_prep_sessions_reads_bodies_only_for_legacy_rows(db, api_db) -> None:
    """The list must not load every conversation body, and must not fan out.

    Cached rows answer the list from their summary / count columns; only the
    legacy rows without them need the stored body, and those are fetched in
    one query. The statement count is the guard against both a per-row
    re-read (an N+1) and a body column pulled into the row query.
    """
    body = json.dumps([{"role": "user", "content": "x" * 200}])
    cached = [
        PrepSession(resume_id=None, messages=body, summary=f"cached {i}", message_count=2)
        for i in range(5)
    ]
    legacy = [PrepSession(resume_id=None, messages=body) for _ in range(2)]
    db.add_all(cached + legacy)
    db.commit()

    with _captured_statements(db) as statements:
        items = list_prep_sessions(db, api_db)

    listed = {item.id for item in items}
    assert {s.id for s in cached + legacy} <= listed
    reads = [s for s in statements if "FROM prep_sessions" in s]
    assert len(reads) == 2, statements
    # The row query leaves the conversation body out; only the legacy batch
    # selects it.
    assert "prep_sessions.messages" not in reads[0]
    assert "prep_sessions.messages" in reads[1]
