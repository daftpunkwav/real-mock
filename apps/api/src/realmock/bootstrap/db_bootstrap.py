"""Aggregation entry database guidance (dual database + legacy demolition database).

Attribution combination root (``bootstrap`` package): Business ORM must be registered before creating a table. This orchestration function depends on
``bootstrap.sessions_orm`` and each business package, so it cannot be placed in the ``platform`` layer
(See ``tests/test_platform_no_domain_imports.py`` for guards).

``session_domains`` controls whether/according to which business package to register sessions ORM, so that each service
There is no need to load unrelated business models when starting independently.
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
)
from realmock.platform.services.db_split import maybe_migrate_legacy_app_db
from realmock.platform.services.seed import seed_llm_settings
from realmock.platform.services.pipeline.config import ensure_pipeline_migrated

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


def bootstrap_databases_and_seed(
    *,
    session_domains: Collection[str] | None = None,
) -> None:
    """Create tables, migrate, and seed.

    Args:
        session_domains:
            - ``None`` (default): Register all session fields (prep + interview + records), for aggregation entry.
            - Empty set: only the platform sessions table (current-limiting bucket), no business packages are imported - api independent process.
            - ``("prep",)`` / ``("interview",)`` / ``("records",)``: On-demand registration - corresponding to business independent process.
    """
    if os.environ.get("TEST_MODE") == "1":
        # The test uses the conftest temporary library and skips the legacy single file demolition.
        pass
    else:
        maybe_migrate_legacy_app_db()
        _warn_inmemory_backends()
    register_sessions_domain_models(session_domains)
    init_db()
    _run_migrations(session_domains)
    if os.environ.get("TEST_MODE") == "1":
        logger.debug("TEST_MODE: skip seed_llm_settings")
        return
    db = ApiSessionLocal()
    try:
        seed_llm_settings(db)
        ensure_pipeline_migrated(db)
    finally:
        db.close()


def shutdown_databases() -> None:
    """The shutdown phase releases the twin engines."""
    dispose_all_engines()
