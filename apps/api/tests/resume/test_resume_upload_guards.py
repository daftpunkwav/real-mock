"""Upload payload guards: overlong filenames fail as business errors, not 500s."""

from __future__ import annotations

from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.platform.models import Resume


def test_upload_rejects_overlong_filename_as_a0003(api_db) -> None:
    """A 300-char name must map to A0003 (ORM VARCHAR(255)), never a DB 500."""
    before = api_db.query(Resume).count()
    long_name = "a" * 296 + ".pdf"
    assert len(long_name) == 300
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/resume/upload",
            files={"file": (long_name, b"%PDF-1.7 fake-bytes", "application/pdf")},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "A0003"
    assert api_db.query(Resume).count() == before


def test_upload_accepts_boundary_filename_length(api_db) -> None:
    """Exactly 255 chars passes validation (no off-by-one)."""
    name = "b" * 251 + ".txt"
    assert len(name) == 255
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/resume/upload",
            files={"file": (name, b"hello", "text/plain")},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["filename"] == name
