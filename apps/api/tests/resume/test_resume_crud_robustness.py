"""Resume CRUD robustness: graceful degradation for corrupted persisted JSON, two-stage file lookup rules, and cleanup on deletion."""

from __future__ import annotations

import json
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


def _seed(
    api_db,
    *,
    filename: str,
    parsed_profile: str = "{}",
    analysis: str | None = None,
) -> Resume:
    kwargs: dict = {
        "filename": filename,
        "file_type": "pdf",
        "raw_text": "x",
        "parsed_profile": parsed_profile,
    }
    if analysis is not None:
        kwargs["analysis"] = analysis
    row = Resume(**kwargs)
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    return row


def test_get_resume_corrupt_profile_degrades_to_empty(api_db) -> None:
    """If the profile JSON is corrupted, the detail endpoint degrades to an empty profile instead of returning 500."""
    row = _seed(api_db, filename="broken.pdf", parsed_profile="{not-json")

    with TestClient(app) as client:
        resp = client.get(f"/api/v1/resume/{row.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_profile"]["name"] == ""
    assert body["parsed_profile"]["skills"] == []


def test_get_resume_corrupt_analysis_degrades_to_empty(api_db) -> None:
    """If the analysis JSON is corrupted, the detail endpoint degrades to an empty object instead of returning 500."""
    row = _seed(api_db, filename="bad-analysis.pdf", analysis="{oops")

    with TestClient(app) as client:
        resp = client.get(f"/api/v1/resume/{row.id}")
    assert resp.status_code == 200
    assert resp.json()["analysis"] == {}


@pytest.mark.parametrize("bad", ['[1]', '"str"', 'null', '"[1,2]"'])
def test_get_resume_non_object_analysis_degrades_to_empty(api_db, bad: str) -> None:
    """When analysis is valid JSON but its top level is not an object, likewise degrade to an empty object instead of returning 500."""
    row = _seed(api_db, filename="non-object-analysis.pdf", analysis=bad)

    with TestClient(app) as client:
        resp = client.get(f"/api/v1/resume/{row.id}")
    assert resp.status_code == 200
    assert resp.json()["analysis"] == {}


def test_get_resume_profile_type_mismatch_degrades_to_empty(api_db) -> None:
    """When profile is valid JSON but has incorrect field types, degrade to an empty profile instead of returning 500 (preventing silent propagation of an upstream bug)."""
    row = _seed(api_db, filename="type-mismatch.pdf", parsed_profile='{"skills": "not-a-list"}')

    with TestClient(app) as client:
        resp = client.get(f"/api/v1/resume/{row.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_profile"]["name"] == ""
    assert body["parsed_profile"]["skills"] == []


def test_list_resume_single_corrupt_row_does_not_break_page(api_db) -> None:
    """A single corrupted profile must not break the entire paginated list (degrade the bad row to an empty profile and return valid rows unchanged)."""
    bad = _seed(api_db, filename="bad.pdf", parsed_profile="{{{")
    good = _seed(
        api_db,
        filename="good.pdf",
        parsed_profile=json.dumps({"name": "Zhang San", "skills": ["Python"]}),
    )

    with TestClient(app) as client:
        resp = client.get("/api/v1/resume/list")
    assert resp.status_code == 200
    rows = {r["id"]: r for r in resp.json()}
    assert rows[bad.id]["parsed_profile"]["name"] == ""
    assert rows[good.id]["parsed_profile"]["name"] == "Zhang San"


def test_find_resume_files_prefers_row_unique_name() -> None:
    """When the row-unique name matches, return only that file; do not include legacy UUID files with the same sanitized name."""
    from realmock.domains.resume.services.extract import find_resume_files

    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    row = Resume(filename="My Resume.pdf", file_type="pdf", raw_text="", parsed_profile="{}")
    row.id = 7
    sanitized = sanitize_filename(row.filename)
    exact = upload_dir / f"7_{sanitized}"
    legacy = upload_dir / f"{uuid.uuid4().hex[:8]}_{sanitized}"
    exact.write_bytes(b"new")
    legacy.write_bytes(b"old")

    found = find_resume_files(row)
    assert found == [upload_dir / f"7_{sanitized}"]


def test_find_resume_files_falls_back_to_legacy() -> None:
    """When the row-unique name is missing, fall back to the old-style glob while excluding new-style names belonging to other rows."""
    from realmock.domains.resume.services.extract import find_resume_files

    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    row = Resume(filename="resume.pdf", file_type="pdf", raw_text="", parsed_profile="{}")
    row.id = 9
    sanitized = sanitize_filename(row.filename)
    other_row = upload_dir / f"99_{sanitized}"  # Do not mix in new-style names from other rows
    legacy_a = upload_dir / f"{uuid.uuid4().hex[:8]}_{sanitized}"
    legacy_b = upload_dir / f"{uuid.uuid4().hex[:8]}_{sanitized}"
    other_row.write_bytes(b"x")
    legacy_a.write_bytes(b"a")
    legacy_b.write_bytes(b"b")

    found = find_resume_files(row)
    assert legacy_a in found and legacy_b in found
    assert other_row not in found


