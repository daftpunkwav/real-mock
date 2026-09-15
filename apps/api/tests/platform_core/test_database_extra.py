"""Database tests for realmock.platform.database.

Covers: SQLite engine kwargs/pragmas, module attribute aliases,
  and session-generator lifecycle.
Conventions: tmp SQLite files and shared api_engine/engine fixtures.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine


class TestDatabaseExtras:
    def test_sqlite_kwargs_and_pragmas(self, tmp_path) -> None:
        from realmock.platform import database as dbm

        ca, pk = dbm._sqlite_engine_kwargs("sqlite:///:memory:")
        assert "poolclass" in pk
        ca2, pk2 = dbm._sqlite_engine_kwargs("postgresql://x")
        assert ca2 == {} and pk2 == {}
        eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
        dbm._attach_sqlite_pragmas(eng, "sqlite:///:memory:")
        dbm._sqlite_pragmas(eng.raw_connection(), None)
        dbm._ensure_parent_dir("postgresql://x")
        dbm._ensure_parent_dir("sqlite:///:memory:")
        p = tmp_path / "sub" / "db.sqlite"
        dbm._ensure_parent_dir(f"sqlite:///{p.as_posix()}")
        assert p.parent.is_dir()

    def test_getattr_and_aliases(self) -> None:
        from realmock.platform import database as dbm

        assert dbm.get_engine() is dbm.get_sessions_engine()
        assert dbm.__getattr__("engine") is dbm.get_sessions_engine()
        assert dbm.__getattr__("SessionLocal") is dbm.get_sessions_session_factory()
        assert dbm.__getattr__("ApiSessionLocal") is dbm.get_api_session_factory()
        with pytest.raises(AttributeError):
            dbm.__getattr__("nope")
        assert dbm.reset_engine is dbm.reset_engines

    def test_session_generators(self, api_engine, engine) -> None:
        import realmock.platform.models  # noqa: F401
        import realmock.domains.prep.models  # noqa: F401
        import realmock.domains.interview.models  # noqa: F401

        from realmock.platform.database import (
            ApiBase,
            SessionsBase,
            api_db_session,
            get_api_db,
            get_db,
            get_sessions_db,
            init_api_db,
            init_sessions_db,
            init_db,
            sessions_db_session,
        )

        ApiBase.metadata.create_all(bind=api_engine)
        SessionsBase.metadata.create_all(bind=engine)
        init_api_db()
        init_sessions_db()
        init_db()
        for gen in (get_api_db(), get_sessions_db(), get_db()):
            db = next(gen)
            db.close()
        with api_db_session():
            pass
        with sessions_db_session():
            pass
