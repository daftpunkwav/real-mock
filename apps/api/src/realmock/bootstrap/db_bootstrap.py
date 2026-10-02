"""Database bootstrap: dual-database initialization plus legacy single-file migration.

Business ORM classes must be registered before ``create_all`` runs. This
orchestration depends on ``bootstrap.sessions_orm`` and the business packages,
so it lives in ``bootstrap`` — the platform layer must not import domains.

``session_domains`` selects which business packages register their sessions
ORM, so services started independently do not load unrelated models.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Collection

from realmock.bootstrap.sessions_orm import (
    register_sessions_domain_models,
    sessions_column_migrations,
)
from realmock.platform.config import get_settings
from realmock.platform.core.migrate import API_MIGRATIONS, apply_column_migrations, run_migrations
from realmock.platform.database import (
    ApiSessionLocal,
    dispose_all_engines,
    get_api_engine,
    get_sessions_engine,
    init_db,
    sessions_db_session,
)
from realmock.platform.services.db_split import maybe_migrate_legacy_app_db
from realmock.platform.services.pipeline.config import ensure_pipeline_migrated
from realmock.platform.services.seed import seed_llm_settings

logger = logging.getLogger(__name__)


def _warn_inmemory_backends() -> None:
    """The in-process lease/rate-limiting backend fails under multi-instance deployment, with an explicit warning on startup."""
    settings = get_settings()
    memory_backends = [
        name
        for name, backend in (
            ("ws_lease_backend", settings.ws_lease_backend),
            ("ratelimit_backend", settings.ratelimit_backend),
        )
        if backend == "memory"
    ]
    if memory_backends:
        logger.warning(
            "%s = memory: Applicable to single-process deployment only. It will appear under multiple workers/multiple instances."
            "The same session multi-channel WS and current limit quota are enlarged by N times, please switch to database backend",
            "/".join(memory_backends),
        )


def _run_migrations(session_domains: Collection[str] | None) -> None:
    """Dual-database column-level migration: full api library completion + Alembic stamp; sessions library completion by domain.

    The Alembic version chain only manages the api domain schema (see ``alembic/env.py``); sessions
    The domain table is created by ``SessionsBase.metadata.create_all``. Only idempotent column completion is done here.
    And only apply the business DDL of the registered domain - the independent process does not touch the session table of irrelevant business.
    """
    run_migrations(get_api_engine(), migrations=API_MIGRATIONS)
    sessions_migrations = sessions_column_migrations(session_domains)
    if sessions_migrations:
        apply_column_migrations(get_sessions_engine(), migrations=sessions_migrations)
    if session_domains is None or "interview" in session_domains:
        # Importing the ledger package registers every interview ORM on
        # SessionsBase. Keep that off the module body so a prep-only process
        # does not create interview tables.
        _migrate_interview_ledger()


def _migrate_interview_ledger() -> None:
    """Copy the legacy ledger blob into interview_turns, then drop the column.

    Both steps are idempotent and skip on fresh databases. The import is
    inside the function so it runs only for processes that own interview.
    """
    from realmock.domains.interview.ledger.migration import (
        backfill_ledger_rows,
        drop_legacy_ledger_column,
    )

    with sessions_db_session() as db:
        backfill_ledger_rows(db)
        drop_legacy_ledger_column(db)


def _log_startup_failure(stage: str) -> None:
    """Log an actionable repair path, then let the caller re-raise.

    The process must still fail fast (a half-initialized database is worse
    than a clean crash), but the operator needs to know what to check, not
    just see a bare SQLAlchemy traceback.
    """
    logger.error(
        "Startup %s failed. The SQLite file may be locked by another running "
        "instance, on a read-only disk, or corrupted. Close other instances, "
        "check file permissions of the database files (see API_DATABASE_URL / "
        "SESSIONS_DATABASE_URL), then back up and restore the data directory "
        "before restarting.",
        stage,
        exc_info=True,
    )


def bootstrap_databases_and_seed(
    *,
    session_domains: Collection[str] | None = None,
) -> None:
    """Create tables, migrate, and seed.

    Args:
        session_domains:
            - ``None`` (default): Register all session domains (prep + interview + records + growth), for the aggregate app.
            - Empty set: only the platform sessions table (rate-limit bucket), no business packages imported — API-only process.
            - ``("prep",)`` / ``("interview",)`` / ``("records",)`` / ``("growth",)``: On-demand registration — matching standalone processes.
    """
    if os.environ.get("TEST_MODE") == "1":
        # Tests use the conftest temporary databases; skip the legacy single-file migration.
        pass
    else:
        maybe_migrate_legacy_app_db()
        _warn_inmemory_backends()
    register_sessions_domain_models(session_domains)
    try:
        init_db()
        _run_migrations(session_domains)
    except Exception:
        _log_startup_failure("create tables / migrate")
        raise
    if os.environ.get("TEST_MODE") == "1":
        logger.debug("TEST_MODE: skip seed_llm_settings")
        return
    db = ApiSessionLocal()
    try:
        seed_llm_settings(db)
        ensure_pipeline_migrated(db)
    except Exception:
        _log_startup_failure("seed")
        raise
    finally:
        db.close()


def shutdown_databases() -> None:
    """The shutdown phase releases the twin engines."""
    dispose_all_engines()
