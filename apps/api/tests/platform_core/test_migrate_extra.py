"""Migrate tests for realmock.platform.core.migrate.

Covers: column-name parsing edge cases, non-SQLite skips, table creation,
  generic failure swallowing, lineage backfill, and alembic path helpers.
Conventions: file-backed SQLite for real DDL; mocks only for failure paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy import create_engine, text


class TestMigrateExtras:
    def test_column_name_exception(self, monkeypatch) -> None:
        from realmock.platform.core import migrate as mg

        assert mg._column_name_from_stmt(None) is None  # type: ignore[arg-type]

    def test_non_sqlite_skips(self) -> None:
        from realmock.platform.core.migrate import apply_column_migrations

        eng = MagicMock()
        eng.url.get_backend_name.return_value = "postgresql"
        assert apply_column_migrations(eng, migrations={"t": ["ALTER TABLE t ADD COLUMN x TEXT"]}) == {}

    def test_create_table_path(self) -> None:
        from realmock.platform.core.migrate import apply_column_migrations

        eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
        applied = apply_column_migrations(eng, migrations={"stage_configs": ["CREATE TABLE IF NOT EXISTS stage_configs (id INTEGER PRIMARY KEY)"]})
        assert "stage_configs" in applied

    def test_generic_exception_path(self, monkeypatch) -> None:
        from realmock.platform.core import migrate as mg

        eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
        with eng.begin() as conn:
            conn.execute(text("CREATE TABLE _mg (id INTEGER PRIMARY KEY)"))

        def _boom(*a, **k):
            raise ValueError("boom")

        monkeypatch.setattr(mg, "text", _boom)
        # falls into generic Exception branch, returns without raising
        assert mg.apply_column_migrations(eng, migrations={"_mg": ["ALTER TABLE _mg ADD COLUMN z TEXT"]}) == {}

    def test_backfill_no_table_and_no_col(self) -> None:
        from realmock.platform.core.migrate import _backfill_resume_lineage

        eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
        with eng.begin() as conn:
            conn.execute(text("CREATE TABLE other (id INTEGER PRIMARY KEY)"))
        _backfill_resume_lineage(eng)
        eng2 = create_engine("sqlite://", connect_args={"check_same_thread": False})
        with eng2.begin() as conn:
            conn.execute(text("CREATE TABLE resumes (id INTEGER PRIMARY KEY)"))
        _backfill_resume_lineage(eng2)

    def test_run_migrations_stamp_failure_swallowed(self, monkeypatch) -> None:
        import realmock.platform.core.migrate as mg

        eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
        with eng.begin() as conn:
            conn.execute(text("CREATE TABLE _s (id INTEGER PRIMARY KEY)"))
        monkeypatch.setattr(mg, "stamp_alembic_head", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stamp fail")))
        out = mg.run_migrations(eng, migrations={"_s": ["ALTER TABLE _s ADD COLUMN q TEXT DEFAULT ''"]})
        assert "_s" in out

    def test_alembic_config_path(self) -> None:
        from realmock.platform.core.migrate import alembic_config_path

        assert alembic_config_path().name == "alembic.ini"
