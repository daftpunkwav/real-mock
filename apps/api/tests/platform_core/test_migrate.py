"""``realmock.platform.core.migrate`` unit tests.

Coverage:

- First run: add missing columns to existing tables;
- Second run: skip existing columns (idempotent) without reporting DuplicateColumn;
- Error path: if SQL execution fails, swallow that table's migration failure while other tables complete normally;
- Silently skip migration entries for nonexistent tables without affecting other tables.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from realmock.platform.core.migrate import API_MIGRATIONS, _column_name_from_stmt, run_migrations
from realmock.platform.database import ApiBase


def _fresh_engine():
    """Return a fresh :memory: engine that only creates tables without running migrations, making it easy to assert the before/after state."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        future=True,
    )
    ApiBase.metadata.create_all(eng)
    return eng


def test_column_name_extraction() -> None:
    """``_column_name_from_stmt`` extracts the bare column name (including quoted forms)."""
    assert _column_name_from_stmt(
        "ALTER TABLE x ADD COLUMN foo VARCHAR(20) DEFAULT ''"
    ) == "foo"
    assert _column_name_from_stmt(
        "ALTER TABLE x ADD COLUMN `bar` VARCHAR(20) DEFAULT 0"
    ) == "bar"
    assert _column_name_from_stmt("ALTER TABLE x DROP COLUMN z") is None
    assert _column_name_from_stmt("") is None


def test_run_migrations_is_idempotent() -> None:
    """Run migrations twice: the second run should be empty (verifying idempotency) and must not report DuplicateColumn.

    Use a synthetic table plus an explicitly injected migration dictionary to avoid relying on the drift assumption that the model lacks columns and migrations add them
    (when the model already contains every column, applied is empty after create_all).
    """
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        future=True,
    )
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE _mig_test (id INTEGER PRIMARY KEY)"))

    migrations = {
        "_mig_test": [
            "ALTER TABLE _mig_test ADD COLUMN foo VARCHAR(20) DEFAULT ''",
            "ALTER TABLE _mig_test ADD COLUMN bar INTEGER DEFAULT 0",
        ]
    }
    first = run_migrations(eng, migrations=migrations)
    second = run_migrations(eng, migrations=migrations)
    assert "_mig_test" in first
    assert len(first["_mig_test"]) == 2
    assert "_mig_test" not in second
    cols = {c["name"] for c in inspect(eng).get_columns("_mig_test")}
    assert "foo" in cols and "bar" in cols


