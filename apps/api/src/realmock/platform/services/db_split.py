"""Split the legacy single-file ``app.db`` into ``api.db`` + ``sessions.db``."""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

from realmock.platform.config import PLATFORM_ROOT

logger = logging.getLogger(__name__)

API_TABLES = frozenset(
    {
        "user_profiles",
        "resumes",
        "llm_providers",
        "model_profiles",
        "task_bindings",
        "llm_settings",
        "stage_configs",
        "alembic_version",
    }
)

SESSIONS_TABLES = frozenset(
    {
        "interview_sessions",
        "growth_records",
        "prep_sessions",
        "ws_session_leases",
        "rate_limit_buckets",
        "alembic_version",
    }
)


# Table names come from the registered whitelists above, so _quote_ident
# keeps a strict shape check as defense in depth. Column names are read back
# from the source schema and may be any SQLite-valid name, so _quote_column
# only quotes and escapes them (identifiers cannot be bound parameters).
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _quote_ident(name: str) -> str:
    """Return ``name`` as a quoted SQL identifier; reject anything unusual."""
    if not _IDENTIFIER_RE.fullmatch(name):
        raise ValueError(f"unexpected SQL identifier: {name!r}")
    return f'"{name}"'


def _quote_column(name: str) -> str:
    """Return a column name as a quoted SQL identifier (quotes doubled)."""
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _copy_table(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> None:
    quoted_table = _quote_ident(table)
    existing = {
        r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if table in existing:
        return
    row = src.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not row or not row[0]:
        return
    dst.execute(row[0])
    # Identifiers are safe here (table names whitelist-validated, column
    # names quote-escaped, values parameterized), so silence the pattern
    # scanners that cannot model that guarantee.
    cols = [
        _quote_column(c[1])
        for c in src.execute(f"PRAGMA table_info({quoted_table})")  # nosec B608  # nosemgrep
    ]
    col_list = ", ".join(cols)
    placeholders = ", ".join("?" for _ in cols)
    rows = src.execute(f"SELECT {col_list} FROM {quoted_table}").fetchall()  # nosec B608  # nosemgrep
    if rows:
        dst.executemany(
            f"INSERT INTO {quoted_table} ({col_list}) VALUES ({placeholders})",  # nosec B608  # nosemgrep
            rows,
        )
    dst.commit()


def split_app_db(
    src_path: Path,
    api_path: Path,
    sessions_path: Path,
) -> bool:
    """Copies tables from ``app.db`` to two new databases; returns True on success."""
    if not src_path.is_file():
        return False
    api_path.parent.mkdir(parents=True, exist_ok=True)
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(src_path))
    api_conn = sqlite3.connect(str(api_path))
    sessions_conn = sqlite3.connect(str(sessions_path))
    try:
        src_tables = {
            r[0]
            for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for table in sorted(src_tables):
            if table.startswith("sqlite_"):
                continue
            if table in API_TABLES:
                _copy_table(src, api_conn, table)
            elif table in SESSIONS_TABLES:
                _copy_table(src, sessions_conn, table)
            else:
                logger.warning("Legacy delisting skips unknown tables: %s", table)
        logger.info(
            "The database has been removed from %s to %s and %s",
            src_path.name,
            api_path.name,
            sessions_path.name,
        )
        return True
    finally:
        src.close()
        api_conn.close()
        sessions_conn.close()


def maybe_migrate_legacy_app_db() -> None:
    """If ``app.db`` exists and the new library does not exist, it will be split automatically."""
    data_dir = PLATFORM_ROOT / "data"
    legacy = data_dir / "app.db"
    api_path = data_dir / "api.db"
    sessions_path = data_dir / "sessions.db"
    if api_path.exists() and sessions_path.exists():
        return
    if not legacy.is_file():
        return
    # Only destinations created by this attempt may be cleaned up on
    # failure: a destination that existed beforehand (possibly just one of
    # the two, which still enters the migration) may already hold
    # legitimate data and must survive the failed attempt.
    pre_existing = {p for p in (api_path, sessions_path) if p.exists()}
    try:
        split_app_db(legacy, api_path, sessions_path)
    except Exception:
        logger.exception(
            "Legacy app.db failed to dismantle the library and will be initialized as an empty library."
        )
        # Remove partial outputs so the next startup retries the migration
        # instead of skipping it forever because the destination files exist.
        for path in (api_path, sessions_path):
            if path not in pre_existing:
                path.unlink(missing_ok=True)
