"""Prep session list API: summary fields and ordering needed for resume-grouped display."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from realmock.domains.prep.models import PrepSession
from realmock.asgi import app
from realmock.platform.models import Resume


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
