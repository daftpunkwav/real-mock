"""Wipe-all endpoint and service tests for realmock.platform.services.data_reset.

Covers: sessions/api row wipe, upload file removal, learning sidecar removal,
config-table preservation, and the HTTP summary shape.
Conventions: temp dual DBs from conftest; TestClient for HTTP.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import realmock.domains.growth.models  # noqa: F401
import realmock.domains.interview.models  # noqa: F401
import realmock.domains.prep.models  # noqa: F401
import realmock.domains.records.models  # noqa: F401
import realmock.platform.models  # noqa: F401
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
    from realmock.platform.database import ApiBase, SessionsBase

    ApiBase.metadata.create_all(bind=api_engine)
    SessionsBase.metadata.create_all(bind=engine)
    result = clear_all_business_data()
    assert result["upload_files"] == 0
    assert all(count == 0 for count in result["api_tables"].values())


def test_clear_endpoint_returns_summary(seeded, tmp_path, monkeypatch) -> None:
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
