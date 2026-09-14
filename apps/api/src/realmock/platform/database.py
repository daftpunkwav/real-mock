"""Database connections and session management (two databases: api.db + sessions.db).

- **ApiBase** / ``api_engine``: profile, resume, and processor configuration (write ownership belongs to the profile/resume/settings domains).
- **SessionsBase** / ``sessions_engine``: interview / Prep / lease / rate-limit buckets.

``Base`` remains an alias for ``SessionsBase`` for session-domain ORM compatibility.
``get_db`` remains an alias for ``get_api_db`` (a historical convention in api routes).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from realmock.platform.config import get_settings

logger = logging.getLogger(__name__)


class ApiBase(DeclarativeBase):
    """api.db metadata (archive/resume/configuration)."""


class SessionsBase(DeclarativeBase):
    """sessions.db metadata (session/runtime)."""


# Session domain model history alias
Base = SessionsBase


_api_engine: Engine | None = None
_sessions_engine: Engine | None = None
_ApiSessionLocal: sessionmaker[Session] | None = None
_SessionsSessionLocal: sessionmaker[Session] | None = None
# RLock: ``get_*_session_factory`` calls ``get_*_engine`` while holding the lock, so it must be reentrant.
_engine_lock = threading.RLock()


def _sqlite_engine_kwargs(url: str) -> tuple[dict, dict]:
    connect_args: dict = {}
    pool_kwargs: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if url.endswith(":memory:") or url == "sqlite://":
            from sqlalchemy.pool import StaticPool

            pool_kwargs["poolclass"] = StaticPool
    return connect_args, pool_kwargs


def _attach_sqlite_pragmas(engine: Engine, url: str) -> None:
    if (
        url.startswith("sqlite")
        and ":memory:" not in url
        and url != "sqlite://"
        and "mode=memory" not in url
    ):
        event.listen(engine, "connect", _sqlite_pragmas)


def _sqlite_pragmas(dbapi_conn, _conn_record) -> None:
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
    finally:
        cur.close()


def _ensure_parent_dir(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    db_path = url.replace("sqlite:///", "", 1)
    if db_path.startswith(":") or "mode=memory" in db_path:
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def get_api_engine() -> Engine:
    global _api_engine
    if _api_engine is not None:
        return _api_engine
    with _engine_lock:
        if _api_engine is not None:
            return _api_engine
        settings = get_settings()
        url = settings.api_database_url
        connect_args, pool_kwargs = _sqlite_engine_kwargs(url)
        _api_engine = create_engine(url, connect_args=connect_args, **pool_kwargs)
        _attach_sqlite_pragmas(_api_engine, url)
        _ensure_parent_dir(url)
    return _api_engine


def get_sessions_engine() -> Engine:
    global _sessions_engine
    if _sessions_engine is not None:
        return _sessions_engine
    with _engine_lock:
        if _sessions_engine is not None:
            return _sessions_engine
        settings = get_settings()
        url = settings.sessions_database_url
        connect_args, pool_kwargs = _sqlite_engine_kwargs(url)
        _sessions_engine = create_engine(url, connect_args=connect_args, **pool_kwargs)
        _attach_sqlite_pragmas(_sessions_engine, url)
        _ensure_parent_dir(url)
    return _sessions_engine


def get_engine() -> Engine:
    """Backward compatibility: Return to sessions engine (old single library semantics)."""
    return get_sessions_engine()


def get_api_session_factory() -> sessionmaker[Session]:
    global _ApiSessionLocal
    if _ApiSessionLocal is not None:
        return _ApiSessionLocal
    with _engine_lock:
        if _ApiSessionLocal is not None:
            return _ApiSessionLocal
        _ApiSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_api_engine()
        )
    return _ApiSessionLocal


def get_sessions_session_factory() -> sessionmaker[Session]:
    global _SessionsSessionLocal
    if _SessionsSessionLocal is not None:
        return _SessionsSessionLocal
    with _engine_lock:
        if _SessionsSessionLocal is not None:
            return _SessionsSessionLocal
        _SessionsSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_sessions_engine()
        )
    return _SessionsSessionLocal


def reset_engines() -> None:
    """For testing: Release dual engine cache."""
    global _api_engine, _sessions_engine, _ApiSessionLocal, _SessionsSessionLocal
    with _engine_lock:
        if _api_engine is not None:
            _api_engine.dispose()
        if _sessions_engine is not None:
            _sessions_engine.dispose()
        _api_engine = None
        _sessions_engine = None
        _ApiSessionLocal = None
        _SessionsSessionLocal = None


def __getattr__(name: str):
    """Lazy export to avoid triggering engine creation during import (must be done after setenv)."""
    if name == "engine":
        return get_sessions_engine()
    if name in ("SessionLocal", "SessionsSessionLocal"):
        return get_sessions_session_factory()
    if name == "ApiSessionLocal":
        return get_api_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_api_db() -> Generator[Session, None, None]:
    db = get_api_session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_sessions_db() -> Generator[Session, None, None]:
    db = get_sessions_session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    """Historical aliases: api domain routing uses the api library by default."""
    yield from get_api_db()


@contextmanager
def api_db_session() -> Generator[Session, None, None]:
    """Short life cycle api library Session (tools/prompt word reading files)."""
    db = get_api_session_factory()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def sessions_db_session() -> Generator[Session, None, None]:
    db = get_sessions_session_factory()()
    try:
        yield db
    finally:
        db.close()


def init_api_db() -> None:
    from realmock.platform import models as _api_models  # noqa: F401

    get_api_engine()
    ApiBase.metadata.create_all(bind=get_api_engine())


def init_sessions_db() -> None:
    """Create the sessions database tables. ``register_sessions_domain_models()`` must be called first to register the ORM."""
    get_sessions_engine()
    SessionsBase.metadata.create_all(bind=get_sessions_engine())


def init_db() -> None:
    """Create all tables in dual databases."""
    init_api_db()
    init_sessions_db()


def dispose_all_engines() -> None:
    """The shutdown phase releases the twin engines."""
    reset_engines()


# Compatible with old names
reset_engine = reset_engines
