"""Collection clears: wipe deep-review results vs delete every resume."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.resume.services import store
from realmock.platform.schemas import CandidateProfile


def _seed(api_db, *, scored: bool = True):
    row = store.insert_upload(        api_db,
        filename="cv.txt",
        file_type="txt",
        raw_text="body",
        parsed=CandidateProfile(name="Ada"),
    )
    if scored:
        row.analysis = json.dumps({"score": 70, "dimension_scores": {f"d{i}": 70 for i in range(5)}})
        row.score = 70
        api_db.commit()
        api_db.refresh(row)
    return row


def test_clear_review_results_keeps_rows_and_files(api_db) -> None:
    store.delete_all_rows(api_db)
    scored = _seed(api_db, scored=True)
    plain = _seed(api_db, scored=False)

    with TestClient(app) as client:
        resp = client.delete("/api/v1/resume/analyses")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "cleared": 1}

    api_db.refresh(scored)
    api_db.refresh(plain)
    assert scored.analysis == "{}" and scored.score is None
    assert plain.analysis == "{}" and plain.score is None
    with TestClient(app) as client:
        assert len(client.get("/api/v1/resume/list").json()) == 2


def test_delete_collection_removes_rows(api_db) -> None:
    store.delete_all_rows(api_db)
    _seed(api_db, scored=True)
    _seed(api_db, scored=False)

    with TestClient(app) as client:
        resp = client.delete("/api/v1/resume/collection")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "deleted": 2}
        assert client.get("/api/v1/resume/list").json() == []


def test_clear_review_results_empty_collection(api_db) -> None:
    store.delete_all_rows(api_db)
    with TestClient(app) as client:
        assert client.delete("/api/v1/resume/analyses").json() == {"ok": True, "cleared": 0}
        assert client.delete("/api/v1/resume/collection").json() == {"ok": True, "deleted": 0}
