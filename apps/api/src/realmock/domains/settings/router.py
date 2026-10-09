"""Processor configuration domain route aggregation: the three sub-routes are unified with the /settings prefix and are mounted by the aggregation entry."""

from __future__ import annotations

from fastapi import APIRouter

from realmock.domains.settings.routes import (
    data_router,
    integrations_router,
    model_tests_router,
    models_router,
)
from realmock.domains.settings.routes import (
    router as settings_routes_router,
)

service_router = APIRouter()
service_router.include_router(settings_routes_router, prefix="/settings", tags=["settings"])
service_router.include_router(models_router, prefix="/settings", tags=["settings"])
service_router.include_router(model_tests_router, prefix="/settings", tags=["settings"])
service_router.include_router(integrations_router, prefix="/settings", tags=["settings"])
service_router.include_router(data_router, prefix="/settings", tags=["settings"])