def test_run_migrations_skips_missing_table() -> None:
    """If a table in the migration list does not exist, do not crash; the other tables should still complete."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        future=True,
    )
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE _mig_ok (id INTEGER PRIMARY KEY)"))

    applied = run_migrations(
        eng,
        migrations={
            "_mig_missing": [
                "ALTER TABLE _mig_missing ADD COLUMN x VARCHAR(10) DEFAULT ''",
            ],
            "_mig_ok": [
                "ALTER TABLE _mig_ok ADD COLUMN y VARCHAR(10) DEFAULT ''",
            ],
        },
    )
    assert "_mig_missing" not in applied
    assert "_mig_ok" in applied


def test_failed_alter_silently_continues_other_tables() -> None:
    """Inject invalid SQL for one table: that table's failure is swallowed, while the other tables complete normally."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        future=True,
    )
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE _mig_bad (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE _mig_good (id INTEGER PRIMARY KEY)"))

    applied = run_migrations(
        eng,
        migrations={
            "_mig_bad": [
                # Intentional syntax error that triggers OperationalError
                "ALTER TABLE _mig_bad ADD COLUMN !!!",
            ],
            "_mig_good": [
                "ALTER TABLE _mig_good ADD COLUMN ok VARCHAR(10) DEFAULT ''",
            ],
        },
    )

    assert "_mig_bad" not in applied
    assert "_mig_good" in applied
    cols = {c["name"] for c in inspect(eng).get_columns("_mig_good")}
    assert "ok" in cols


def test_run_migrations_stamps_alembic_version() -> None:
    """run_migrations should write alembic_version=head.

    Pass production ``API_MIGRATIONS``: it should be a no-op for the complete schema produced by create_all,
    implicitly verifying that model columns and the migration manifest are synchronized.
    """
    from realmock.platform.core.migrate import ALEMBIC_HEAD_REVISION

    eng = _fresh_engine()
    run_migrations(eng, migrations=API_MIGRATIONS)
    with eng.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
    assert row is not None
    assert row[0] == ALEMBIC_HEAD_REVISION



def test_session_ddl_ownership_by_domain() -> None:
    """Session-business DDL belongs to business packages and is not owned by the shared platform layer (changing or deleting a business does not change the platform).

    - ``realmock.domains.prep`` / ``realmock.domains.interview`` each declare only
      tables of their own domain (interview owns the session and process tables);
    - The source of ``platform/core/migrate.py`` no longer contains any session-business table names;
    - ``API_MIGRATIONS`` must not include session-business tables.
    """
    import realmock.platform.core.migrate
    from realmock.domains.interview.column_migrations import (
        SESSIONS_MIGRATIONS as INTERVIEW_MIGRATIONS,
    )
    from realmock.domains.prep.column_migrations import SESSIONS_MIGRATIONS as PREP_MIGRATIONS

    assert set(PREP_MIGRATIONS) == {"prep_sessions"}
    assert set(INTERVIEW_MIGRATIONS) == {"interview_sessions", "interview_processes"}

    source = Path(realmock.platform.core.migrate.__file__).read_text(encoding="utf-8")
    assert "prep_sessions" not in source
    assert "interview_sessions" not in source
    assert "interview_processes" not in source

    assert "interview_sessions" not in API_MIGRATIONS
    assert "interview_processes" not in API_MIGRATIONS
    assert "prep_sessions" not in API_MIGRATIONS


def test_apply_column_migrations_respects_explicit_dict() -> None:
    """The explicitly provided dictionary is the only migration source: never touch tables outside the allowlist."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        future=True,
    )
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE _only_api (id INTEGER PRIMARY KEY)"))

    from realmock.platform.core.migrate import apply_column_migrations

    applied = apply_column_migrations(
        eng,
        migrations={
            "_only_api": [
                "ALTER TABLE _only_api ADD COLUMN x VARCHAR(10) DEFAULT ''",
            ],
            "interview_sessions": [
                "ALTER TABLE interview_sessions ADD COLUMN ghost VARCHAR(10) DEFAULT ''",
            ],
        },
    )
    assert "_only_api" in applied
    assert "interview_sessions" not in applied


def test_stamp_alembic_head_keeps_mismatched_version() -> None:
    """Preserve the existing record when its version differs from head (do not overwrite it; emit a warning only)."""
    from realmock.platform.core.migrate import ALEMBIC_HEAD_REVISION, stamp_alembic_head

    eng = _fresh_engine()
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('legacy_0000')"))

    stamp_alembic_head(eng)

    with eng.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
    assert row is not None
    # Preserve the original version instead of overwriting it with head
    assert row[0] == "legacy_0000"
    assert row[0] != ALEMBIC_HEAD_REVISION

    # Still write head when the table is empty (compatibility for initial adoption)
    eng2 = _fresh_engine()
    stamp_alembic_head(eng2)
    with eng2.connect() as conn:
        row2 = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
    assert row2 is not None and row2[0] == ALEMBIC_HEAD_REVISION


def test_backfill_resume_lineage_assigns_family_id() -> None:
    from sqlalchemy.orm import Session

    from realmock.platform.models import Resume

    eng = _fresh_engine()
    with Session(eng) as session:
        row = Resume(
            filename="a.pdf",
            file_type="pdf",
            raw_text="x",
            parsed_profile="{}",
            family_id=0,
            version_n=0,
        )
        session.add(row)
        session.commit()
        resume_id = int(row.id)
    with eng.begin() as conn:
        conn.execute(text("UPDATE resumes SET family_id = 0, version_n = 0"))
    run_migrations(eng, migrations=API_MIGRATIONS)
    with eng.connect() as conn:
        loaded = conn.execute(
            text("SELECT id, family_id, version_n FROM resumes WHERE id = :id"),
            {"id": resume_id},
        ).fetchone()
    assert loaded is not None
    assert loaded[1] == loaded[0]
    assert loaded[2] == 1
