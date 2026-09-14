"""Growth domain service router aggregation.

Exposes ``service_router`` for the composition root (asgi) to include.
"""

from __future__ import annotations

from fastapi import APIRouter

from realmock.domains.growth.routes import router as growth_routes

service_router = APIRouter()
service_router.include_router(growth_routes, prefix="/growth", tags=["growth"])
