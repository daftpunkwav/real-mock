"""Standalone entry point for the mock interview service (used for validation during the modular monolith phase; production uses the realmock.asgi aggregate).

Run independently: ``uvicorn realmock.domains.interview.main:app --port 8083``
"""

from __future__ import annotations

import asyncio
import logging

from realmock.bootstrap.db_bootstrap import bootstrap_databases_and_seed
from realmock.domains.interview.router import service_router
from realmock.domains.interview.startup import (
    SESSION_DOMAINS,
    ensure_rag_index,
    wire_session_catalog,
)
from realmock.platform.app_factory import create_service_app
from realmock.platform.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


async def _bootstrap() -> None:
    # Create table + migrate
    await asyncio.to_thread(bootstrap_databases_and_seed, session_domains=SESSION_DOMAINS)
    wire_session_catalog()
    await ensure_rag_index()


app = create_service_app(
    service_routers=service_router,
    title="Interview Service",
    description="RealMock simulation interview domain (interview engine/real-time conversation)",
    service_name="interview-service",
    lifespan_startup=_bootstrap,
)
