"""Records domain service router aggregation.

Exposes ``service_router`` for the composition root (asgi) to include.
"""

from __future__ import annotations

from fastapi import APIRouter

from realmock.domains.records.routes import history, report

service_router = APIRouter()
service_router.include_router(history.router, prefix="/records", tags=["records"])
service_router.include_router(report.router, prefix="/reports", tags=["reports"])
