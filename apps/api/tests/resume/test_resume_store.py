"""Resume store unit tests: JSON coerce, unique activate, delete missing, response score."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from realmock.domains.resume.schemas.limits import MAX_RESUME_VERSIONS
from realmock.domains.resume.services import resume_mappers, store
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.models import Resume
from realmock.platform.schemas import CandidateProfile


def _seed(api_db, **kwargs) -> Resume:
    row = Resume(
        filename=kwargs.get("filename", "a.pdf"),
        file_type=kwargs.get("file_type", "pdf"),
        raw_text=kwargs.get("raw_text", "x"),
        parsed_profile=kwargs.get("parsed_profile", "{}"),
        analysis=kwargs.get("analysis", "{}"),
        is_active=kwargs.get("is_active", False),
    )
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    return row


def test_load_parsed_profile_degrades() -> None:
    empty = resume_mappers.load_parsed_profile("{not-json", resume_id=1)
    assert empty == CandidateProfile()
    ok = resume_mappers.load_parsed_profile('{"name":"Ada","skills":["Py"]}', resume_id=1)
    assert ok.name == "Ada"
    assert ok.skills == ["Py"]


def test_load_analysis_dict_degrades() -> None:
    assert resume_mappers.load_analysis_dict("{oops", resume_id=1) == {}
    assert resume_mappers.load_analysis_dict("[1]", resume_id=1) == {}
    assert resume_mappers.load_analysis_dict('{"score": 12}', resume_id=1) == {"score": 12}


def test_activate_clears_other_active_rows(api_db) -> None:
    first = _seed(api_db, filename="one.pdf", is_active=True)
    second = _seed(api_db, filename="two.pdf", is_active=False)
    activated = store.activate_row(api_db, second.id)
    assert activated is not None
    assert activated.id == second.id
    assert activated.is_active is True
    api_db.refresh(first)
    assert first.is_active is False


def test_activate_missing_returns_none(api_db) -> None:
    assert store.activate_row(api_db, 999_001) is None


def test_delete_missing_returns_none(api_db) -> None:
    assert store.delete_row(api_db, 999_002) is None


def test_insert_upload_persists_row(api_db) -> None:
    parsed = CandidateProfile(name="Ada", skills=["Python"])
    row = store.insert_upload(
        api_db,
        filename="cv.pdf",
        file_type="pdf",
        raw_text="body",
        parsed=parsed,
    )
    assert row.id is not None
    loaded = store.get_row(api_db, row.id)
    assert loaded is not None
    assert loaded.filename == "cv.pdf"
    assert resume_mappers.load_parsed_profile(loaded.parsed_profile, loaded.id).name == "Ada"


def test_insert_upload_persists_parse_degraded(api_db) -> None:
    parsed = CandidateProfile(summary="raw excerpt", parse_degraded=True)
    row = store.insert_upload(
        api_db,
        filename="cv.pdf",
        file_type="pdf",
        raw_text="raw excerpt",
        parsed=parsed,
    )
    loaded = resume_mappers.load_parsed_profile(row.parsed_profile, row.id)
    assert loaded.parse_degraded is True
    assert resume_mappers.to_response(row).parsed_profile.parse_degraded is True


def test_finalize_stored_file_renames_to_row_id() -> None:
    from realmock.platform.config import get_settings
    from realmock.platform.core.security import sanitize_filename

    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_filename("cv.pdf")
    temp = upload_dir / f"abcd1234_{sanitized}"
    temp.write_bytes(b"%PDF-test")
    row = Resume(id=42, filename="cv.pdf", file_type="pdf", raw_text="x", parsed_profile="{}")
    store.finalize_stored_file(row, temp, sanitized)
    final = upload_dir / f"{row.id}_{sanitized}"
    assert final.is_file()
    assert not temp.exists()


def test_list_rows_newest_first(api_db) -> None:
    first = _seed(api_db, filename="old.pdf")
    first.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    api_db.commit()
    second = _seed(api_db, filename="new.pdf")
    ids = [row.id for row in store.list_rows(api_db)]
    assert ids.index(second.id) < ids.index(first.id)


def test_to_response_roundtrip(api_db) -> None:
    row = _seed(
        api_db,
        filename="cv.pdf",
        parsed_profile='{"name":"Lin"}',
        analysis='{"score": 70, "headline": "h"}',
    )
    row.score = 70
    api_db.commit()
    payload = resume_mappers.to_response(row)
    assert payload.filename == "cv.pdf"
    assert payload.parsed_profile.name == "Lin"
    assert payload.analysis["score"] == 70
    assert payload.score == 70
    assert payload.family_id == row.id
    assert payload.version_n == 1


def test_insert_upload_starts_own_family(api_db) -> None:
    parsed = CandidateProfile(name="Ada")
    row = store.insert_upload(
        api_db, filename="cv.pdf", file_type="pdf", raw_text="body", parsed=parsed
    )
    assert row.family_id == row.id
    assert row.version_n == 1
    assert row.is_active is False


def test_insert_version_appends_same_family(api_db) -> None:
    parsed = CandidateProfile(name="Ada")
    v1 = store.insert_upload(
        api_db, filename="cv.pdf", file_type="pdf", raw_text="v1", parsed=parsed
    )
    v2 = store.insert_upload(
        api_db,
        filename="cv-v2.pdf",
        file_type="pdf",
        raw_text="v2",
        parsed=parsed,
        family_id=v1.family_id,
    )
    assert v2.family_id == v1.family_id
    assert v2.version_n == 2
    assert v2.is_active is False
    other = store.insert_upload(
        api_db, filename="other.pdf", file_type="pdf", raw_text="x", parsed=parsed
    )
    assert other.family_id != v1.family_id
    assert other.version_n == 1


def test_delete_active_promotes_latest_family_version(api_db) -> None:
    parsed = CandidateProfile(name="Ada")
    v1 = store.insert_upload(
        api_db, filename="cv.pdf", file_type="pdf", raw_text="v1", parsed=parsed
    )
    v2 = store.insert_upload(
        api_db,
        filename="cv-v2.pdf",
        file_type="pdf",
        raw_text="v2",
        parsed=parsed,
        family_id=v1.family_id,
    )
    store.activate_row(api_db, v1.id)
    store.delete_row(api_db, v1.id)
    leftover = store.get_row(api_db, v2.id)
    assert leftover is not None
    assert leftover.is_active is True


def test_delete_latest_active_promotes_previous_version(api_db) -> None:
    parsed = CandidateProfile(name="Ada")
    v1 = store.insert_upload(
        api_db, filename="cv.pdf", file_type="pdf", raw_text="v1", parsed=parsed
    )
    v2 = store.insert_upload(
        api_db,
        filename="cv-v2.pdf",
        file_type="pdf",
        raw_text="v2",
        parsed=parsed,
        family_id=v1.family_id,
    )
    store.activate_row(api_db, v2.id)
    store.delete_row(api_db, v2.id)
    leftover = store.get_row(api_db, v1.id)
    assert leftover is not None
    assert leftover.is_active is True
    assert store.get_row(api_db, v2.id) is None


def test_delete_inactive_does_not_steal_active(api_db) -> None:
    parsed = CandidateProfile(name="Ada")
    v1 = store.insert_upload(
        api_db, filename="cv.pdf", file_type="pdf", raw_text="v1", parsed=parsed
    )
    v2 = store.insert_upload(
        api_db,
        filename="cv-v2.pdf",
        file_type="pdf",
        raw_text="v2",
        parsed=parsed,
        family_id=v1.family_id,
    )
    store.activate_row(api_db, v1.id)
    store.delete_row(api_db, v2.id)
    leftover = store.get_row(api_db, v1.id)
    assert leftover is not None
    assert leftover.is_active is True


def test_insert_upload_enforces_version_cap(api_db) -> None:
    parsed = CandidateProfile(name="Ada")
    v1 = store.insert_upload(
        api_db, filename="cv.pdf", file_type="pdf", raw_text="v1", parsed=parsed
    )
    for i in range(2, MAX_RESUME_VERSIONS + 1):
        store.insert_upload(
            api_db,
            filename=f"cv-v{i}.pdf",
            file_type="pdf",
            raw_text=f"v{i}",
            parsed=parsed,
            family_id=v1.family_id,
        )
    with pytest.raises(ApiBusinessError) as exc:
        store.insert_upload(
            api_db,
            filename="overflow.pdf",
            file_type="pdf",
            raw_text="x",
            parsed=parsed,
            family_id=v1.family_id,
        )
    assert exc.value.error_code == "A1008"


def test_insert_upload_rejects_invalid_family_id(api_db) -> None:
    parsed = CandidateProfile(name="Ada")
    with pytest.raises(ApiBusinessError) as exc:
        store.insert_upload(
            api_db,
            filename="cv.pdf",
            file_type="pdf",
            raw_text="x",
            parsed=parsed,
            family_id=0,
        )
    assert exc.value.error_code == "A1005"
    with pytest.raises(ApiBusinessError) as missing:
        store.insert_upload(
            api_db,
            filename="cv.pdf",
            file_type="pdf",
            raw_text="x",
            parsed=parsed,
            family_id=999_001,
        )
    assert missing.value.error_code == "A1005"
