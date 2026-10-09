"""Wipe-all endpoint and service tests for realmock.platform.services.data_reset.

Covers: sessions/api row wipe, upload file removal, learning sidecar removal,
config-table preservation, and the HTTP summary shape.
Conventions: temp dual DBs from conftest; TestClient for HTTP.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.growth.models import GrowthRecord
from realmock.domains.prep.models import PrepSession
from realmock.platform.models import Resume
from realmock.platform.services.data_reset import clear_all_business_data


@pytest.fixture(autouse=True)
def _isolated_platform_root(monkeypatch, tmp_path):
    """Point PLATFORM_ROOT at tmp so the wipe's learning-sidecar cleanup (and
    the wipe-baseline below) never touches the real source-tree data dir."""
    import realmock.platform.config as config_mod

    monkeypatch.setattr(config_mod, "PLATFORM_ROOT", tmp_path)
    yield


@pytest.fixture(autouse=True)
def _wipe_baseline():
    """The conftest DB files live for the whole pytest session; start every
    test from a wiped state so absolute-count assertions hold regardless of
    rows left behind by earlier test files."""
    clear_all_business_data()
    yield


@pytest.fixture
def seeded(api_engine, engine, tmp_path):
    """Rows in both databases plus files on disk; returns the settings paths."""
    from sqlalchemy.orm import sessionmaker

    from realmock.platform.database import ApiBase, SessionsBase

    ApiBase.metadata.create_all(bind=api_engine)
    SessionsBase.metadata.create_all(bind=engine)

    api_session = sessionmaker(bind=api_engine)()
    api_session.add(Resume(filename="a.pdf", file_type="pdf", analysis='{"score":50}', score=50))
    api_session.commit()

    sess_session = sessionmaker(bind=engine)()
    sess_session.add(PrepSession())
    sess_session.add(
        GrowthRecord(
            session_id=1,
            weak_skills='["x"]',
            common_mistakes="[]",
            training_plan="[]",
        )
    )
    sess_session.commit()

    upload = Path(tmp_path / "uploads")
    upload.mkdir(parents=True, exist_ok=True)
    (upload / "1_a.pdf").write_bytes(b"%PDF-1.4")
    data_dir = Path(tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "system_learning.json").write_text("{}", encoding="utf-8")
    (data_dir / "system_learning.json.lock").write_text("", encoding="utf-8")
    return {"uploads": upload, "data": data_dir}


def test_wipe_clears_rows_and_files(seeded, tmp_path, monkeypatch) -> None:
    """The wipe removes seeded rows, uploads, and the learning sidecar."""
    monkeypatch.setenv("UPLOAD_DIR", str(seeded["uploads"]))
    from realmock.platform.config import get_settings

    get_settings.cache_clear()

    result = clear_all_business_data()

    assert result["api_tables"]["resumes"] == 1
    assert result["sessions_tables"]["prep_sessions"] == 1
    assert result["sessions_tables"]["growth_records"] == 1
    assert result["upload_files"] == 1
    assert result["learning_reset"] is True
    assert list(seeded["uploads"].iterdir()) == []
    assert not (seeded["data"] / "system_learning.json").exists()
    assert not (seeded["data"] / "system_learning.json.lock").exists()


def test_wipe_preserves_config_tables(api_engine, engine) -> None:
    """Config tables (providers etc.) survive the content wipe."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from realmock.platform.database import ApiBase, SessionsBase
    from realmock.platform.models.config_models import LlmProvider

    ApiBase.metadata.create_all(bind=api_engine)
    SessionsBase.metadata.create_all(bind=engine)
    api_session = sessionmaker(bind=api_engine)()
    before = api_session.execute(text("SELECT COUNT(*) FROM llm_providers")).scalar()
    api_session.add(LlmProvider(name="p1"))
    api_session.commit()

    result = clear_all_business_data()

    assert "llm_providers" not in result["api_tables"]
    remaining = api_session.execute(text("SELECT COUNT(*) FROM llm_providers")).scalar()
    assert remaining == before + 1


def test_wipe_is_idempotent_on_empty_databases(api_engine, engine) -> None:
    """A second wipe on empty databases succeeds with zero counts."""
    from realmock.platform.database import ApiBase, SessionsBase

    ApiBase.metadata.create_all(bind=api_engine)
    SessionsBase.metadata.create_all(bind=engine)
    result = clear_all_business_data()
    assert result["upload_files"] == 0
    assert all(count == 0 for count in result["api_tables"].values())