def test_find_resume_files_all_digit_uuid_still_legacy() -> None:
    """A legacy file with an all-numeric eight-digit UUID prefix must not be mistaken for a row-unique name and consequently missed during lookup."""
    from realmock.domains.resume.services.extract import find_resume_files

    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    row = Resume(filename="resume.pdf", file_type="pdf", raw_text="", parsed_profile="{}")
    row.id = 9
    sanitized = sanitize_filename(row.filename)
    all_digit_uuid = upload_dir / f"12345678_{sanitized}"
    all_digit_uuid.write_bytes(b"a")

    found = find_resume_files(row)
    assert all_digit_uuid in found


def test_find_resume_files_no_suffix_overlap_hit() -> None:
    """Overlapping sanitized-name suffixes must not cause a false match: ``*_a_b.pdf`` does not match a longer name whose row-sanitized name is ``a_b.pdf``."""
    from realmock.domains.resume.services.extract import find_resume_files

    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    row = Resume(filename="a b.pdf", file_type="pdf", raw_text="", parsed_profile="{}")
    row.id = 9
    sanitized = sanitize_filename(row.filename)  # a_b.pdf
    longer = upload_dir / f"{uuid.uuid4().hex[:8]}_x_{sanitized}"  # Extra x_ before the sanitized name
    longer.write_bytes(b"other-row")

    assert find_resume_files(row) == []


def test_find_resume_files_no_hit() -> None:
    """Return an empty list when the directory contains no matching files."""
    from realmock.domains.resume.services.extract import find_resume_files

    row = Resume(filename="ghost.pdf", file_type="pdf", raw_text="", parsed_profile="{}")
    row.id = 1
    assert find_resume_files(row) == []


def test_delete_resume_cleans_row_unique_file(api_db) -> None:
    """Deletion: when the row-unique name matches, remove only that file; old-style files with the same sanitized name are unaffected."""
    row = _seed(api_db, filename="del-new.pdf")
    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_filename(row.filename)
    exact = upload_dir / f"{row.id}_{sanitized}"
    legacy = upload_dir / f"{uuid.uuid4().hex[:8]}_{sanitized}"
    exact.write_bytes(b"new")
    legacy.write_bytes(b"old")

    with TestClient(app) as client:
        resp = client.delete(f"/api/v1/resume/{row.id}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "id": row.id}
    assert not exact.exists()
    assert legacy.exists()


def test_delete_resume_cleans_legacy_files_when_row_unique_missing(api_db) -> None:
    """Deletion: when the row-unique name is missing, remove all old-style files with the same sanitized name."""
    row = _seed(api_db, filename="del-legacy.pdf")
    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_filename(row.filename)
    legacy_a = upload_dir / f"{uuid.uuid4().hex[:8]}_{sanitized}"
    legacy_b = upload_dir / f"{uuid.uuid4().hex[:8]}_{sanitized}"
    legacy_a.write_bytes(b"a")
    legacy_b.write_bytes(b"b")

    with TestClient(app) as client:
        resp = client.delete(f"/api/v1/resume/{row.id}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "id": row.id}
    assert not legacy_a.exists()
    assert not legacy_b.exists()


def test_activate_resume_is_unique(api_db) -> None:
    """POST activate clears other active flags so exactly one row stays active."""
    a = _seed(api_db, filename="a.pdf")
    b = _seed(api_db, filename="b.pdf")
    with TestClient(app) as client:
        first = client.post(f"/api/v1/resume/{a.id}/activate")
        second = client.post(f"/api/v1/resume/{b.id}/activate")
        missing = client.post("/api/v1/resume/999001/activate")
        listed = {row["id"]: row["is_active"] for row in client.get("/api/v1/resume/list").json()}
    assert first.status_code == 200
    assert first.json()["is_active"] is True
    assert second.status_code == 200
    assert second.json()["is_active"] is True
    assert listed[a.id] is False
    assert listed[b.id] is True
    assert missing.status_code == 404


def test_get_missing_resume_is_a1005(api_db) -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/resume/999002")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "A1005"


def test_delete_missing_resume_is_a1005(api_db) -> None:
    """DELETE must 404 with A1005; an empty 200 would pass frontend expectBody incorrectly."""
    with TestClient(app) as client:
        resp = client.delete("/api/v1/resume/999004")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "A1005"
