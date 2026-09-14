"""Global pytest fixtures: dual file-backed temp SQLite DBs (api.db/sessions.db under mkdtemp) + isolated UPLOAD_DIR."""

from __future__ import annotations

import base64
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker


def pytest_configure(config: pytest.Config) -> None:
    import tempfile

    db_dir = tempfile.mkdtemp(prefix="realmock_pytest_db_")
    api_path = Path(db_dir) / "api.db"
    sessions_path = Path(db_dir) / "sessions.db"
    os.environ["API_DATABASE_URL"] = f"sqlite:///{api_path.as_posix()}"
    os.environ["SESSIONS_DATABASE_URL"] = f"sqlite:///{sessions_path.as_posix()}"
    os.environ["DATABASE_URL"] = os.environ["SESSIONS_DATABASE_URL"]
    os.environ.setdefault("LLM_API_KEY", "test-key")
    os.environ.setdefault("LLM_API_BASE", "http://localhost:9999/v1")
    os.environ.setdefault("LLM_MODEL", "test-model")
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:8080")
    os.environ["TEST_MODE"] = "1"
    os.environ.setdefault(
        "SECRET_KEY", base64.b64encode(b"test-master-key-32-bytes").decode()
    )
    try:
        from realmock.platform.config import get_settings
        from realmock.platform.database import reset_engines

        get_settings.cache_clear()
        reset_engines()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    yield


@pytest.fixture
def engine():
    from realmock.platform.database import get_sessions_engine

    return get_sessions_engine()


@pytest.fixture
def api_engine():
    from realmock.platform.database import get_api_engine

    return get_api_engine()


@pytest.fixture
def session_factory(engine, api_engine):
    from realmock.platform.database import ApiBase, SessionsBase
    import realmock.platform.models  # noqa: F401
    import realmock.domains.prep.models  # noqa: F401
    import realmock.domains.interview.models  # noqa: F401

    ApiBase.metadata.create_all(bind=api_engine)
    SessionsBase.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db(session_factory) -> Generator:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def api_db(api_engine) -> Generator:
    from realmock.platform.database import ApiBase
    import realmock.platform.models  # noqa: F401

    ApiBase.metadata.create_all(bind=api_engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=api_engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def temp_upload_dir(tmp_path: Path) -> Path:
    p = tmp_path / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch):
    import ipaddress

    from realmock.platform.core.security import url as security_url

    def fake_resolve(hostname: str):
        try:
            return [ipaddress.ip_address(hostname.strip("[]"))]
        except ValueError:
            pass
        if hostname.lower() == "localhost":
            return [ipaddress.ip_address("127.0.0.1")]
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(security_url, "_resolve_all", fake_resolve)
