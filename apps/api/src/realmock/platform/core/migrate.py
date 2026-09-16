"""SQLite column-completion migration engine + api-domain manifest + Alembic version stamp.

``API_MIGRATIONS`` (api.db) is colocated with the engine in this module; session-business DDL is owned by each business package
(``realmock.domains.prep.column_migrations`` / ``realmock.domains.interview.column_migrations``).
The composition root assembles them by domain and passes them to ``apply_column_migrations`` / ``run_migrations``—
``migrations`` is required, so callers must explicitly declare the dictionary for the target database and cannot accidentally use the wrong database.
Alembic tracks ``alembic_version`` for the api domain.
CLI: ``alembic upgrade head`` (config ``apps/api/alembic.ini``; only api domain uses Alembic, sessions use create_all + column backfill).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError

from realmock.platform.core.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_OUTPUT_TOKENS,
)

logger = logging.getLogger(__name__)

# Aligned with the revision id in alembic/versions (the version chain manages only the api-domain schema)
ALEMBIC_HEAD_REVISION = "20260916_0004"

# api.db:archive/resume/processor-config
API_MIGRATIONS: dict[str, list[str]] = {
    "user_profiles": [
        "ALTER TABLE user_profiles ADD COLUMN gender VARCHAR(20) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN identity VARCHAR(50) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN school VARCHAR(200) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN major VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN graduation_year VARCHAR(20) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN work_years_detail VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN current_company VARCHAR(200) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN expected_salary VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN self_intro TEXT DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN github_username VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN portfolio_url VARCHAR(500) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN linkedin_url VARCHAR(500) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN city VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN preferred_languages VARCHAR(200) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN career_highlights TEXT DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN open_to_remote VARCHAR(20) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN notice_period VARCHAR(50) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN education_level VARCHAR(50) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN expected_city VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN email VARCHAR(200) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN phone VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN certificates TEXT DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN english_level VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN signature_projects TEXT DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN strengths TEXT DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN weaknesses TEXT DEFAULT ''",
    ],
    "llm_settings": [
        "ALTER TABLE llm_settings ADD COLUMN protocol VARCHAR(50) DEFAULT 'openai_chat'",
        "ALTER TABLE llm_settings ADD COLUMN reasoning_effort VARCHAR(20) DEFAULT 'medium'",
        "ALTER TABLE llm_settings ADD COLUMN supports_vision BOOLEAN DEFAULT 1",
        "ALTER TABLE llm_settings ADD COLUMN supports_audio BOOLEAN DEFAULT 0",
        "ALTER TABLE llm_settings ADD COLUMN stt_model VARCHAR(50) DEFAULT 'base'",
        "ALTER TABLE llm_settings ADD COLUMN tts_voice VARCHAR(100) DEFAULT 'zh-CN-XiaoxiaoNeural'",
        "ALTER TABLE llm_settings ADD COLUMN speech_recognize_handler VARCHAR(50) DEFAULT 'local'",
        "ALTER TABLE llm_settings ADD COLUMN speech_recognize_mode VARCHAR(30) DEFAULT 'transcribe'",
        "ALTER TABLE llm_settings ADD COLUMN asr_api_base VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_api_key VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_model VARCHAR(100) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_app_id VARCHAR(100) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_api_secret VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_access_key VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_resource_id VARCHAR(100) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_app_key VARCHAR(100) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN speech_speak_handler VARCHAR(50) DEFAULT 'edge'",
        "ALTER TABLE llm_settings ADD COLUMN speech_speak_mode VARCHAR(30) DEFAULT 'tts_from_text'",
        "ALTER TABLE llm_settings ADD COLUMN tts_api_base VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN tts_api_key VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN tts_model VARCHAR(100) DEFAULT ''",
    ],
    "llm_providers": [
        "ALTER TABLE llm_providers ADD COLUMN full_url BOOLEAN DEFAULT 0",
    ],
    "stage_configs": [
        (
            "CREATE TABLE IF NOT EXISTS stage_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "stage VARCHAR(30) NOT NULL UNIQUE, provider VARCHAR(100) DEFAULT '', "
            "api_base VARCHAR(500) DEFAULT '', api_key VARCHAR(500) DEFAULT '', "
            "protocol VARCHAR(50) DEFAULT 'openai_chat', model VARCHAR(100) DEFAULT '', "
            f"max_tokens INTEGER DEFAULT {DEFAULT_MAX_OUTPUT_TOKENS}, "
            f"context_window INTEGER DEFAULT {DEFAULT_CONTEXT_WINDOW}, "
            "supports_vision BOOLEAN DEFAULT 0, supports_audio_input BOOLEAN DEFAULT 0, "
            "supports_audio_output BOOLEAN DEFAULT 0, supports_video_input BOOLEAN DEFAULT 0, "
            "fallback_handler VARCHAR(100) DEFAULT '', fallback_mode VARCHAR(30) DEFAULT '', "
            "extras TEXT DEFAULT '{}', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        ),
    ],
    "resumes": [
        "ALTER TABLE resumes ADD COLUMN is_active BOOLEAN DEFAULT 0",
        "ALTER TABLE resumes ADD COLUMN score INTEGER",
        "ALTER TABLE resumes ADD COLUMN analysis TEXT DEFAULT '{}'",
        "ALTER TABLE resumes ADD COLUMN family_id INTEGER DEFAULT 0",
        "ALTER TABLE resumes ADD COLUMN version_n INTEGER DEFAULT 1",
    ],
}

def _column_name_from_stmt(stmt: str) -> str | None:
    """Extract column names from an ALTER ADD COLUMN statement."""
    try:
        marker = "ADD COLUMN"
        idx = stmt.upper().find(marker)
        if idx < 0:
            return None
        rest = stmt[idx + len(marker) :].strip()
        token = rest.split()[0] if rest else ""
        return token.strip('"').strip("`").strip("[]") or None
    except Exception:
        return None


def apply_column_migrations(
    engine: Engine,
    *,
    migrations: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Idempotently add missing columns. Returns ``{table: [applied_sql, ...]}``.

    Args:
        migrations: Table-to-statements mapping, **required**; the API domain passes
            ``API_MIGRATIONS``, while the composition root assembles the session-domain mapping
            from registered business groups.
    """
    backend = engine.url.get_backend_name()
    if backend != "sqlite":
        logger.info("Non-SQLite database (%s), skips column-level ALTER migration, relies on Alembic", backend)
        return {}

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    applied: dict[str, list[str]] = {}

    for table, statements in migrations.items():
        if table not in existing_tables:
            create_statements = [
                statement
                for statement in statements
                if statement.lstrip().upper().startswith("CREATE TABLE")
            ]
            if not create_statements:
                continue
            try:
                with engine.begin() as conn:
                    for statement in create_statements:
                        conn.execute(text(statement))
                applied[table] = create_statements
                existing_tables.add(table)
            except Exception as e:
                logger.error("Migration failed %s (table creation transaction has been rolled back): %s", table, e, exc_info=True)
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        to_apply: list[str] = [
            s
            for s in statements
            if (col := _column_name_from_stmt(s)) and col not in existing_cols
        ]
        if not to_apply:
            continue
        try:
            with engine.begin() as conn:
                for stmt in to_apply:
                    conn.execute(text(stmt))
                    logger.info("Migration successful: %s", stmt[:80])
            applied[table] = to_apply
        except (OperationalError, IntegrityError) as e:
            logger.error("Migration failed %s (transaction rolled back): %s", table, e, exc_info=True)
        except Exception as e:
            logger.error(
                "Migration failed %s (transaction rolled back, unknown exception type): %s",
                table,
                e,
                exc_info=True,
            )

    if applied:
        logger.info(
            "Database migration completed, a total of %d tables and %d columns were added",
            len(applied),
            sum(len(v) for v in applied.values()),
        )
    else:
        logger.debug("No database column migration required")
    return applied