def test_clear_endpoint_returns_summary(seeded, tmp_path, monkeypatch) -> None:
    """The HTTP endpoint returns the per-area removal summary."""
    monkeypatch.setenv("UPLOAD_DIR", str(seeded["uploads"]))
    from realmock.platform.config import get_settings

    get_settings.cache_clear()

    with TestClient(app) as client:
        resp = client.post("/api/v1/settings/data/clear")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_tables"].get("resumes") == 1
    assert "sessions_tables" in body
    assert body["upload_files"] == 1
    assert body["learning_reset"] is True


@pytest.mark.parametrize("operation", ["_clear_sessions_db", "_clear_api_db"])
def test_database_failure_preserves_uploads(
    seeded, monkeypatch, api_engine, engine, operation
) -> None:
    """A db failure aborts before any file removal; uploads survive."""
    from sqlalchemy import text

    from realmock.platform.core.errors import ApiBusinessError
    from realmock.platform.services import data_reset

    def fail():
        """Stub replacement that simulates an unavailable database."""
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(data_reset, operation, fail)
    message = "partially completed" if operation == "_clear_api_db" else "database unavailable"
    error_type = ApiBusinessError if operation == "_clear_api_db" else RuntimeError
    with pytest.raises(error_type, match=message):
        clear_all_business_data()

    assert (seeded["uploads"] / "1_a.pdf").read_bytes() == b"%PDF-1.4"
    assert (seeded["data"] / "system_learning.json").read_text() == "{}"
    with api_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM resumes")).scalar() == 1
    with engine.connect() as conn:
        expected = 0 if operation == "_clear_api_db" else 1
        assert conn.execute(text("SELECT COUNT(*) FROM prep_sessions")).scalar() == expected
        assert conn.execute(text("SELECT COUNT(*) FROM growth_records")).scalar() == expected


def test_api_database_failure_reports_partial_completion_and_can_be_retried(
    seeded, monkeypatch, api_engine, engine
) -> None:
    """A partial api-db wipe reports B1003 and retries to completion."""
    from sqlalchemy import event, text

    from realmock.platform.config import get_settings

    monkeypatch.setenv("UPLOAD_DIR", str(seeded["uploads"]))
    get_settings.cache_clear()

    # Fail after resumes have been deleted inside the API transaction, proving
    # its rollback preserves rows while the sessions deletion is committed.
    def fail_profile_delete(conn, cursor, statement, parameters, context, executemany):
        """Fail only the user_profiles delete, after resumes were removed."""
        if statement.startswith("DELETE FROM user_profiles"):
            raise RuntimeError("database unavailable")

    with TestClient(app, raise_server_exceptions=False) as client:
        event.listen(api_engine, "before_cursor_execute", fail_profile_delete)
        try:
            resp = client.post("/api/v1/settings/data/clear")
        finally:
            event.remove(api_engine, "before_cursor_execute", fail_profile_delete)

        assert resp.status_code == 500
        assert "partially completed" in resp.json()["detail"]
        assert "Session data has been cleared" in resp.json()["detail"]
        assert resp.json()["error"]["code"] == "B1003"
        assert resp.json()["error"]["retryable"] is True
        assert "Retry" in resp.json()["error"]["hint"]
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM prep_sessions")).scalar() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM growth_records")).scalar() == 0
        with api_engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM resumes")).scalar() == 1
        assert (seeded["uploads"] / "1_a.pdf").exists()
        assert (seeded["data"] / "system_learning.json").exists()

        retry = client.post("/api/v1/settings/data/clear")
        assert retry.status_code == 200
        assert retry.json()["api_tables"]["resumes"] == 1
        assert all(count == 0 for count in retry.json()["sessions_tables"].values())
        assert retry.json()["upload_files"] == 1
        with api_engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM resumes")).scalar() == 0
        assert not (seeded["uploads"] / "1_a.pdf").exists()
        assert not (seeded["data"] / "system_learning.json").exists()


def test_file_cleanup_failure_can_be_retried(seeded, monkeypatch) -> None:
    """An upload-cleanup failure leaves files for an idempotent retry."""
    from realmock.platform.services import data_reset

    with monkeypatch.context() as patch:
        patch.setattr(
            data_reset, "_clear_uploads", lambda _: (_ for _ in ()).throw(OSError("disk"))
        )
        with pytest.raises(OSError, match="disk"):
            clear_all_business_data()
    assert (seeded["uploads"] / "1_a.pdf").exists()
    result = clear_all_business_data()
    assert all(count == 0 for count in result["api_tables"].values())
    assert result["upload_files"] == 1
