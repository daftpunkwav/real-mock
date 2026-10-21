"""Upload payload guards: overlong filenames fail as business errors, not 500s.

The route also owns the three payload rules that keep a spoofed file out of
the store: a nameless upload (A1001), an empty body (A0005) and an extension
that contradicts the file header (A1003). None of them may reach the store.
"""

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


def test_upload_rejects_a_nameless_file_as_a1001(api_db) -> None:
    """A blank file name is A1001, and no row is created."""
    before = api_db.query(Resume).count()
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/resume/upload",
            files={"file": ("   ", b"%PDF-1.7 fake-bytes", "application/pdf")},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "A1001"
    assert api_db.query(Resume).count() == before


def test_upload_rejects_an_empty_body_as_a0005(api_db) -> None:
    """An empty file body is A0005, and no row is created."""
    before = api_db.query(Resume).count()
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/resume/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "A0005"
    assert api_db.query(Resume).count() == before


def test_upload_rejects_a_spoofed_extension_as_a1003(api_db) -> None:
    """A file whose header contradicts its extension is A1003, and no row is created.

    The magic-number rule is the last line against a renamed payload: a
    ``.pdf`` that is really a zip container (and the reverse) must never be
    parsed as the format its name claims.
    """
    before = api_db.query(Resume).count()
    spoofed = [
        ("cv.pdf", b"PK\x03\x04not-a-pdf", "application/pdf"),
        (
            "cv.docx",
            b"%PDF-1.7 not-a-docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ]
    for name, body, mime in spoofed:
        with TestClient(app) as client:
            resp = client.post("/api/v1/resume/upload", files={"file": (name, body, mime)})
        assert resp.status_code == 400, (name, resp.text)
        assert resp.json()["error"]["code"] == "A1003", (name, resp.text)
    assert api_db.query(Resume).count() == before