def stamp_alembic_head(engine: Engine, revision: str = ALEMBIC_HEAD_REVISION) -> None:
    """Write the head version stamp when a database first adopts Alembic.

    Insert only when ``alembic_version`` is empty; if an existing version differs from head,
    **preserve the original record and warn**—overwriting it unconditionally would cause future
    incremental revisions in ``alembic upgrade`` to be skipped, defeating version tracking.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL PRIMARY KEY"
                ")"
            )
        )
        row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
        if row is None:
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": revision},
            )
        elif row[0] != revision:
            logger.warning(
                "alembic_version=%s is inconsistent with the code head=%s: keep the original version record;"
                "If you need to align, please explicitly execute alembic upgrade head or alembic stamp",
                row[0],
                revision,
            )


def _backfill_resume_lineage(engine: Engine) -> None:
    """Assign each existing resume its own family when family_id is still 0/NULL."""
    inspector = inspect(engine)
    if "resumes" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("resumes")}
    if "family_id" not in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE resumes SET family_id = id WHERE family_id IS NULL OR family_id = 0")
        )
        if "version_n" in cols:
            conn.execute(
                text("UPDATE resumes SET version_n = 1 WHERE version_n IS NULL OR version_n < 1")
            )


def run_migrations(
    engine: Engine,
    *,
    migrations: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Single-database entry point: column backfill + Alembic version stamp (used by the api engine; ``migrations`` is required)."""
    applied = apply_column_migrations(engine, migrations=migrations)
    _backfill_resume_lineage(engine)
    try:
        stamp_alembic_head(engine)
    except Exception:
        logger.exception("Writing to alembic_version failed (column migration completed)")
    return applied


def alembic_config_path() -> Path:
    """apps/api/alembic.ini."""
    return Path(__file__).resolve().parents[4] / "alembic.ini"
