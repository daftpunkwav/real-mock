"""RealMock backend composition root (modular monolith, single process).

Assembles domain ``service_router`` instances into one FastAPI app:

- profile / resume / settings: profile / resume / processor config
- prep: interview prep coach
- interview: live mock interview / WebSocket
- records: history replay + debrief reports
- growth: candidate growth records + system learning

Run: ``uvicorn realmock.asgi:app --port 8081``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from realmock.bootstrap.db_bootstrap import bootstrap_databases_and_seed
from realmock.domains.growth.router import service_router as growth_router
from realmock.domains.growth.services.ingest import register_growth_lifecycle_handlers
from realmock.domains.interview.router import service_router as interview_router
from realmock.domains.interview.startup import ensure_rag_index
from realmock.domains.prep.router import service_router as prep_router
from realmock.domains.profile.router import service_router as profile_router
from realmock.domains.records.router import service_router as records_router
from realmock.domains.records.services.ingest import register_records_lifecycle_handlers
from realmock.domains.resume.router import service_router as resume_router
from realmock.domains.settings.router import service_router as settings_router
from realmock.platform.app_factory import (
    add_default_cors,
    install_trace_middleware,
    register_core_error_handlers,
)
from realmock.platform.config import Settings, get_settings
from realmock.platform.core.logging import configure_logging
from realmock.platform.database import dispose_all_engines
from realmock.platform.router_mount import include_with_legacy_api_alias

logger = logging.getLogger(__name__)

# Domain routers (prefixes owned inside each domain router); mounted under /api/v1
SERVICE_ROUTERS = (
    profile_router,
    resume_router,
    settings_router,
    prep_router,
    interview_router,
    records_router,
    growth_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup / shutdown hooks.

    Sync IO (SQLite / filesystem / local RAG) runs in a thread pool so the
    event loop stays responsive for heartbeats and WebSockets.
    """
    if os.environ.get("TEST_MODE") == "1":
        _bootstrap_db_and_seed()
    else:
        await asyncio.to_thread(_bootstrap_db_and_seed)
    await ensure_rag_index()
    cfg = get_settings()
    logger.info("RealMock backend started env=%s", cfg.env)
    try:
        yield
    finally:
        if not cfg.is_prod and os.environ.get("TEST_MODE") == "1":
            logger.debug("test mode: skip engine dispose")
        else:
            try:
                await asyncio.to_thread(_shutdown_engine)
            except Exception:
                logger.exception("engine dispose failed during shutdown")
        logger.info("RealMock backend stopped")


def _bootstrap_db_and_seed() -> None:
    bootstrap_databases_and_seed()
    _wire_platform_contracts()


def _wire_platform_contracts() -> None:
    """Composition-root wiring: catalog, score projection, insights, ingest hooks."""
    from realmock.domains.growth.column_migrations import ensure_growth_indexes
    from realmock.domains.growth.services.learning import get_system_insights
    from realmock.domains.interview.process.catalog import register_interview_session_catalog
    from realmock.platform.contracts.lifecycle_hooks import (
        get_on_interview_finished,
        get_on_report_summary,
        get_system_insights_provider,
        set_system_insights_provider,
    )
    from realmock.platform.contracts.session_catalog import get_session_catalog
    from realmock.platform.contracts.session_score import get_session_score_projection
    from realmock.platform.database import get_sessions_engine

    register_interview_session_catalog()
    set_system_insights_provider(get_system_insights)
    register_records_lifecycle_handlers()
    register_growth_lifecycle_handlers()
    ensure_growth_indexes(get_sessions_engine())

    # Fail loud in composition root if a required port was not wired.
    catalog = get_session_catalog()
    if type(catalog).__name__ == "_EmptySessionCatalog":
        raise RuntimeError("session catalog port not registered")
    if type(get_session_score_projection()).__name__ == "_NoopScoreProjection":
        raise RuntimeError("session score projection port not registered")
    if get_system_insights_provider() is None:
        raise RuntimeError("system insights provider not registered")
    if get_on_interview_finished() is None:
        raise RuntimeError("interview-finished handler not registered")
    if get_on_report_summary() is None:
        raise RuntimeError("report-summary handler not registered")


def _shutdown_engine() -> None:
    """Dispose both DB engines on shutdown."""
    try:
        dispose_all_engines()
    except Exception:
        logger.exception("engine.dispose failed")


def create_app() -> FastAPI:
    """Build the aggregated FastAPI app: domain routers + middleware."""
    configure_logging()
    cfg = get_settings()
    app = FastAPI(
        title="RealMock API",
        description=(
            "RealMock mock-interview platform composition root "
            "(profile / resume / settings / prep / interview / records / growth)"
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    install_trace_middleware(app)

    _check_cors_policy(cfg)
    add_default_cors(app, cors_origin_list=cfg.cors_origin_list)

    _check_secret_key_policy(cfg)

    include_with_legacy_api_alias(app, SERVICE_ROUTERS)

    register_core_error_handlers(app)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "realmock", "version": "1.0.0"}

    return app


def _check_cors_policy(s: Settings) -> None:
    """Wildcard origins are prohibited in the production environment; allowed but with a warning in the development environment."""
    if "*" in s.cors_origin_list:
        if s.is_prod:
            raise RuntimeError(
                "Invalid CORS configuration: production (env=prod) does not allow allow_origins=['*']."
                "Please explicitly list trusted sources in the environment variable CORS_ORIGINS."
            )
        logger.warning("CORS allows * globbing, dev environments only; production environments already mandate explicit origins")


def _check_secret_key_policy(s: Settings) -> None:
    """prod deployments must explicitly provide SECRET_KEY; otherwise the key is persisted to platform/data/.secret.key,
    and API Key ciphertext cannot be decrypted after the database is migrated from another machine."""
    if s.is_prod:
        from realmock.platform.core.secrets import validate_master_key_env

        status = validate_master_key_env()
        if status != "ok":
            raise RuntimeError(
                "Production environment (env=prod) must set SECRET_KEY (≥16 bytes);"
                "It is forbidden to rely on the automatically generated data/.secret.key, otherwise the ciphertext cannot be decrypted after the database is migrated."
            )


app = create_app()


if __name__ == "__main__":
    boot = get_settings()
    uvicorn.run(app, host=boot.host, port=boot.port)
