"""Prep service route aggregation.

Exposes ``service_router`` (routes only) for the aggregate entry point to include; standalone deployment is assembled by
``realmock.domains.prep.main:app`` (via create_service_app).
"""

from __future__ import annotations

from fastapi import APIRouter

from realmock.domains.prep.routes.router import router as prep_router

service_router = APIRouter()
service_router.include_router(prep_router, prefix="/prep", tags=["prep"])

__all__ = [
    "service_router",
]
