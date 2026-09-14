"""Standalone entry point for the Prep service (interview preparation coach) (used for validation during the modular monolith phase; production uses the realmock.asgi aggregate).

Run independently: ``uvicorn realmock.domains.prep.main:app --port 8082``
"""

from __future__ import annotations

import asyncio
import logging

from realmock.bootstrap.db_bootstrap import bootstrap_databases_and_seed
from realmock.domains.prep.router import service_router
from realmock.domains.prep.startup import SESSION_DOMAINS
from realmock.platform.app_factory import create_service_app
from realmock.platform.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


async def _bootstrap() -> None:
    # Table creation + migration + processor configuration seed
    await asyncio.to_thread(bootstrap_databases_and_seed, session_domains=SESSION_DOMAINS)


app = create_service_app(
    service_routers=service_router,
    title="Prep Service",
    description="RealMock Prep Services (Interview Preparation Coach)",
    service_name="prep-service",
    lifespan_startup=_bootstrap,
)

__all__ = [
    "app",
]
