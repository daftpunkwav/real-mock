"""Resume source-file preview/download endpoints: inline preview, attachment download, and the 404 contract."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.platform.config import get_settings
from realmock.platform.core.security import sanitize_filename
from realmock.platform.models import Resume


@pytest.fixture(autouse=True)
def _fresh_upload_settings():
    """Reset the get_settings cache to ensure that both reads and writes use this test's temporary upload directory."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _seed_resume_with_file(api_db, filename: str, content: bytes) -> Resume:
    """Create a database record and disk file according to the upload-storage rule (UUID prefix_sanitized name).

    The database stores the original filename, while the disk filename is sanitized by ``sanitize_filename``—exactly matching
    ``upload_resume``; a Chinese filename is sanitized to underscores.
    """
    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{uuid.uuid4().hex[:8]}_{sanitize_filename(filename)}").write_bytes(content)
    row = Resume(filename=filename, file_type="pdf", raw_text="x", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    return row


def test_get_resume_file_inline_preview(api_db) -> None:
    """Default to inline: the browser can preview the PDF directly, and the file bytes are returned unchanged."""
    row = _seed_resume_with_file(api_db, "Xiao Guoqiang Resume.pdf", b"%PDF-1.7 fake-bytes")

    with TestClient(app) as client:
        resp = client.get(f"/api/v1/resume/{row.id}/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content == b"%PDF-1.7 fake-bytes"
    assert "attachment" not in resp.headers.get("content-disposition", "")


def test_get_resume_file_download_mode(api_db) -> None:
    """With ``?download=1``, Content-Disposition becomes attachment."""
    row = _seed_resume_with_file(api_db, "resume.pdf", b"%PDF-1.7 fake-bytes")

    with TestClient(app) as client:
        resp = client.get(f"/api/v1/resume/{row.id}/file?download=1")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")


def test_get_resume_file_missing_row_and_orphan(api_db) -> None:
    """No database record / database record exists but the file is missing: always return a 404 business envelope."""
    with TestClient(app) as client:
        assert client.get("/api/v1/resume/999/file").status_code == 404

        row = Resume(filename="ghost.pdf", file_type="pdf", raw_text="", parsed_profile="{}")
        api_db.add(row)
        api_db.commit()
        api_db.refresh(row)
        resp = client.get(f"/api/v1/resume/{row.id}/file")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "A1005"


def _write_multipage_pdf(path: Path, pages: int) -> None:
    """Generate a multi-page PDF with a text layer (for the paginated preview contract)."""
    import fitz

    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"page {i + 1}")
    doc.save(path)
    doc.close()


def test_get_resume_pages_meta_and_page_image(api_db) -> None:
    """Paginated PDF preview: page-count metadata + server-side rendering of individual pages as PNG."""
    row = _seed_resume_with_file(api_db, "multi.pdf", b"")
    upload_dir = Path(get_settings().upload_dir)
    pattern = f"*_{sanitize_filename(row.filename)}"
    pdf_path = next(upload_dir.glob(pattern))
    _write_multipage_pdf(pdf_path, pages=2)

    with TestClient(app) as client:
        meta = client.get(f"/api/v1/resume/{row.id}/pages")
        img = client.get(f"/api/v1/resume/{row.id}/pages/2")
        beyond = client.get(f"/api/v1/resume/{row.id}/pages/3")
        non_int = client.get(f"/api/v1/resume/{row.id}/pages/abc")
    assert meta.status_code == 200
    assert meta.json() == {"pages": 2}
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.content[:8].startswith(b"\x89PNG\r\n\x1a\n")
    assert beyond.status_code == 404
    assert non_int.status_code in {400, 422}


def test_get_resume_pages_meta_non_pdf(api_db) -> None:
    """For non-PDF formats, pages=0 and the frontend uses the download fallback."""
    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{uuid.uuid4().hex[:8]}_{sanitize_filename('note.txt')}").write_text("hello")
    row = Resume(filename="note.txt", file_type="txt", raw_text="hello", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)

    with TestClient(app) as client:
        resp = client.get(f"/api/v1/resume/{row.id}/pages")
    assert resp.status_code == 200
    assert resp.json() == {"pages": 0}


def test_get_resume_pages_missing_row_is_a1005(api_db) -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/resume/999005/pages")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "A1005"


def test_cross_site_fetch_rejected(api_db) -> None:
    """Browser-driven cross-site request (Sec-Fetch-Site: cross-site) → 403 A0403.

    A malicious page can exploit loopback authentication to blindly target local endpoints; same-site requests and
    non-browser clients without this header are unaffected.
    """
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    row = _seed_resume_with_file(api_db, "cs.pdf", b"%PDF-1.7 fake")

    with TestClient(app) as client:
        ok = client.get(
            f"/api/v1/resume/{row.id}/file",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        cross = client.get(
            f"/api/v1/resume/{row.id}/file",
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        no_header = client.get(f"/api/v1/resume/{row.id}/file")
    assert ok.status_code == 200
    assert no_header.status_code == 200
    assert cross.status_code == 403
    assert cross.json()["error"]["code"] == "A0403"


def test_resume_file_download_rate_limited(api_db) -> None:
    """The download endpoint is protected by sliding-window rate limiting; exceeding DEFAULT_RATE_LIMIT_PER_MINUTE returns 429."""
    from realmock.platform.core.constants import DEFAULT_RATE_LIMIT_PER_MINUTE
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    row = _seed_resume_with_file(api_db, "rated.pdf", b"%PDF-1.7 fake")

    with TestClient(app) as client:
        codes = [
            client.get(f"/api/v1/resume/{row.id}/file?download=1").status_code
            for _ in range(DEFAULT_RATE_LIMIT_PER_MINUTE + 1)
        ]
    assert all(code == 200 for code in codes[:-1])
    assert codes[-1] == 429


def test_delete_then_reupload_same_name(api_db) -> None:
    """Upload → delete → re-upload with the same name → delete again: the entire flow succeeds with no files left behind."""
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    with TestClient(app) as client:
        r1 = client.post(
            "/api/v1/resume/upload",
            files={"file": ("same-name-resume.txt", b"VERSION_1", "text/plain")},
        ).json()
        assert client.get(f"/api/v1/resume/{r1['id']}/file").content == b"VERSION_1"

        assert client.delete(f"/api/v1/resume/{r1['id']}").status_code == 200
        assert client.get(f"/api/v1/resume/{r1['id']}/file").status_code == 404

        r2 = client.post(
            "/api/v1/resume/upload",
            files={"file": ("same-name-resume.txt", b"VERSION_2", "text/plain")},
        ).json()
        assert client.get(f"/api/v1/resume/{r2['id']}/file").content == b"VERSION_2"

        assert client.delete(f"/api/v1/resume/{r2['id']}").status_code == 200
        assert client.get(f"/api/v1/resume/{r2['id']}/file").status_code == 404

    # After two deletion rounds, no files with that sanitized name should remain on disk
    leftovers = list(
        Path(get_settings().upload_dir).glob(f"*_{sanitize_filename('same-name-resume.txt')}")
    )
    assert leftovers == []


def test_same_name_different_content_isolated(api_db) -> None:
    """Two resumes with identical names but different content: each row's preview/download resolves to its own file."""
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    with TestClient(app) as client:
        r1 = client.post(
            "/api/v1/resume/upload",
            files={"file": ("same-name-resume.txt", b"CONTENT_A", "text/plain")},
        ).json()
        r2 = client.post(
            "/api/v1/resume/upload",
            files={"file": ("same-name-resume.txt", b"CONTENT_B", "text/plain")},
        ).json()
        assert r1["id"] != r2["id"]
        assert client.get(f"/api/v1/resume/{r1['id']}/file").content == b"CONTENT_A"
        assert client.get(f"/api/v1/resume/{r2['id']}/file").content == b"CONTENT_B"

        # Deleting the first row does not affect the second row
        client.delete(f"/api/v1/resume/{r1['id']}")
        assert client.get(f"/api/v1/resume/{r2['id']}/file").content == b"CONTENT_B"


def test_colliding_sanitized_names_stay_isolated(api_db) -> None:
    """Different original non-ASCII names sanitize to the same name: row-unique stored names keep rows isolated.

    Both fixture filenames sanitize to "_-beta.txt"; the old behavior could overwrite previews or delete the wrong file,
    while row-unique names ({id}_sanitized name) let each row locate its own file exactly.
    """
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    with TestClient(app) as client:
        r1 = client.post(
            "/api/v1/resume/upload",
            files={"file": ("Xiao Guoqiang-beta.txt", b"CONTENT_A", "text/plain")},
        ).json()
        r2 = client.post(
            "/api/v1/resume/upload",
            files={"file": ("Li Si-beta.txt", b"CONTENT_B", "text/plain")},
        ).json()
        assert r1["id"] != r2["id"]

        assert client.get(f"/api/v1/resume/{r1['id']}/file").content == b"CONTENT_A"
        assert client.get(f"/api/v1/resume/{r2['id']}/file").content == b"CONTENT_B"

        # Deleting the first row removes only its own file; the second row is unaffected
        assert client.delete(f"/api/v1/resume/{r1['id']}").status_code == 200
        assert client.get(f"/api/v1/resume/{r1['id']}/file").status_code == 404
        assert client.get(f"/api/v1/resume/{r2['id']}/file").content == b"CONTENT_B"
